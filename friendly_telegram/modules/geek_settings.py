"""
█ █ ▀ █▄▀ ▄▀█ █▀█ ▀    ▄▀█ ▀█▀ ▄▀█ █▀▄▀█ ▄▀█
█▀█ █ █ █ █▀█ █▀▄ █ ▄  █▀█  █  █▀█ █ ▀ █ █▀█

Copyright 2022 t.me/hikariatama
Licensed under the GNU GPLv3
"""

# meta pic: https://img.icons8.com/pastel-glyph/344/sun-glasses--v2.png
# scope: inline
# scope: geektg_only
# meta developer: @hikariatama

import logging

from telethon.tl.types import Message

from .. import loader, main, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)


@loader.tds
class GeekSettingsMod(loader.Module):
    """Advanced settings for GeekTG"""

    strings = {
        "name": "GeekSettings",
        "watchers": "👀 <b>Watchers:</b>\n\n<b>{}</b>",
        "mod404": "🚫 <b>Watcher {} not found</b>",
        "already_disabled": "👀 <b>Watcher {} is already disabled</b>",
        "disabled": "👀 <b>Watcher {} is now <u>disabled</u></b>",
        "enabled": "👀 <b>Watcher {} is now <u>enabled</u></b>",
        "args": "🚫 <b>You need to specify watcher name</b>",
        "user_nn": "🔰 <b>NoNick for this user is now {}</b>",
        "no_cmd": "🔰 <b>Please, specify command to toggle NoNick for</b>",
        "cmd_nn": "🔰 <b>NoNick for </b><code>{}</code><b> is now {}</b>",
        "cmd404": "🔰 <b>Command not found</b>",
        "inline_settings": "⚙️ <b>Here you can configure your GeekTG settings</b>",
        "confirm_update": "🪂 <b>Please, confirm that you want to update. Your userbot will be restarted</b>",
        "confirm_restart": "🔄 <b>Please, confirm that you want to restart</b>",
    }

    def get_watchers(self) -> tuple:
        return [
            str(_.__self__.__class__.strings["name"])
            for _ in self.allmodules.watchers
            if _.__self__.__class__.strings is not None
        ], self.ctx.db.get(main.__name__, "disabled_watchers", {})

    async def watcherscmd(self, message: Message) -> None:
        """List current watchers"""
        watchers, disabled_watchers = self.get_watchers()
        watchers = [
            f"♻️ {_}" for _ in watchers if _ not in list(disabled_watchers.keys())
        ]
        watchers += [f"💢 {k} {v}" for k, v in disabled_watchers.items()]
        await utils.answer(
            message, self.strings("watchers").format("\n".join(watchers))
        )

    async def watcherblcmd(self, message: Message) -> None:
        """<module> - Toggle watcher in current chat"""
        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, self.strings("args"))

        watchers, disabled_watchers = self.get_watchers()

        if args.lower() not in [_.lower() for _ in watchers]:
            return await utils.answer(message, self.strings("mod404").format(args))

        args = [_ for _ in watchers if _.lower() == args.lower()][0]

        current_bl = [
            v for k, v in disabled_watchers.items() if k.lower() == args.lower()
        ]
        current_bl = current_bl[0] if current_bl else []

        chat = utils.get_chat_id(message)
        if chat not in current_bl:
            if args in disabled_watchers:
                for k, _ in disabled_watchers.items():
                    if k.lower() == args.lower():
                        disabled_watchers[k].append(chat)
                        break
            else:
                disabled_watchers[args] = [chat]

            await utils.answer(
                message,
                self.strings("disabled").format(args) + " <b>in current chat</b>",
            )
        else:
            for k in disabled_watchers.copy():
                if k.lower() == args.lower():
                    disabled_watchers[k].remove(chat)
                    if not disabled_watchers[k]:
                        del disabled_watchers[k]
                    break

            await utils.answer(
                message,
                self.strings("enabled").format(args) + " <b>in current chat</b>",
            )

        self.ctx.db.set(main.__name__, "disabled_watchers", disabled_watchers)

    async def watchercmd(self, message: Message) -> None:
        """<module> - Toggle global watcher rules
        Args:
        [-c - only in chats]
        [-p - only in pm]
        [-o - only out]
        [-i - only incoming]"""
        raw = utils.get_args_raw(message)
        if not raw:
            return await utils.answer(message, self.strings("args"))

        # Tokenize so flags like ``-counter`` don't accidentally match ``-c``.
        tokens = raw.split()
        flags = {"-c", "-p", "-o", "-i"}
        chats = "-c" in tokens
        pm = "-p" in tokens
        out = "-o" in tokens
        incoming = "-i" in tokens
        rest = [t for t in tokens if t not in flags]
        args = " ".join(rest).strip()
        if not args:
            return await utils.answer(message, self.strings("args"))

        if chats and pm:
            pm = False
        if out and incoming:
            incoming = False

        watchers, disabled_watchers = self.get_watchers()

        if args.lower() not in [_.lower() for _ in watchers]:
            return await utils.answer(message, self.strings("mod404").format(args))

        args = [_ for _ in watchers if _.lower() == args.lower()][0]

        if chats or pm or out or incoming:
            disabled_watchers[args] = [
                *(["only_chats"] if chats else []),
                *(["only_pm"] if pm else []),
                *(["out"] if out else []),
                *(["in"] if incoming else []),
            ]
            self.ctx.db.set(main.__name__, "disabled_watchers", disabled_watchers)
            await utils.answer(
                message,
                self.strings("enabled").format(args)
                + f" (<code>{disabled_watchers[args]}</code>)",
            )
            return

        if args in disabled_watchers and "*" in disabled_watchers[args]:
            await utils.answer(message, self.strings("enabled").format(args))
            del disabled_watchers[args]
            self.ctx.db.set(main.__name__, "disabled_watchers", disabled_watchers)
            return

        disabled_watchers[args] = ["*"]
        self.ctx.db.set(main.__name__, "disabled_watchers", disabled_watchers)
        await utils.answer(message, self.strings("disabled").format(args))

    async def nonickusercmd(self, message: Message) -> None:
        """<reply> - Allow this user to run commands without nickname"""
        reply = await message.get_reply_message()
        u = reply.sender_id

        nn = self.ctx.db.get(main.__name__, "nonickusers", [])
        if u in nn:
            nn = [x for x in nn if x != u]
            await utils.answer(message, self.strings("user_nn").format("off"))
        else:
            nn.append(u)
            await utils.answer(message, self.strings("user_nn").format("on"))

        self.ctx.db.set(main.__name__, "nonickusers", nn)

    async def nonickcmdcmd(self, message: Message) -> None:
        """<command> - Allow command to be executed without nickname"""
        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, self.strings("no_cmd"))

        if args not in self.allmodules.commands:
            return await utils.answer(message, self.strings("cmd404"))

        prefix = self.ctx.db.get(main.__name__, "command_prefix", ".")
        nn = self.ctx.db.get(main.__name__, "nonickcmds", [])
        if args in nn:
            nn = [x for x in nn if x != args]
            state = "off"
        else:
            nn.append(args)
            state = "on"

        await utils.answer(message, self.strings("cmd_nn").format(prefix + args, state))
        self.ctx.db.set(main.__name__, "nonickcmds", nn)

    async def inline__setting(self, call: InlineCall, key: str, state: bool) -> None:
        self.ctx.db.set(main.__name__, key, state)

        if (
            key == "no_nickname"
            and state
            and self.ctx.db.get(main.__name__, "command_prefix", ".") == "."
        ):
            await call.answer(
                "Warning! You enabled NoNick with default prefix! You may get muted in GeekTG chats. Change prefix or disable NoNick!",
                show_alert=True,
            )
        else:
            await call.answer("Configuration value saved!")

        await call.edit(
            self.strings("inline_settings"), reply_markup=self._get_settings_markup()
        )

    async def inline__close(self, call: InlineCall) -> None:
        await call.delete()

    async def _confirm_action(
        self,
        call: InlineCall,
        *,
        confirm_required: bool,
        confirm_text_key: str,
        accept_label: str,
        accept_callback,
        running_text: str,
        command: str,
    ) -> None:
        """Two-step confirm flow shared by .update and .restart inline buttons."""
        if confirm_required:
            await call.edit(
                self.strings(confirm_text_key),
                reply_markup=[
                    [
                        {"text": accept_label, "callback": accept_callback},
                        {"text": "🚫 Cancel", "callback": self.inline__close},
                    ]
                ],
            )
            return

        await call.answer(running_text, show_alert=True)
        await call.delete()
        m = await self.ctx.client.send_message("me", command)
        await self.allmodules.commands[command.lstrip(".")](m)

    async def inline__update(
        self, call: InlineCall, confirm_required: bool = False
    ) -> None:
        await self._confirm_action(
            call,
            confirm_required=confirm_required,
            confirm_text_key="confirm_update",
            accept_label="🪂 Update",
            accept_callback=self.inline__update,
            running_text="You userbot is being updated...",
            command=".update",
        )

    async def inline__restart(
        self, call: InlineCall, confirm_required: bool = False
    ) -> None:
        await self._confirm_action(
            call,
            confirm_required=confirm_required,
            confirm_text_key="confirm_restart",
            accept_label="🔄 Restart",
            accept_callback=self.inline__restart,
            running_text="You userbot is being restarted...",
            command=".restart",
        )

    def _toggle_button(self, label: str, key: str, default: bool) -> dict:
        """A 2-state inline button that flips db[main][key]."""
        on = self.ctx.db.get(main.__name__, key, default)
        return {
            "text": f"{'✅' if on else '🚫'} {label}",
            "callback": self.inline__setting,
            "args": (key, not on),
        }

    def _get_settings_markup(self) -> list:
        return [
            [
                self._toggle_button("NoNick", "no_nickname", True),
                self._toggle_button("Grep", "grep", True),
                self._toggle_button("InlineLogs", "inlinelogs", True),
            ],
            [
                {
                    "text": "🔄 Restart",
                    "callback": self.inline__restart,
                    "args": (True,),
                },
                {
                    "text": "🪂 Update",
                    "callback": self.inline__update,
                    "args": (True,),
                },
            ],
            [{"text": "😌 Close menu", "callback": self.inline__close}],
        ]

    @loader.owner
    async def settingscmd(self, message: Message) -> None:
        """Show settings menu"""
        await self.inline.form(
            self.strings("inline_settings"),
            message=message,
            reply_markup=self._get_settings_markup(),
        )
