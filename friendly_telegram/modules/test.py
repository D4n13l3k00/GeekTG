"""
█ █ ▀ █▄▀ ▄▀█ █▀█ ▀    ▄▀█ ▀█▀ ▄▀█ █▀▄▀█ ▄▀█
█▀█ █ █ █ █▀█ █▀▄ █ ▄  █▀█  █  █▀█ █ ▀ █ █▀█

Copyright 2022 t.me/hikariatama
Licensed under the GNU GPLv3
"""

# scope: inline_content

import logging
import time
from io import BytesIO
from typing import Union

from telethon.errors.rpcerrorlist import ChatSendInlineForbiddenError
from telethon.tl.types import Message

from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)


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

        await utils.answer(
            message,
            "<code>"
            + utils.escape_html((await message.get_reply_message()).stringify())
            + "</code>",
        )

    @staticmethod
    async def cancel(call: InlineCall) -> None:
        await call.delete()

    async def logscmd(
        self,
        message: Union[Message, InlineCall],
        force: bool = False,
        lvl: Union[int, None] = None,
    ) -> None:
        """<level> - Dumps logs. Loglevels below WARNING may contain personal info."""
        if not isinstance(lvl, int):
            args = utils.get_args_raw(message)
            try:
                try:
                    lvl = int(args.split()[0])
                except ValueError:
                    lvl = getattr(logging, args.split()[0].upper(), None)
            except IndexError:
                lvl = None

        if not isinstance(lvl, int):
            if self.inline.init_complete:
                await self.inline.form(
                    text=self.strings("choose_loglevel"),
                    reply_markup=[
                        [
                            {
                                "text": "🚨 Critical",
                                "callback": self.logscmd,
                                "args": (False, 50),
                            },
                            {
                                "text": "🚫 Error",
                                "callback": self.logscmd,
                                "args": (False, 40),
                            },
                        ],
                        [
                            {
                                "text": "⚠️ Warning",
                                "callback": self.logscmd,
                                "args": (False, 30),
                            },
                            {
                                "text": "ℹ️ Info",
                                "callback": self.logscmd,
                                "args": (False, 20),
                            },
                        ],
                        [
                            {
                                "text": "🧑‍💻 Debug",
                                "callback": self.logscmd,
                                "args": (False, 10),
                            },
                            {
                                "text": "👁 All",
                                "callback": self.logscmd,
                                "args": (False, 0),
                            },
                        ],
                        [{"text": "🚫 Cancel", "callback": self.cancel}],
                    ],
                    message=message,
                )
            else:
                await utils.answer(message, self.strings("set_loglevel"))

            return

        logs = "\n\n".join(
            [
                ("\n".join(handler.dumps(lvl)))
                for handler in logging.getLogger().handlers
            ]
        ).encode("utf-16")

        named_lvl = (
            lvl
            if lvl not in logging._levelToName
            else logging._levelToName[lvl]  # skipcq: PYL-W0212
        )

        if (
            lvl < logging.WARNING
            and not force
            and (
                not isinstance(message, Message)
                or "force_insecure" not in message.raw_text.lower()
            )
        ):
            if self.inline.init_complete:
                try:
                    cfg = {
                        "text": self.strings("confidential").format(named_lvl),
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
                    if isinstance(message, Message):
                        await self.inline.form(**cfg, message=message)
                    else:
                        await message.edit(**cfg)
                except ChatSendInlineForbiddenError:
                    await utils.answer(
                        message, self.strings("confidential_text").format(named_lvl)
                    )
            else:
                await utils.answer(
                    message, self.strings("confidential_text").format(named_lvl)
                )

            return

        if len(logs) <= 2:
            if isinstance(message, Message):
                await utils.answer(message, self.strings("no_logs").format(named_lvl))
            else:
                await message.edit(self.strings("no_logs").format(named_lvl))
                await message.unload()

            return

        logs = BytesIO(logs)
        logs.name = self.strings("logs_filename")

        if isinstance(message, Message):
            await utils.answer(
                message, logs, caption=self.strings("logs_caption").format(named_lvl)
            )
        else:
            await message.delete()
            await self._client.send_file(
                message.form["chat"],
                logs,
                caption=self.strings("logs_caption").format(named_lvl),
            )

    async def _apply_loglevel(self, lvl: int) -> None:
        for handler in logging.getLogger().handlers:
            handler.setLevel(lvl)
        self._db.set("friendly_telegram.main", "loglevel", lvl)

    @loader.owner
    async def setloglevelcmd(
        self,
        message: Union[Message, InlineCall],
        lvl: Union[int, None] = None,
    ) -> None:
        """<level> - Set stdout log level (CRITICAL/ERROR/WARNING/INFO/DEBUG or 0-50). Persists across restarts."""
        if not isinstance(lvl, int):
            args = utils.get_args_raw(message) if isinstance(message, Message) else ""
            if args:
                try:
                    lvl = int(args.split()[0])
                except ValueError:
                    lvl = getattr(logging, args.split()[0].upper(), None)

        if not isinstance(lvl, int):
            if isinstance(message, Message) and utils.get_args_raw(message):
                await utils.answer(message, self.strings("loglevel_invalid"))
                return

            if self.inline.init_complete:
                await self.inline.form(
                    text=self.strings("choose_loglevel"),
                    reply_markup=[
                        [
                            {
                                "text": "🚨 Critical",
                                "callback": self.setloglevelcmd,
                                "args": (50,),
                            },
                            {
                                "text": "🚫 Error",
                                "callback": self.setloglevelcmd,
                                "args": (40,),
                            },
                        ],
                        [
                            {
                                "text": "⚠️ Warning",
                                "callback": self.setloglevelcmd,
                                "args": (30,),
                            },
                            {
                                "text": "ℹ️ Info",
                                "callback": self.setloglevelcmd,
                                "args": (20,),
                            },
                        ],
                        [
                            {
                                "text": "🧑‍💻 Debug",
                                "callback": self.setloglevelcmd,
                                "args": (10,),
                            },
                            {
                                "text": "👁 All",
                                "callback": self.setloglevelcmd,
                                "args": (0,),
                            },
                        ],
                        [{"text": "🚫 Cancel", "callback": self.cancel}],
                    ],
                    message=message,
                )
            else:
                await utils.answer(message, self.strings("loglevel_invalid"))
            return

        await self._apply_loglevel(lvl)
        named = logging._levelToName.get(lvl, str(lvl))  # skipcq: PYL-W0212
        text = self.strings("loglevel_set").format(named)
        if isinstance(message, Message):
            await utils.answer(message, text)
        else:
            await message.edit(text)

    @loader.owner
    async def suspendcmd(self, message: Message) -> None:
        """.suspend <time>
        Suspends the bot for N seconds"""
        try:
            time_sleep = float(utils.get_args_raw(message))
            await utils.answer(
                message, self.strings("suspended", message).format(str(time_sleep))
            )
            time.sleep(time_sleep)
        except ValueError:
            await utils.answer(message, self.strings("suspend_invalid_time", message))

    async def pingcmd(self, message: Message) -> None:
        """Test your userbot ping"""
        start = time.perf_counter_ns()
        message = await utils.answer(message, "<code>Ping checking...</code>")
        end = time.perf_counter_ns()

        if isinstance(message, (list, tuple, set)):
            message = message[0]

        ms = (end - start) * 0.000001

        await utils.answer(message, self.strings("results_ping").format(round(ms, 3)))

    async def client_ready(self, client, db) -> None:
        self._client = client
        self._db = db
