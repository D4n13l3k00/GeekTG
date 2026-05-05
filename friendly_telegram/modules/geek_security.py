"""
█ █ ▀ █▄▀ ▄▀█ █▀█ ▀    ▄▀█ ▀█▀ ▄▀█ █▀▄▀█ ▄▀█
█▀█ █ █ █ █▀█ █▀▄ █ ▄  █▀█  █  █▀█ █ ▀ █ █▀█
Copyright 2022 t.me/hikariatama
Licensed under the GNU GPLv3
"""

# meta pic: https://img.icons8.com/stickers/100/000000/enter-pin.png
# scope: inline

import logging
from types import FunctionType
from typing import List, Union

from telethon.tl.types import Message, PeerUser, User
from telethon.utils import get_display_name

from .. import loader, main, security, utils
from ..inline.types import InlineCall
from ..security import (
    DEFAULT_PERMISSIONS,
    GROUP_ADMIN,
    GROUP_ADMIN_ADD_ADMINS,
    GROUP_ADMIN_BAN_USERS,
    GROUP_ADMIN_CHANGE_INFO,
    GROUP_ADMIN_DELETE_MESSAGES,
    GROUP_ADMIN_INVITE_USERS,
    GROUP_ADMIN_PIN_MESSAGES,
    GROUP_MEMBER,
    GROUP_OWNER,
    OWNER,
    PM,
    SUDO,
    SUPPORT,
)

logger = logging.getLogger(__name__)


def chunks(lst: list, n: int) -> List[list]:
    return [lst[i : i + n] for i in range(0, len(lst), n)]


@loader.tds
class GeekSecurityMod(loader.Module):
    """Control security settings (geek3.0.8alpha+)"""

    strings = {
        "name": "GeekSecurity",
        "no_command": "🚫 <b>Command </b><code>{}</code><b> not found!</b>",
        "permissions": "🔐 <b>Here you can configure permissions for </b><code>{}{}</code>",
        "close_menu": "🙈 Close this menu",
        "global": "🔐 <b>Here you can configure global bounding mask. If the permission is excluded here, it is excluded everywhere!</b>",
        "owner": "🤴 Owner",
        "sudo": "🤵 Sudo",
        "support": "💁‍♂️ Support",
        "group_owner": "🧛‍♂️ Group owner",
        "group_admin_add_admins": "👨‍💻 Admin (add members)",
        "group_admin_change_info": "👨‍💻 Admin (change info)",
        "group_admin_ban_users": "👨‍💻 Admin (ban)",
        "group_admin_delete_messages": "👨‍💻 Admin (delete msgs)",
        "group_admin_pin_messages": "👨‍💻 Admin (pin)",
        "group_admin_invite_users": "👨‍💻 Admin (invite)",
        "group_admin": "👨‍💻 Admin (any)",
        "group_member": "👥 In group",
        "pm": "🤙 In PM",
        "owner_list": "🤴 <b>Users in group </b><code>owner</code><b>:</b>\n\n{}",
        "sudo_list": "🤵‍♀️ <b>Users in group </b><code>sudo</code><b>:</b>\n\n{}",
        "support_list": "🙋‍♂️ <b>Users in group </b><code>support</code><b>:</b>\n\n{}",
        "no_owner": "🤴 <b>There is no users in group </b><code>owner</code>",
        "no_sudo": "🤵‍♀️ <b>There is no users in group </b><code>sudo</code>",
        "no_support": "🙋‍♂️ <b>There is no users in group </b><code>support</code>",
        "owner_added": '🤴 <b><a href="tg://user?id={}">{}</a> added to group </b><code>owner</code>',
        "sudo_added": '🤵‍♀️ <b><a href="tg://user?id={}">{}</a> added to group </b><code>sudo</code>',
        "support_added": '🙋‍♂️ <b><a href="tg://user?id={}">{}</a> added to group </b><code>support</code>',
        "owner_removed": '🤴 <b><a href="tg://user?id={}">{}</a> removed from group </b><code>owner</code>',
        "sudo_removed": '🤵‍♀️ <b><a href="tg://user?id={}">{}</a> removed from group </b><code>sudo</code>',
        "support_removed": '🙋‍♂️ <b><a href="tg://user?id={}">{}</a> removed from group </b><code>support</code>',
        "no_user": "🚫 <b>Specify user to permit</b>",
        "not_a_user": "🚫 <b>Specified entity is not a user</b>",
        "li": '⦿ <b><a href="tg://user?id={}">{}</a></b>',
        "warning": (
            '⚠️ <b>Please, confirm, that you want to add <a href="tg://user?id={}">{}</a> '
            "to group </b><code>{}</code><b>!\n"
            "This action may reveal personal info and grant "
            "full or partial access to userbot to this user</b>"
        ),
        "cancel": "🚫 Cancel",
        "confirm": "👑 Confirm",
        "self": "🚫 <b>You can't promote/demote yourself!</b>",
        "restart": "<i>🔄 Restart may be required to commit changes</i>",
    }

    def get(self, *args) -> dict:
        return self.ctx.db.get(self.strings["name"], *args)

    def set(self, *args) -> None:
        return self.ctx.db.set(self.strings["name"], *args)

    async def client_ready(self, client, db) -> None:
        self.prefix = utils.escape_html(
            (self.ctx.db.get(main.__name__, "command_prefix", False) or ".")
        )

        self._me = (await client.get_me()).id
        self._is_geek = hasattr(self, "inline")

    async def inline__switch_perm(
        self, call: InlineCall, command: str, group: str, level: bool
    ) -> None:
        cmd = self.allmodules.commands[command]
        mask = self.ctx.db.get(security.__name__, "masks", {}).get(
            f"{cmd.__module__}.{cmd.__name__}",
            getattr(cmd, "security", security.DEFAULT_PERMISSIONS),
        )

        bit = security.BITMAP[group.upper()]

        if level:
            mask |= bit
        else:
            mask &= ~bit

        masks = self.ctx.db.get(security.__name__, "masks", {})
        masks[f"{cmd.__module__}.{cmd.__name__}"] = mask
        self.ctx.db.set(security.__name__, "masks", masks)

        await call.answer("Security value set!")
        await call.edit(
            self.strings("permissions").format(self.prefix, command),
            reply_markup=self._build_markup(cmd),
        )

    async def inline__switch_perm_bm(
        self, call: InlineCall, group: str, level: bool
    ) -> None:
        mask = self.ctx.db.get(security.__name__, "bounding_mask", DEFAULT_PERMISSIONS)
        bit = security.BITMAP[group.upper()]

        if level:
            mask |= bit
        else:
            mask &= ~bit

        self.ctx.db.set(security.__name__, "bounding_mask", mask)

        await call.answer("Bounding mask value set!")
        await call.edit(
            self.strings("global"), reply_markup=self._build_markup_global()
        )

    @staticmethod
    async def inline_close(call: InlineCall) -> None:
        await call.delete()

    def _build_markup(self, command: FunctionType) -> List[List[dict]]:
        perms = self._get_current_perms(command)
        buttons = [
            {
                "text": f"{'✅' if level else '🚫'} {self.strings[group]}",
                "callback": self.inline__switch_perm,
                "args": (command.__name__[:-3], group, not level),
            }
            for group, level in perms.items()
        ]

        return chunks(buttons, 2) + [
            [{"text": self.strings("close_menu"), "callback": self.inline_close}]
        ]

    def _build_markup_global(self) -> List[List[dict]]:
        perms = self._get_current_bm()
        buttons = [
            {
                "text": f"{'✅' if level else '🚫'} {self.strings[group]}",
                "callback": self.inline__switch_perm_bm,
                "args": (group, not level),
            }
            for group, level in perms.items()
        ]

        return chunks(buttons, 2) + [
            [{"text": self.strings("close_menu"), "callback": self.inline_close}]
        ]

    def _get_current_bm(self) -> dict:
        return self._perms_map(
            self.ctx.db.get(security.__name__, "bounding_mask", DEFAULT_PERMISSIONS)
        )

    @staticmethod
    def _perms_map(perms: int) -> dict:
        return {
            "owner": bool(perms & OWNER),
            "sudo": bool(perms & SUDO),
            "support": bool(perms & SUPPORT),
            "group_owner": bool(perms & GROUP_OWNER),
            "group_admin_add_admins": bool(perms & GROUP_ADMIN_ADD_ADMINS),
            "group_admin_change_info": bool(perms & GROUP_ADMIN_CHANGE_INFO),
            "group_admin_ban_users": bool(perms & GROUP_ADMIN_BAN_USERS),
            "group_admin_delete_messages": bool(perms & GROUP_ADMIN_DELETE_MESSAGES),
            "group_admin_pin_messages": bool(perms & GROUP_ADMIN_PIN_MESSAGES),
            "group_admin_invite_users": bool(perms & GROUP_ADMIN_INVITE_USERS),
            "group_admin": bool(perms & GROUP_ADMIN),
            "group_member": bool(perms & GROUP_MEMBER),
            "pm": bool(perms & PM),
        }

    def _get_current_perms(self, command: FunctionType) -> dict:
        config = self.ctx.db.get(security.__name__, "masks", {}).get(
            f"{command.__module__}.{command.__name__}",
            getattr(
                command, "security", self.ctx.client.dispatcher.security._default
            ),  # skipcq: PYL-W0212
        )

        return self._perms_map(config)

    async def securitycmd(self, message: Message) -> None:
        """[command] - Configure command's security settings"""
        args = utils.get_args_raw(message).lower().strip()
        if args and args not in self.allmodules.commands:
            await utils.answer(message, self.strings("no_command").format(args))
            return

        if not args:
            await self.inline.form(
                self.strings("global"),
                reply_markup=self._build_markup_global(),
                message=message,
                ttl=5 * 60,
            )
            return

        cmd = self.allmodules.commands[args]

        await self.inline.form(
            self.strings("permissions").format(self.prefix, args),
            reply_markup=self._build_markup(cmd),
            message=message,
            ttl=5 * 60,
        )

    async def _resolve_user(self, message: Message) -> None:
        reply = await message.get_reply_message()
        args = utils.get_args_raw(message)

        if not args and not reply:
            await utils.answer(message, self.strings("no_user"))
            return

        user = None

        if args:
            try:
                if str(args).isdigit():
                    args = int(args)

                user = await self.ctx.client.get_entity(args)
            except Exception:
                pass

        if user is None:
            user = await self.ctx.client.get_entity(reply.sender_id)

        if not isinstance(user, (User, PeerUser)):
            await utils.answer(message, self.strings("not_a_user"))
            return

        if user.id == self._me:
            await utils.answer(message, self.strings("self"))
            return

        return user

    async def _add_to_group(
        self,
        message: Union[Message, InlineCall],  # noqa: F821
        group: str,
        confirmed: bool = False,
        user: int = None,
    ) -> None:
        if user is None:
            user = await self._resolve_user(message)
            if not user:
                return

        if isinstance(user, int):
            user = await self.ctx.client.get_entity(user)

        if self._is_geek and not confirmed:
            await self.inline.form(
                self.strings("warning").format(
                    user.id, utils.escape_html(get_display_name(user)), group
                ),
                message=message,
                ttl=10 * 60,
                reply_markup=[
                    [
                        {
                            "text": self.strings("cancel"),
                            "callback": self.inline_close,
                        },
                        {
                            "text": self.strings("confirm"),
                            "callback": self._add_to_group,
                            "args": (group, True, user.id),
                        },
                    ]
                ],
            )
            return

        self.ctx.db.set(
            security.__name__,
            group,
            list(set(self.ctx.db.get(security.__name__, group, []) + [user.id])),
        )

        m = self.strings(f"{group}_added").format(
            user.id,
            utils.escape_html(get_display_name(user)),
        )

        if not self._is_geek:
            m += f"\n\n{self.strings('restart')}"

        if isinstance(message, Message):
            await utils.answer(
                message,
                m,
            )
        else:
            await message.edit(m)

    async def _remove_from_group(self, message: Message, group: str) -> None:
        user = await self._resolve_user(message)
        if not user:
            return

        self.ctx.db.set(
            security.__name__,
            group,
            list(set(self.ctx.db.get(security.__name__, group, [])) - {user.id}),
        )

        m = self.strings(f"{group}_removed").format(
            user.id,
            utils.escape_html(get_display_name(user)),
        )

        if not self._is_geek:
            m += f"\n\n{self.strings('restart')}"

        await utils.answer(message, m)

    async def _list_group(self, message: Message, group: str) -> None:
        _resolved_users = []
        for user in self.ctx.db.get(security.__name__, group, []) + (
            [self._me] if group == "owner" else []
        ):
            try:
                _resolved_users += [await self.ctx.client.get_entity(user)]
            except Exception:
                pass

        if _resolved_users:
            await utils.answer(
                message,
                self.strings(f"{group}_list").format(
                    "\n".join(
                        [
                            self.strings("li").format(
                                i.id, utils.escape_html(get_display_name(i))
                            )
                            for i in _resolved_users
                        ]
                    )
                ),
            )
        else:
            await utils.answer(message, self.strings(f"no_{group}"))

    async def sudoaddcmd(self, message: Message) -> None:
        """<user> - Add user to `sudo`"""
        await self._add_to_group(message, "sudo")

    async def owneraddcmd(self, message: Message) -> None:
        """<user> - Add user to `owner`"""
        await self._add_to_group(message, "owner")

    async def supportaddcmd(self, message: Message) -> None:
        """<user> - Add user to `support`"""
        await self._add_to_group(message, "support")

    async def sudormcmd(self, message: Message) -> None:
        """<user> - Remove user from `sudo`"""
        await self._remove_from_group(message, "sudo")

    async def ownerrmcmd(self, message: Message) -> None:
        """<user> - Remove user from `owner`"""
        await self._remove_from_group(message, "owner")

    async def supportrmcmd(self, message: Message) -> None:
        """<user> - Remove user from `support`"""
        await self._remove_from_group(message, "support")

    async def sudolistcmd(self, message: Message) -> None:
        """List users in `sudo`"""
        await self._list_group(message, "sudo")

    async def ownerlistcmd(self, message: Message) -> None:
        """List users in `owner`"""
        await self._list_group(message, "owner")

    async def supportlistcmd(self, message: Message) -> None:
        """List users in `support`"""
        await self._list_group(message, "support")
