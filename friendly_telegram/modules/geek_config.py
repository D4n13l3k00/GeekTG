"""
█ █ ▀ █▄▀ ▄▀█ █▀█ ▀    ▄▀█ ▀█▀ ▄▀█ █▀▄▀█ ▄▀█
█▀█ █ █ █ █▀█ █▀▄ █ ▄  █▀█  █  █▀█ █ ▀ █ █▀█

Copyright 2022 t.me/hikariatama
Licensed under the GNU GPLv3
"""

# scope: inline_content

import ast
import logging
from typing import Iterator, List, Sequence, TypeVar, Union

from telethon.tl.custom import Message

from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

T = TypeVar("T")


def chunks(lst: Sequence[T], n: int) -> Iterator[List[T]]:
    for i in range(0, len(lst), n):
        yield list(lst[i : i + n])


blacklist = [
    "Raphielgang Configuration Placeholder",
    "Uniborg configuration placeholder",
    "Logger",
]


@loader.tds
class GeekConfigMod(loader.Module):
    """Interactive configurator for GeekTG"""

    strings = {
        "name": "GeekConfig",
        "configure": "🎚 <b>Here you can configure your modules' configs</b>",
        "configuring_mod": "🎚 <b>Choose config option for mod</b> <code>{}</code>",
        "configuring_option": (
            "🎚 <b>Configuring option </b><code>{}</code><b> of mod </b><code>{}</code>\n"
            "<i>ℹ️ {}</i>\n\n"
            "<b>Default: </b><code>{}</code>\n\n"
            "<b>Current: </b><code>{}</code>"
        ),
        "option_saved": (
            "🎚 <b>Configuring option </b><code>{}</code><b>"
            "of mod </b><code>{}</code><b> saved!</b>\n"
            "<b>Current: </b><code>{}</code>"
        ),
    }

    async def client_ready(self, client, db) -> None:
        self._bot_id = (await self.inline.bot.get_me()).id

    def _find_module(self, name: str):
        return next(
            (m for m in self.allmodules.modules if m.tr("name") == name),
            None,
        )

    @staticmethod
    async def inline__close(call: InlineCall) -> None:  # noqa
        await call.delete()

    async def inline__set_config(
        self,
        call: InlineCall,
        query: str,
        mod: str,
        option: str,
        inline_message_id: str,
    ) -> None:  # noqa
        module = self._find_module(mod)
        if module is not None:
            module.config[option] = query
            stored = query
            if query:
                try:
                    stored = ast.literal_eval(query)
                except (ValueError, SyntaxError):
                    pass
                self.ctx.db.setdefault(module.__module__, {}).setdefault(
                    "__config__", {}
                )[option] = stored
            else:
                self.ctx.db.setdefault(module.__module__, {}).setdefault(
                    "__config__", {}
                ).pop(option, None)

            self.allmodules.send_config_one(module, self.ctx.db, skip_hook=True)
            self.ctx.db.save()
            display = stored
        else:
            display = query

        await call.edit(
            self.tr("option_saved").format(
                utils.escape_html(option),
                utils.escape_html(mod),
                utils.escape_html(str(display)),
            ),
            reply_markup=[
                [
                    {
                        "text": "👈 Back",
                        "callback": self.inline__configure,
                        "args": (mod,),
                    },
                    {
                        "text": "🚫 Close",
                        "callback": self.inline__close,
                        "style": "danger",
                    },
                ]
            ],
            inline_message_id=inline_message_id,
        )

    async def inline__configure_option(
        self, call: InlineCall, mod: str, config_opt: str
    ) -> None:  # noqa
        module = self._find_module(mod)
        if module is None:
            return
        await call.edit(
            self.tr("configuring_option").format(
                utils.escape_html(config_opt),
                utils.escape_html(mod),
                utils.escape_html(module.config.getdoc(config_opt)),
                utils.escape_html(str(module.config.getdef(config_opt))),
                utils.escape_html(str(module.config[config_opt])),
            ),
            reply_markup=[
                [
                    {
                        "text": "✍️ Enter value",
                        "input": "✍️ Enter new configuration value for this option",  # noqa: E501
                        "handler": self.inline__set_config,
                        "args": (mod, config_opt, call.inline_message_id),
                        "style": "primary",
                    }
                ],
                [
                    {
                        "text": "👈 Back",
                        "callback": self.inline__configure,
                        "args": (mod,),
                    },
                    {
                        "text": "🚫 Close",
                        "callback": self.inline__close,
                        "style": "danger",
                    },
                ],
            ],
        )

    async def inline__configure(self, call: InlineCall, mod: str) -> None:  # noqa
        module = self._find_module(mod)
        btns = (
            [
                {
                    "text": param,
                    "callback": self.inline__configure_option,
                    "args": (mod, param),
                }
                for param in module.config
            ]
            if module is not None
            else []
        )

        await call.edit(
            self.tr("configuring_mod").format(utils.escape_html(mod)),
            reply_markup=list(chunks(btns, 2))
            + [
                [
                    {
                        "text": "👈 Back",
                        "callback": self.inline__global_config,
                    },
                    {
                        "text": "🚫 Close",
                        "callback": self.inline__close,
                        "style": "danger",
                    },
                ]
            ],
        )

    async def inline__global_config(
        self, call: Union[Message, InlineCall]
    ) -> None:  # noqa
        to_config = [
            mod.tr("name")
            for mod in self.allmodules.modules
            if hasattr(mod, "config") and mod.tr("name") not in blacklist
        ]
        kb = [
            [
                {"text": btn, "callback": self.inline__configure, "args": (btn,)}
                for btn in mod_row
            ]
            for mod_row in chunks(to_config, 3)
        ]
        kb += [
            [
                {
                    "text": "🚫 Close",
                    "callback": self.inline__close,
                }
            ]
        ]

        if isinstance(call, Message):
            await self.inline.form(self.tr("configure"), reply_markup=kb, message=call)
        else:
            await call.edit(self.tr("configure"), reply_markup=kb)

    async def configcmd(self, message: Message) -> None:
        """Configure modules"""
        await self.inline__global_config(message)

    async def watcher(self, message: Message) -> None:
        if (
            not getattr(message, "out", False)
            or not getattr(message, "via_bot_id", False)
            or message.via_bot_id != self._bot_id
            or "This message is gonna be deleted..."
            not in getattr(message, "raw_text", "")
        ):
            return

        await message.delete()
