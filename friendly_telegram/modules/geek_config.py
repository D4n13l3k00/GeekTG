"""
█ █ ▀ █▄▀ ▄▀█ █▀█ ▀    ▄▀█ ▀█▀ ▄▀█ █▀▄▀█ ▄▀█
█▀█ █ █ █ █▀█ █▀▄ █ ▄  █▀█  █  █▀█ █ ▀ █ █▀█

Copyright 2022 t.me/hikariatama
Licensed under the GNU GPLv3
"""

# scope: inline_content

import ast
import logging
from typing import List, Union

from telethon.tl.types import Message

from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)


def chunks(lst: Union[list, tuple, set], n: int) -> List[list]:
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


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

    def get(self, *args) -> dict:
        return self.ctx.db.get(self.strings["name"], *args)

    def set(self, *args) -> None:
        return self.ctx.db.set(self.strings["name"], *args)

    async def client_ready(self, client, db) -> None:
        self._bot_id = (await self.inline.bot.get_me()).id
        self._forms = {}

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
        for module in self.allmodules.modules:
            if module.strings("name") == mod:
                module.config[option] = query
                if query:
                    try:
                        query = ast.literal_eval(query)
                    except (ValueError, SyntaxError):
                        pass
                    self.ctx.db.setdefault(module.__module__, {}).setdefault(
                        "__config__", {}
                    )[option] = query
                else:
                    try:
                        del self.ctx.db.setdefault(module.__module__, {}).setdefault(
                            "__config__", {}
                        )[option]
                    except KeyError:
                        pass

                self.allmodules.send_config_one(module, self.ctx.db, skip_hook=True)
                self.ctx.db.save()

        await call.edit(
            self.strings("option_saved").format(mod, option, query),
            reply_markup=[
                [
                    {
                        "text": "👈 Back",
                        "callback": self.inline__configure,
                        "args": (mod,),
                    },
                    {"text": "🚫 Close", "callback": self.inline__close},
                ]
            ],
            inline_message_id=inline_message_id,
        )

    async def inline__configure_option(
        self, call: InlineCall, mod: str, config_opt: str
    ) -> None:  # noqa
        for module in self.allmodules.modules:
            if module.strings("name") == mod:
                await call.edit(
                    self.strings("configuring_option").format(
                        utils.escape_html(config_opt),
                        utils.escape_html(mod),
                        utils.escape_html(module.config.getdoc(config_opt)),
                        utils.escape_html(module.config.getdef(config_opt)),
                        utils.escape_html(module.config[config_opt]),
                    ),
                    reply_markup=[
                        [
                            {
                                "text": "✍️ Enter value",
                                "input": "✍️ Enter new configuration value for this option",  # noqa: E501
                                "handler": self.inline__set_config,
                                "args": (mod, config_opt, call.inline_message_id),
                            }
                        ],
                        [
                            {
                                "text": "👈 Back",
                                "callback": self.inline__configure,
                                "args": (mod,),
                            },
                            {"text": "🚫 Close", "callback": self.inline__close},
                        ],
                    ],
                )

    async def inline__configure(self, call: InlineCall, mod: str) -> None:  # noqa
        btns = []
        for module in self.allmodules.modules:
            if module.strings("name") == mod:
                for param in module.config:
                    btns += [
                        {
                            "text": param,
                            "callback": self.inline__configure_option,
                            "args": (mod, param),
                        }
                    ]

        await call.edit(
            self.strings("configuring_mod").format(utils.escape_html(mod)),
            reply_markup=list(chunks(btns, 2))
            + [
                [
                    {"text": "👈 Back", "callback": self.inline__global_config},
                    {"text": "🚫 Close", "callback": self.inline__close},
                ]
            ],
        )

    async def inline__global_config(
        self, call: Union[Message, InlineCall]
    ) -> None:  # noqa
        to_config = [
            mod.strings("name")
            for mod in self.allmodules.modules
            if hasattr(mod, "config") and mod.strings("name") not in blacklist
        ]
        kb = []
        for mod_row in chunks(to_config, 3):
            row = [
                {"text": btn, "callback": self.inline__configure, "args": (btn,)}
                for btn in mod_row
            ]
            kb += [row]

        kb += [[{"text": "🚫 Close", "callback": self.inline__close}]]

        if isinstance(call, Message):
            await self.inline.form(
                self.strings("configure"), reply_markup=kb, message=call
            )
        else:
            await call.edit(self.strings("configure"), reply_markup=kb)

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
