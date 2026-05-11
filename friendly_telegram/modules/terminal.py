"""Run shell commands from the userbot.

Streams stdout/stderr back into the chat in real time, with sudo
password prompting via Saved Messages and SIGTERM/SIGKILL helpers
for runaway processes.
"""

import asyncio
import contextlib
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional

import telethon
from telethon.errors import (
    MessageEmptyError,
    MessageNotModifiedError,
    MessageTooLongError,
)
from telethon.tl.custom import Message

from .. import loader, utils

logger = logging.getLogger(__name__)


_PASS_REQ = "[sudo] password for"
_WRONG_PASS = re.compile(r"\[sudo\] password for (.*): Sorry, try again\.")
_TOO_MANY_TRIES = re.compile(
    r"\[sudo\] password for (.*): sudo: [0-9]+ incorrect password attempts"
)


def _hash_msg(message: Message) -> str:
    """Stable identifier for one chat message — used as activecmds key."""
    return f"{utils.get_chat_id(message)}/{message.id}"


async def _read_stream(
    func: Callable[[str], Awaitable[None]],
    stream: asyncio.StreamReader,
    delay: float,
) -> None:
    """Pump ``stream`` byte-by-byte into ``func``, debouncing edits to ``delay``s.

    The trailing pending edit is flushed once the stream hits EOF so the
    user doesn't lose the final lines.
    """

    async def _flush_after(payload: bytes) -> None:
        await asyncio.sleep(delay)
        await func(payload.decode("utf-8", errors="replace"))

    last: Optional[asyncio.Task] = None
    data = b""
    while True:
        chunk = await stream.read(1)
        if not chunk:
            if last:
                last.cancel()
                await func(data.decode("utf-8", errors="replace"))
            return
        data += chunk
        if last:
            last.cancel()
        last = asyncio.ensure_future(_flush_after(data))


# ---------------------------------------------------------------- editors


@dataclass
class _MessageEditor:
    """Render the running command + its (truncated) stdout/stderr into chat.

    Subclassed by :class:`_SudoMessageEditor` for password handling and by
    :class:`_RawMessageEditor` for raw passthrough output.
    """

    message: Any  # telethon Message or list of them; utils.answer normalises
    command: str
    config: loader.ModuleConfig
    strings: Any  # callable Strings (post-tds) or dict pre-tds; both subscriptable
    request_message: Message
    stdout: str = ""
    stderr: str = ""
    rc: Optional[int] = None

    async def update_stdout(self, stdout: str) -> None:
        self.stdout = stdout
        await self.redraw()

    async def update_stderr(self, stderr: str) -> None:
        self.stderr = stderr
        await self.redraw()

    async def redraw(self) -> None:
        rm = self.request_message
        text = self.strings("running", rm).format(utils.escape_html(self.command))
        if self.rc is not None:
            text += self.strings("finished", rm).format(utils.escape_html(str(self.rc)))
        text += self.strings("stdout", rm)
        text += utils.escape_html(self.stdout[-2048:])
        text += self.strings("stderr", rm)
        text += utils.escape_html(self.stderr[-1024:])
        text += self.strings("end", rm)
        try:
            self.message = await utils.answer(self.message, text)
        except MessageNotModifiedError:
            pass
        except MessageTooLongError as e:
            logger.error("terminal output too long: %s", e)

    async def cmd_ended(self, rc: int) -> None:
        self.rc = rc
        await self.redraw()

    def update_process(self, process: asyncio.subprocess.Process) -> None:
        # Hook for sudo editor; default is a no-op.
        return


@dataclass
class _SudoMessageEditor(_MessageEditor):
    process: Optional[asyncio.subprocess.Process] = None
    state: int = 0  # 0 idle, 1 sent password, 2 finished/locked, 3 stdout-only
    authmsg: Optional[Message] = None
    _handler_bound: bool = field(default=False, init=False, repr=False)

    def update_process(self, process: asyncio.subprocess.Process) -> None:
        self.process = process

    async def update_stderr(self, stderr: str) -> None:
        self.stderr = stderr
        lines = stderr.strip().split("\n")
        last = lines[-1] if lines else ""
        last_split = last.rsplit(" ", 1)
        handled = False

        # Wrong password — re-prompt.
        if (
            len(lines) > 1
            and _WRONG_PASS.fullmatch(lines[-2])
            and last_split[0] == _PASS_REQ
            and self.state == 1
            and self.authmsg is not None
        ):
            await self.authmsg.edit(self.strings("auth_failed", self.request_message))
            self.state = 0
            handled = True
            await asyncio.sleep(2)
            with contextlib.suppress(Exception):
                if self.authmsg is not None:
                    await self.authmsg.delete()

        # First sudo password prompt.
        elif last_split[0] == _PASS_REQ and self.state == 0:
            text = self.strings("auth_needed", self.request_message).format(
                (await self.message[0].client.get_me()).id
            )
            with contextlib.suppress(MessageNotModifiedError):
                await utils.answer(self.message, text)
            command_html = "<code>" + utils.escape_html(self.command) + "</code>"
            user = utils.escape_html(last_split[1][:-1] if len(last_split) > 1 else "")
            self.authmsg = await self.message[0].client.send_message(
                "me",
                self.strings("auth_msg", self.request_message).format(
                    command_html, user
                ),
            )
            client = self.message[0].client
            if self._handler_bound:
                client.remove_event_handler(self.on_message_edited)
            client.add_event_handler(
                self.on_message_edited,
                telethon.events.MessageEdited(chats=["me"]),
            )
            self._handler_bound = True
            handled = True

        # Out of attempts.
        elif (
            len(lines) > 1
            and _TOO_MANY_TRIES.fullmatch(last)
            and self.state in (1, 3, 4)
        ):
            await utils.answer(
                self.message, self.strings("auth_locked", self.request_message)
            )
            if self.authmsg:
                with contextlib.suppress(Exception):
                    await self.authmsg.delete()
            self.state = 2
            handled = True

        if not handled:
            if self.authmsg is not None:
                with contextlib.suppress(Exception):
                    await self.authmsg.delete()
                self.authmsg = None
            self.state = 2
            await self.redraw()

    async def update_stdout(self, stdout: str) -> None:
        self.stdout = stdout
        if self.state != 2:
            self.state = 3
        if self.authmsg is not None:
            with contextlib.suppress(Exception):
                await self.authmsg.delete()
            self.authmsg = None
        await self.redraw()

    async def on_message_edited(self, message: Message) -> None:
        if self.authmsg is None:
            return
        if _hash_msg(message) != _hash_msg(self.authmsg):
            return
        # Password came in — wipe the visible copy and pipe it to sudo.
        try:
            ret = await utils.answer(
                message, self.strings("auth_ongoing", self.request_message)
            )
            if isinstance(ret, (list, tuple)) and ret:
                first = ret[0]
            else:
                first = ret
            self.authmsg = first if isinstance(first, Message) else None
        except MessageNotModifiedError:
            with contextlib.suppress(Exception):
                await message.delete()
        self.state = 1
        if self.process and self.process.stdin:
            raw = message.message
            text = raw.split("\n", 1)[0] if raw else ""
            password = text.encode("utf-8") + b"\n"
            self.process.stdin.write(password)


@dataclass
class _RawMessageEditor(_SudoMessageEditor):
    """Echo the command's raw output without the formatted header.

    Inherits the sudo handling so ``apt`` can still prompt for a password.
    """

    show_done: bool = False

    async def redraw(self) -> None:
        if self.rc is None:
            payload = self.stdout[-4095:]
        elif self.rc == 0:
            payload = self.stdout[-4090:]
        else:
            payload = self.stderr[-4095:]
        text = "<code>" + utils.escape_html(payload) + "</code>"
        if self.rc is not None and self.show_done:
            text += "\n" + self.strings("done", self.request_message)
        try:
            await utils.answer(self.message, text)
        except (MessageNotModifiedError, MessageEmptyError, ValueError):
            pass
        except MessageTooLongError as e:
            logger.error("terminal raw output too long: %s", e)


# ---------------------------------------------------------------- module


@loader.tds
class TerminalMod(loader.Module):
    """Runs commands"""

    strings = {
        "name": "Terminal",
        "flood_wait_protect_cfg_doc": (
            "How long to wait in seconds between edits in commands"
        ),
        "what_to_kill": "<b>Reply to a terminal command to terminate it</b>",
        "kill_fail": "<b>Could not kill process</b>",
        "killed": "<b>Killed</b>",
        "no_cmd": "<b>No command is running in that message</b>",
        "running": "<b>Command:</b> <code>{}</code>",
        "finished": "\n<b>Code:</b> <code>{}</code>",
        "stdout": "\n<b>Stdout:</b>\n<code>",
        "stderr": "</code>\n\n<b>Stderr:</b>\n<code>",
        "end": "</code>",
        "auth_failed": "<b>Authentication failed, please try again</b>",
        "auth_needed": (
            '<a href="tg://user?id={}">Interactive authentication required</a>'
        ),
        "auth_msg": (
            "<b>Please edit this message to the password for</b> "
            "<code>{}</code> <b>to run</b> <code>{}</code>"
        ),
        "auth_locked": "<b>Authentication failed, please try again later</b>",
        "auth_ongoing": "<b>Authenticating...</b>",
        "done": "<b>Done</b>",
    }

    def __init__(self) -> None:
        self.config = loader.ModuleConfig(
            "FLOOD_WAIT_PROTECT",
            2,
            lambda m: self.tr("flood_wait_protect_cfg_doc", m),
        )
        self.activecmds: Dict[str, asyncio.subprocess.Process] = {}

    # ----------------------------------------------------------------- core

    @staticmethod
    def _ensure_sudo_S(cmd: str) -> str:
        """Inject ``-S`` so sudo reads the password from stdin (our editor)."""
        parts = cmd.split(" ")
        if len(parts) <= 1 or parts[0] != "sudo":
            return cmd
        for word in parts[1:]:
            if not word or not word.startswith("-"):
                break
            if word == "-S":
                return cmd
        head, tail = cmd.split(" ", 1)
        return f"{head} -S {tail}"

    async def run_command(
        self,
        message: Message,
        cmd: str,
        editor: Optional[_MessageEditor] = None,
    ) -> None:
        cmd = self._ensure_sudo_S(cmd)
        sproc = await asyncio.create_subprocess_shell(
            cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=utils.get_base_dir(),
        )
        if editor is None:
            editor = _SudoMessageEditor(
                message=message,
                command=cmd,
                config=self.config,
                strings=self.strings,
                request_message=message,
            )
        editor.update_process(sproc)
        key = _hash_msg(message)
        self.activecmds[key] = sproc
        try:
            await editor.redraw()
            assert sproc.stdout is not None and sproc.stderr is not None
            await asyncio.gather(
                _read_stream(
                    editor.update_stdout,
                    sproc.stdout,
                    self.config["FLOOD_WAIT_PROTECT"],
                ),
                _read_stream(
                    editor.update_stderr,
                    sproc.stderr,
                    self.config["FLOOD_WAIT_PROTECT"],
                ),
            )
            await editor.cmd_ended(await sproc.wait())
        finally:
            self.activecmds.pop(key, None)

    async def _signal_reply(
        self,
        message: Message,
        send: Callable[[asyncio.subprocess.Process], None],
    ) -> None:
        """Common backend for terminate/kill — locate process by reply-to msg."""
        if not message.is_reply:
            await utils.answer(message, self.tr("what_to_kill", message))
            return
        reply = await message.get_reply_message()
        if reply is None:
            await utils.answer(message, self.tr("no_cmd", message))
            return
        proc = self.activecmds.get(_hash_msg(reply))
        if proc is None:
            await utils.answer(message, self.tr("no_cmd", message))
            return
        try:
            send(proc)
        except Exception:
            logger.exception("signalling process failed")
            await utils.answer(message, self.tr("kill_fail", message))
        else:
            await utils.answer(message, self.tr("killed", message))

    # --------------------------------------------------------------- commands

    @loader.owner
    async def terminalcmd(self, message: Message) -> None:
        """.terminal <command> - Run a shell command"""
        await self.run_command(message, utils.get_args_raw(message))

    @loader.owner
    async def aptcmd(self, message: Message) -> None:
        """Shorthand for `.terminal apt`"""
        args = utils.get_args_raw(message)
        prefix = "apt " if os.geteuid() == 0 else "sudo -S apt "
        await self.run_command(
            message,
            prefix + args + " -y",
            _RawMessageEditor(
                message=message,
                command="apt " + args,
                config=self.config,
                strings=self.strings,
                request_message=message,
                show_done=True,
            ),
        )

    @loader.owner
    async def terminatecmd(self, message: Message) -> None:
        """Reply to a terminal command to send SIGTERM"""
        await self._signal_reply(message, lambda p: p.terminate())

    @loader.owner
    async def killcmd(self, message: Message) -> None:
        """Reply to a terminal command to send SIGKILL"""
        await self._signal_reply(message, lambda p: p.kill())

    @loader.owner
    async def neofetchcmd(self, message: Message) -> None:
        """Show system stats via neofetch"""
        await self.run_command(
            message,
            "neofetch --stdout",
            _RawMessageEditor(
                message=message,
                command="neofetch --stdout",
                config=self.config,
                strings=self.strings,
                request_message=message,
            ),
        )

    @loader.owner
    async def uptimecmd(self, message: Message) -> None:
        """Show system uptime"""
        await self.run_command(
            message,
            "uptime",
            _RawMessageEditor(
                message=message,
                command="uptime",
                config=self.config,
                strings=self.strings,
                request_message=message,
            ),
        )
