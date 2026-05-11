"""
█ █ ▀ █▄▀ ▄▀█ █▀█ ▀    ▄▀█ ▀█▀ ▄▀█ █▀▄▀█ ▄▀█
█▀█ █ █ █ █▀█ █▀▄ █ ▄  █▀█  █  █▀█ █ ▀ █ █▀█

Copyright 2022 t.me/hikariatama
Licensed under the GNU GPLv3
"""

import itertools
import logging
from traceback import format_exc
from types import ModuleType
from typing import Any

import telethon
from meval import meval
from telethon.tl import functions as tl_functions
from telethon.tl import types as tl_types
from telethon.tl.custom import Message

from .. import loader, main, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)


class FakeDbException(Exception):
    pass


class FakeDb:
    def __getattr__(self, name):
        # Pass-through dunders so meval/repr introspection doesn't trigger
        # the "permission required" prompt accidentally.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        raise FakeDbException("Database read-write permission required")


@loader.tds
class PythonMod(loader.Module):
    """Evaluates python code"""

    strings = {
        "name": "Python",
        "eval": "🎬 <b>Code:</b>\n<code>{}</code>\n🪄 <b>Result:</b>\n<code>{}</code>",
        "err": "🎬 <b>Code:</b>\n<code>{}</code>\n\n🚫 <b>Error:</b>\n<code>{}</code>",
        "db_permission": (
            "⚠️ <b>Do not use </b><code>db.set</code><b>,"
            "</b><code>db.get</code><b> and other db operations."
            "You have core modules to control anything you want</b>\n\n"
            "<i>Theses commands may <b><u>crash</u></b> your userbot "
            "or even make it <b><u>unusable</u></b>!</i>\n\n"
            "<i>If you issue any errors after allowing this option "
            "<b><u>you will not get any help in support chat</u></b>!</i>"
        ),
    }

    def lookup(self, modname: str):
        return next(
            (
                mod
                for mod in self.allmodules.modules
                if mod.name.lower() == modname.lower()
            ),
            False,
        )

    @loader.owner
    async def ecmd(self, message: Message) -> None:
        """Evaluates python code"""
        client: Any = self.ctx.client
        phone = str(getattr(client, "phone", None) or "")
        code = utils.get_args_raw(message)
        try:
            it = await meval(code, globals(), **await self.getattrs(message))
        except FakeDbException:
            await self.inline.form(
                self.tr("db_permission"),
                message=message,
                reply_markup=[
                    [
                        {"text": "✅ Allow", "callback": self.inline__allow},
                        {"text": "🚫 Cancel", "callback": self.inline__close},
                    ]
                ],
            )
            return
        except Exception:
            exc = format_exc()
            if phone:
                exc = exc.replace(phone, "📵")
            await utils.answer(
                message,
                self.tr("err", message).format(
                    utils.escape_html(code), utils.escape_html(exc)
                ),
            )
            return

        ret = self.tr("eval", message).format(
            utils.escape_html(code), utils.escape_html(str(it))
        )
        if phone:
            ret = ret.replace(phone, "📵")
        await utils.answer(message, ret)

    # .eval is a historical alias of .e — share the implementation directly.
    evalcmd = ecmd

    async def inline__close(self, call: InlineCall) -> None:
        await call.answer("Operation cancelled")
        await call.delete()

    async def inline__allow(self, call: InlineCall) -> None:
        await call.answer("Now you can access db through .e command", show_alert=True)
        self.ctx.db.set(main.__name__, "enable_db_eval", True)
        await call.delete()

    async def getattrs(self, message):
        reply = await message.get_reply_message()
        return {
            **{
                "message": message,
                "client": self.ctx.client,
                "reply": reply,
                "r": reply,
                **self.get_sub(tl_types),
                **self.get_sub(tl_functions),
                "event": message,
                "chat": message.to_id,
                "telethon": telethon,
                "utils": utils,
                "main": main,
                "f": tl_functions,
                "c": self.ctx.client,
                "m": message,
                "loader": loader,
                "lookup": self.lookup,
                "self": self,
            },
            **(
                {
                    "db": self.ctx.db,
                }
                if self.ctx.db.get(main.__name__, "enable_db_eval", False)
                else {
                    "db": FakeDb(),
                }
            ),
        }

    def get_sub(self, it, _depth: int = 1) -> dict:
        """Get all callable capitalised objects in an object recursively, ignoring _*"""
        return {
            **dict(
                filter(
                    lambda x: x[0][0] != "_"
                    and x[0][0].upper() == x[0][0]
                    and callable(x[1]),
                    it.__dict__.items(),
                )
            ),
            **dict(
                itertools.chain.from_iterable(
                    [
                        self.get_sub(y[1], _depth + 1).items()
                        for y in filter(
                            lambda x: x[0][0] != "_"
                            and isinstance(x[1], ModuleType)
                            and x[1] != it
                            and x[1].__package__.rsplit(".", _depth)[0]
                            == "telethon.tl",
                            it.__dict__.items(),
                        )
                    ]
                )
            ),
        }
