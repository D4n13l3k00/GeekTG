"""
█ █ ▀ █▄▀ ▄▀█ █▀█ ▀    ▄▀█ ▀█▀ ▄▀█ █▀▄▀█ ▄▀█
█▀█ █ █ █ █▀█ █▀▄ █ ▄  █▀█  █  █▀█ █ ▀ █ █▀█

Copyright 2022 t.me/hikariatama
Licensed under the GNU GPLv3
"""

# scope: inline_content

import asyncio
import logging
import time
from io import BytesIO
from typing import Optional, Union

from telethon.errors.rpcerrorlist import ChatSendInlineForbiddenError
from telethon.tl.custom import Message

from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)


# (label, level) pairs reused by both the .logs and .setloglevel pickers.
_LOG_LEVELS = [
    ("🚨 Critical", logging.CRITICAL),
    ("🚫 Error", logging.ERROR),
    ("⚠️ Warning", logging.WARNING),
    ("ℹ️ Info", logging.INFO),
    ("🧑‍💻 Debug", logging.DEBUG),
    ("👁 All", 0),
]


def _level_name(lvl: int) -> Union[int, str]:
    return logging.getLevelName(lvl) if lvl in logging._levelToName else lvl


def _parse_level(token: str) -> Optional[int]:
    """Accept a numeric or named level. Return None if unrecognized."""
    if not token:
        return None
    try:
        return int(token)
    except ValueError:
        named = getattr(logging, token.upper(), None)
        return named if isinstance(named, int) else None


@loader.tds
class TestMod(loader.Module):
    """Perform operations based on userbot self-testing"""

    strings = {
        "name": "Tester",
        "set_loglevel": "🚫 <b>Please specify verbosity as an integer or string</b>",
        "no_logs": "ℹ️ <b>You don't have any logs at verbosity {}.</b>",
        "logs_filename": "geektg-logs.txt",
        "logs_caption": "🗞 GeekTG logs with verbosity {}",
        "suspend_invalid_time": "🚫 <b>Invalid time to suspend</b>",
        "suspended": "🥶 <b>Bot suspended for</b> <code>{}</code> <b>seconds</b>",
        "results_ping": "⏱ <b>Ping:</b> <code>{}</code> <b>ms</b>",
        "confidential": (
            "⚠️ <b>Log level </b><code>{}</code><b> "
            "may reveal your confidential info, be careful</b>"
        ),
        "confidential_text": (
            "⚠️ <b>Log level </b><code>{0}</code><b> "
            "may reveal your confidential info, be careful</b>\n"
            "<b>Type </b>"
            "<code>.logs {0} force_insecure</code>"
            "<b> to ignore this warning</b>"
        ),
        "choose_loglevel": "💁‍♂️ <b>Choose log level</b>",
        "loglevel_set": (
            "✅ <b>Stdout log level set to </b><code>{}</code><b>. "
            "Saved — survives restart.</b>"
        ),
        "loglevel_invalid": (
            "🚫 <b>Unknown level. Use a name (DEBUG/INFO/WARNING/ERROR/CRITICAL) "
            "or an int (0/10/20/30/40/50).</b>"
        ),
    }

    @staticmethod
    async def dumpcmd(message: Message) -> None:
        """Use in reply to get a dump of a message"""
        if not message.is_reply:
            return
        reply = await message.get_reply_message()
        if reply is None:
            return
        await utils.answer(
            message,
            "<code>" + utils.escape_html(reply.stringify()) + "</code>",
        )

    @staticmethod
    async def cancel(call: InlineCall) -> None:
        await call.delete()

    # ----------------------------------------------------------------- helpers

    def _level_keyboard(self, callback, extra_args: tuple = ()) -> list:
        """Build the 3x2 loglevel keyboard used by .logs and .setloglevel."""
        rows = []
        pairs = list(_LOG_LEVELS)
        for left, right in zip(pairs[::2], pairs[1::2]):
            rows.append(
                [
                    {
                        "text": left[0],
                        "callback": callback,
                        "args": (*extra_args, left[1]),
                    },
                    {
                        "text": right[0],
                        "callback": callback,
                        "args": (*extra_args, right[1]),
                    },
                ]
            )
        rows.append([{"text": "🚫 Cancel", "callback": self.cancel}])
        return rows

    async def _resolve_lvl(self, message, lvl: Optional[int]) -> Optional[int]:
        """Coerce a numeric level out of either the explicit arg or message text."""
        if isinstance(lvl, int):
            return lvl
        if isinstance(message, Message):
            args = utils.get_args_raw(message)
            if args:
                return _parse_level(args.split()[0])
        return None

    # -------------------------------------------------------------- .logs flow

    async def logscmd(
        self,
        message: Union[Message, InlineCall],
        force: bool = False,
        lvl: Union[int, None] = None,
    ) -> None:
        """<level> - Dumps logs. Loglevels below WARNING may contain personal info."""
        lvl = await self._resolve_lvl(message, lvl)
        if not isinstance(lvl, int):
            await self._prompt_level(message, callback=self.logscmd, extra=(False,))
            return

        named = _level_name(lvl)
        if lvl < logging.WARNING and not force and not self._allow_insecure(message):
            await self._confidential_gate(message, lvl, named)
            return

        await self._send_logs(message, lvl, named)

    def _allow_insecure(self, message) -> bool:
        return (
            isinstance(message, Message)
            and "force_insecure" in (message.raw_text or "").lower()
        )

    async def _prompt_level(self, message, callback, extra: tuple) -> None:
        if not self.inline.init_complete:
            await utils.answer(message, self.tr("set_loglevel"))
            return
        await self.inline.form(
            text=self.tr("choose_loglevel"),
            reply_markup=self._level_keyboard(callback, extra),
            message=message,
        )

    async def _confidential_gate(self, message, lvl: int, named) -> None:
        if not self.inline.init_complete:
            await utils.answer(message, self.tr("confidential_text").format(named))
            return

        cfg = {
            "text": self.tr("confidential").format(named),
            "reply_markup": [
                [
                    {
                        "text": "📤 Send anyway",
                        "callback": self.logscmd,
                        "args": [True, lvl],
                    },
                    {"text": "🚫 Cancel", "callback": self.cancel},
                ]
            ],
        }
        try:
            if isinstance(message, Message):
                await self.inline.form(**cfg, message=message)
            else:
                await message.edit(**cfg)
        except ChatSendInlineForbiddenError:
            await utils.answer(message, self.tr("confidential_text").format(named))

    async def _send_logs(self, message, lvl: int, named) -> None:
        joined = "\n\n".join(
            "\n".join(getattr(handler, "dumps")(lvl))
            for handler in logging.getLogger().handlers
            if hasattr(handler, "dumps")
        )

        if not joined.strip():
            text = self.tr("no_logs").format(named)
            if isinstance(message, Message):
                await utils.answer(message, text)
            else:
                await message.edit(text)
                await message.unload()
            return

        buf = BytesIO(joined.encode("utf-16"))
        buf.name = self.tr("logs_filename")
        caption = self.tr("logs_caption").format(named)

        if isinstance(message, Message):
            await utils.answer(message, buf, caption=caption)
        else:
            await message.delete()
            await self.ctx.client.send_file(message.form["chat"], buf, caption=caption)

    # ----------------------------------------------------------- .setloglevel

    async def _apply_loglevel(self, lvl: int) -> None:
        for handler in logging.getLogger().handlers:
            handler.setLevel(lvl)
        self.ctx.db.set("friendly_telegram.main", "loglevel", lvl)

    @loader.owner
    async def setloglevelcmd(
        self,
        message: Union[Message, InlineCall],
        lvl: Union[int, None] = None,
    ) -> None:
        """<level> - Set stdout log level (CRITICAL/ERROR/WARNING/INFO/DEBUG or 0-50). Persists across restarts."""
        lvl = await self._resolve_lvl(message, lvl)
        if not isinstance(lvl, int):
            # Bad explicit arg → tell the user; no arg → show picker.
            if isinstance(message, Message) and utils.get_args_raw(message):
                await utils.answer(message, self.tr("loglevel_invalid"))
                return
            await self._prompt_level(message, callback=self.setloglevelcmd, extra=())
            return

        await self._apply_loglevel(lvl)
        text = self.tr("loglevel_set").format(_level_name(lvl))
        if isinstance(message, Message):
            await utils.answer(message, text)
        else:
            await message.edit(text)

    # ------------------------------------------------------------------ misc

    @loader.owner
    async def suspendcmd(self, message: Message) -> None:
        """.suspend <time>
        Suspends the bot for N seconds"""
        try:
            seconds = float(utils.get_args_raw(message))
        except ValueError:
            await utils.answer(message, self.tr("suspend_invalid_time", message))
            return

        await utils.answer(message, self.tr("suspended", message).format(seconds))
        # asyncio.sleep so we don't block the event loop and freeze every
        # other client / handler attached to the same loop.
        await asyncio.sleep(seconds)

    async def pingcmd(self, message: Message) -> None:
        """Test your userbot ping"""
        start = time.perf_counter_ns()
        msgs = await utils.answer(message, "<code>Ping checking...</code>")
        end = time.perf_counter_ns()
        ms = (end - start) * 0.000001
        await utils.answer(msgs, self.tr("results_ping").format(round(ms, 3)))
