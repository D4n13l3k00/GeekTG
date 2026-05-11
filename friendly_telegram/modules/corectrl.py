#    Friendly Telegram (telegram userbot)
#    Copyright (C) 2018-2022 The Authors

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

#    Modded by GeekTG Team

import os
from typing import Optional, Union

from telethon.tl.custom import Message
from telethon.tl.types import Channel

from .. import loader, main, utils


@loader.tds
class CoreMod(loader.Module):
    """Control core userbot settings"""

    strings = {
        "name": "Settings",
        "too_many_args": "🚫 <b>Too many args</b>",
        "blacklisted": "✅ <b>Chat {} blacklisted from userbot</b>",
        "unblacklisted": "✅ <b>Chat {} unblacklisted from userbot</b>",
        "user_blacklisted": "✅ <b>User {} blacklisted from userbot</b>",
        "user_unblacklisted": "✅ <b>User {} unblacklisted from userbot</b>",
        "what_prefix": "❓ <b>What should the prefix be set to?</b>",
        "prefix_incorrect": "🚫 <b>Prefix must be one symbol in length</b>",
        "prefix_set": (
            "✅ <b>Command prefix updated.\n"
            "Type</b> <code>{newprefix}setprefix {oldprefix}</code>"
            "<b>to change it back</b>"
        ),
        "alias_created": "✅ <b>Alias created. Access it with</b> <code>{}</code>",
        "aliases": "📋 <b>Aliases:</b>\n",
        "no_command": "🚫 <b>Command</b> <code>{}</code> <b>does not exist</b>",
        "alias_args": "🚫 <b>You must provide a command and the alias for it</b>",
        "delalias_args": "🚫 <b>You must provide the alias name</b>",
        "alias_removed": "✅ <b>Alias <code>{}</code> removed.</b>",
        "no_alias": "🚫 <b>Alias <code>{}</code> does not exist</b>",
        "who_to_unblacklist": "🚫 <b>Specify a user (id or reply)</b>",
        "no_pack": "❓ <b>What translation pack should be added?</b>",
        "bad_pack": "🚫 <b>Invalid translation pack specified</b>",
        "trnsl_saved": "✅ <b>Translation pack added</b>",
        "packs_cleared": "✅ <b>Translations cleared</b>",
        "lang_set": "✅ <b>Language changed</b>",
        "db_cleared": "✅ <b>Database cleared</b>",
        "geek": (
            "🕶 <b>Congrats! You are Geek!</b>\n\n"
            "<b>GeekTG version: {}.{}.{}</b>\n"
            "<b>Branch: master</b>"
        ),
        "geek_beta": (
            "🕶 <b>Congrats! You are Geek!</b>\n\n"
            "<b>GeekTG version: {}.{}.{}beta</b>\n"
            "<b>Branch: beta</b>\n\n"
            "<i>🔮 You're using the unstable branch (<b>beta</b>). "
            "You receive fresh but untested updates. "
            "Report any bugs to @chat_ftg or @hikari_chat</i>"
        ),
        "geek_alpha": (
            "🕶 <b>Congrats! You are Geek!</b>\n\n"
            "<b>GeekTG version: {}.{}.{}alpha</b>\n"
            "<b>Branch: alpha</b>\n\n"
            "<i>🔮 You're using <b><u>very</u></b> unstable branch (<b>alpha</b>). "
            "You receive fresh but untested updates. "
            "You <b><u>can't ask for help, only report bugs</u></b></i>"
        ),
    }

    async def blacklistcommon(self, message: Message) -> Optional[Union[int, str]]:
        args = utils.get_args(message)

        if len(args) > 2:
            await utils.answer(message, self.tr("too_many_args", message))
            return None

        chatid: Optional[int] = None
        module: Optional[str] = None

        if args:
            try:
                chatid = int(args[0])
            except ValueError:
                module = args[0]

        if len(args) == 2:
            module = args[1]

        if chatid is None:
            chatid = utils.get_chat_id(message)

        module = self.allmodules.get_classname(module)
        return f"{chatid}.{module}" if module else chatid

    async def ftgvercmd(self, message: Message) -> None:
        """Get GeekTG version"""
        ver = getattr(main, "__version__", None) or (0, 0, 0)

        try:
            branch = (
                os.popen("git rev-parse --abbrev-ref HEAD")  # noqa: S605, S607
                .read()
                .strip()
            )
        except OSError:
            branch = ""

        if "beta" in branch:
            key = "geek_beta"
        elif "alpha" in branch:
            key = "geek_alpha"
        else:
            key = "geek"
        await utils.answer(message, self.tr(key).format(*ver))

    async def blacklistcmd(self, message: Message) -> None:
        """.blacklist [id]
        Blacklist the bot from operating somewhere"""
        chatid = await self.blacklistcommon(message)

        self.ctx.db.set(
            main.__name__,
            "blacklist_chats",
            self.ctx.db.get(main.__name__, "blacklist_chats", []) + [chatid],
        )

        await utils.answer(message, self.tr("blacklisted", message).format(chatid))

    async def unblacklistcmd(self, message: Message) -> None:
        """.unblacklist [id]
        Unblacklist the bot from operating somewhere"""
        chatid = await self.blacklistcommon(message)

        self.ctx.db.set(
            main.__name__,
            "blacklist_chats",
            list(set(self.ctx.db.get(main.__name__, "blacklist_chats", [])) - {chatid}),
        )

        await utils.answer(message, self.tr("unblacklisted", message).format(chatid))

    async def getuser(self, message: Message) -> Optional[int]:
        try:
            return int((utils.get_args(message))[0])
        except (ValueError, IndexError):
            reply = await message.get_reply_message()
            if reply:
                return reply.sender_id
            if message.is_private:
                to_id = getattr(message, "to_id", None)
                user_id = getattr(to_id, "user_id", None)
                if user_id is not None:
                    return user_id
            await utils.answer(message, self.tr("who_to_unblacklist", message))
            return None

    async def blacklistusercmd(self, message: Message) -> None:
        """.blacklistuser [id]
        Prevent this user from running any commands"""
        user = await self.getuser(message)

        self.ctx.db.set(
            main.__name__,
            "blacklist_users",
            self.ctx.db.get(main.__name__, "blacklist_users", []) + [user],
        )

        await utils.answer(message, self.tr("user_blacklisted", message).format(user))

    async def unblacklistusercmd(self, message: Message) -> None:
        """.unblacklistuser [id]
        Allow this user to run permitted commands"""
        user = await self.getuser(message)

        self.ctx.db.set(
            main.__name__,
            "blacklist_users",
            list(set(self.ctx.db.get(main.__name__, "blacklist_users", [])) - {user}),
        )

        await utils.answer(message, self.tr("user_unblacklisted", message).format(user))

    @loader.owner
    async def setprefixcmd(self, message: Message) -> None:
        """Sets command prefix"""
        args = utils.get_args_raw(message)

        if not args:
            await utils.answer(message, self.tr("what_prefix", message))
            return

        if len(args) != 1:
            await utils.answer(message, self.tr("prefix_incorrect", message))
            return

        oldprefix = self.ctx.db.get(main.__name__, "command_prefix", ".")
        # Save the single character only — the validation above guarantees
        # ``args`` is one char, but being explicit guards against future drift.
        self.ctx.db.set(main.__name__, "command_prefix", args[0])
        await utils.answer(
            message,
            self.tr("prefix_set", message).format(
                newprefix=utils.escape_html(args[0]),
                oldprefix=utils.escape_html(oldprefix),
            ),
        )

    @loader.owner
    async def aliasescmd(self, message: Message) -> None:
        """Print all your aliases"""
        aliases = self.allmodules.aliases
        body = "\n".join(
            f"\n{utils.escape_html(k)}: {utils.escape_html(v)}"
            for k, v in aliases.items()
        )
        await utils.answer(message, self.tr("aliases", message) + body)

    @loader.owner
    async def addaliascmd(self, message: Message) -> None:
        """Set an alias for a command"""
        args = utils.get_args(message)

        if len(args) != 2:
            await utils.answer(message, self.tr("alias_args", message))
            return

        alias, cmd = args
        ret = self.allmodules.add_alias(alias, cmd)

        if ret:
            current = self.ctx.db.get(__name__, "aliases", {}) or {}
            current[alias] = cmd
            self.ctx.db.set(__name__, "aliases", current)
            await utils.answer(
                message,
                self.tr("alias_created", message).format(utils.escape_html(alias)),
            )
        else:
            await utils.answer(
                message,
                self.tr("no_command", message).format(utils.escape_html(cmd)),
            )

    @loader.owner
    async def delaliascmd(self, message: Message) -> None:
        """Remove an alias for a command"""
        args = utils.get_args(message)

        if len(args) != 1:
            await utils.answer(message, self.tr("delalias_args", message))
            return

        alias = args[0]
        ret = self.allmodules.remove_alias(alias)

        if ret:
            current = self.ctx.db.get(__name__, "aliases", {}) or {}
            current.pop(alias, None)
            self.ctx.db.set(__name__, "aliases", current)
            await utils.answer(
                message,
                self.tr("alias_removed", message).format(utils.escape_html(alias)),
            )
        else:
            await utils.answer(
                message,
                self.tr("no_alias", message).format(utils.escape_html(alias)),
            )

    async def addtrnslcmd(self, message: Message) -> None:
        """Add a translation pack
        .addtrnsl <pack>
        Restart required after use"""
        args = utils.get_args(message)

        if len(args) != 1:
            await utils.answer(message, self.tr("no_pack", message))
            return

        pack = args[0]
        if str(pack).isdigit():
            pack = int(pack)

        try:
            pack = await self.ctx.client.get_entity(pack)
        except ValueError:
            await utils.answer(message, self.tr("bad_pack", message))
            return

        if isinstance(pack, Channel) and not pack.megagroup:
            self.ctx.db.setdefault(main.__name__, {}).setdefault(
                "langpacks", []
            ).append(pack.id)
            self.ctx.db.save()
            await utils.answer(message, self.tr("trnsl_saved", message))
        else:
            await utils.answer(message, self.tr("bad_pack", message))

    async def cleartrnslcmd(self, message: Message) -> None:
        """Remove all translation packs"""
        self.ctx.db.set(main.__name__, "langpacks", [])
        await utils.answer(message, self.tr("packs_cleared", message))

    async def setlangcmd(self, message: Message) -> None:
        """Change the preferred language used for translations
        Specify the language as space separated list of
        ISO 639-1 language codes in order of preference
        With no parameters, all translations are disabled
        Restart required after use"""
        langs = utils.get_args(message)
        self.ctx.db.set(main.__name__, "language", langs)
        await utils.answer(message, self.tr("lang_set", message))

    @loader.owner
    async def cleardbcmd(self, message: Message) -> None:
        """Clears the entire database, effectively performing a factory reset"""
        self.ctx.db.clear()
        self.ctx.db.save()
        await utils.answer(message, self.tr("db_cleared", message))

    async def _client_ready2(self, client, db):  # skicpq: PYL-W0613
        ret = {
            alias: cmd
            for alias, cmd in db.get(__name__, "aliases", {}).items()
            if self.allmodules.add_alias(alias, cmd)
        }

        db.set(__name__, "aliases", ret)
