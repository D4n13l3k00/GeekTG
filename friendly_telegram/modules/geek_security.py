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
from typing import Any, List, Optional, Union

from telethon.tl.custom import Message
from telethon.tl.types import User
from telethon.utils import get_display_name

from .. import loader, main, security, utils
from ..inline.types import InlineCall
from ..security import DEFAULT_PERMISSIONS

logger = logging.getLogger(__name__)


def chunks(lst: list, n: int) -> List[list]:
    return [lst[i : i + n] for i in range(0, len(lst), n)]


def _flip(mask: int, bit: int, on: bool) -> int:
    return (mask | bit) if on else (mask & ~bit)


@loader.tds
class GeekSecurityMod(loader.Module):
    """Control security settings (geek3.0.8alpha+)"""

    strings = {
        "name": "GeekSecurity",
        "no_command": "<tg-emoji emoji-id='5240241223632954241'>🚫</tg-emoji> <b>Command </b><code>{}</code><b> not found!</b>",
        "permissions": "<tg-emoji emoji-id='5472308992514464048'>🔐</tg-emoji> <b>Here you can configure permissions for </b><code>{}{}</code>",
        "close_menu": "<tg-emoji emoji-id='5467370583282950466'>🙈</tg-emoji> Close this menu",
        "global": "<tg-emoji emoji-id='5472308992514464048'>🔐</tg-emoji> <b>Here you can configure global bounding mask. If the permission is excluded here, it is excluded everywhere!</b>",
        "owner": "<tg-emoji emoji-id='5217822164362739968'>🤴</tg-emoji> Owner",
        "sudo": "🤵 Sudo",
        "support": "💁‍♂️ Support",
        "group_owner": "🧛‍♂️ Group owner",
        "group_admin_add_admins": "<tg-emoji emoji-id='5190498849440931467'>👨‍💻</tg-emoji> Admin (add members)",
        "group_admin_change_info": "<tg-emoji emoji-id='5190498849440931467'>👨‍💻</tg-emoji> Admin (change info)",
        "group_admin_ban_users": "<tg-emoji emoji-id='5190498849440931467'>👨‍💻</tg-emoji> Admin (ban)",
        "group_admin_delete_messages": "<tg-emoji emoji-id='5190498849440931467'>👨‍💻</tg-emoji> Admin (delete msgs)",
        "group_admin_pin_messages": "<tg-emoji emoji-id='5190498849440931467'>👨‍💻</tg-emoji> Admin (pin)",
        "group_admin_invite_users": "<tg-emoji emoji-id='5190498849440931467'>👨‍💻</tg-emoji> Admin (invite)",
        "group_admin": "<tg-emoji emoji-id='5190498849440931467'>👨‍💻</tg-emoji> Admin (any)",
        "group_member": "<tg-emoji emoji-id='5372926953978341366'>👥</tg-emoji> In group",
        "pm": "<tg-emoji emoji-id='5469774158650942877'>🤙</tg-emoji> In PM",
        "owner_list": "<tg-emoji emoji-id='5217822164362739968'>🤴</tg-emoji> <b>Users in group </b><code>owner</code><b>:</b>\n\n{}",
        "sudo_list": "🤵‍♀️ <b>Users in group </b><code>sudo</code><b>:</b>\n\n{}",
        "support_list": "🙋‍♂️ <b>Users in group </b><code>support</code><b>:</b>\n\n{}",
        "no_owner": "<tg-emoji emoji-id='5217822164362739968'>🤴</tg-emoji> <b>There is no users in group </b><code>owner</code>",
        "no_sudo": "🤵‍♀️ <b>There is no users in group </b><code>sudo</code>",
        "no_support": "🙋‍♂️ <b>There is no users in group </b><code>support</code>",
        "owner_added": '<tg-emoji emoji-id="5217822164362739968">🤴</tg-emoji> <b><a href="tg://user?id={}">{}</a> added to group </b><code>owner</code>',
        "sudo_added": '🤵‍♀️ <b><a href="tg://user?id={}">{}</a> added to group </b><code>sudo</code>',
        "support_added": '🙋‍♂️ <b><a href="tg://user?id={}">{}</a> added to group </b><code>support</code>',
        "owner_removed": '<tg-emoji emoji-id="5217822164362739968">🤴</tg-emoji> <b><a href="tg://user?id={}">{}</a> removed from group </b><code>owner</code>',
        "sudo_removed": '🤵‍♀️ <b><a href="tg://user?id={}">{}</a> removed from group </b><code>sudo</code>',
        "support_removed": '🙋‍♂️ <b><a href="tg://user?id={}">{}</a> removed from group </b><code>support</code>',
        "no_user": "<tg-emoji emoji-id='5240241223632954241'>🚫</tg-emoji> <b>Specify user to permit</b>",
        "not_a_user": "<tg-emoji emoji-id='5240241223632954241'>🚫</tg-emoji> <b>Specified entity is not a user</b>",
        "li": '⦿ <b><a href="tg://user?id={}">{}</a></b>',
        "warning": (
            '⚠️ <b>Please, confirm, that you want to add <a href="tg://user?id={}">{}</a> '
            "to group </b><code>{}</code><b>!\n"
            "This action may reveal personal info and grant "
            "full or partial access to userbot to this user</b>"
        ),
        "cancel": "<tg-emoji emoji-id='5240241223632954241'>🚫</tg-emoji> Cancel",
        "confirm": "<tg-emoji emoji-id='5467406098367521267'>👑</tg-emoji> Confirm",
        "self": "<tg-emoji emoji-id='5240241223632954241'>🚫</tg-emoji> <b>You can't promote/demote yourself!</b>",
    }

    async def client_ready(self, client, db) -> None:
        self.prefix = utils.escape_html(
            self.ctx.db.get(main.__name__, "command_prefix", False) or "."
        )
        self._me = (await client.get_me()).id

    # ---------------------------------------------------------------- helpers

    def _cmd_key(self, cmd: FunctionType) -> str:
        return f"{cmd.__module__}.{cmd.__name__}"

    def _perms_map(self, perms: int) -> dict:
        """Lowercased label → bool, in BITMAP order."""
        return {
            name.lower(): bool(perms & bit) for name, bit in security.BITMAP.items()
        }

    def _current_cmd_mask(self, cmd: FunctionType) -> int:
        client: Any = self.ctx.client
        masks = self.ctx.db.get(security.__name__, "masks", {}) or {}
        return masks.get(
            self._cmd_key(cmd),
            getattr(
                cmd,
                "security",
                client.dispatcher.security._default,  # noqa: SLF001
            ),
        )

    def _current_global_mask(self) -> int:
        value = self.ctx.db.get(security.__name__, "bounding_mask", DEFAULT_PERMISSIONS)
        return value if value is not None else DEFAULT_PERMISSIONS

    def _perm_buttons(self, mask: int, callback, prefix_args: tuple) -> list:
        """Build the permission toggle keyboard for either single-cmd or global."""
        perms = self._perms_map(mask)

        def _icon(level: bool) -> str:
            return (
                "<tg-emoji emoji-id='5427009714745517609'>✅</tg-emoji>"
                if level
                else "<tg-emoji emoji-id='5240241223632954241'>🚫</tg-emoji>"
            )

        buttons = [
            {
                "text": f"{_icon(level)} {self.strings[group]}",
                "callback": callback,
                "args": (*prefix_args, group, not level),
            }
            for group, level in perms.items()
        ]
        return chunks(buttons, 2) + [
            [
                {
                    "text": self.tr("close_menu"),
                    "callback": self.inline_close,
                    "style": "danger",
                }
            ]
        ]

    def _build_markup(self, command: FunctionType) -> List[List[dict]]:
        return self._perm_buttons(
            self._current_cmd_mask(command),
            self.inline__switch_perm,
            (command.__name__[:-3],),
        )

    def _build_markup_global(self) -> List[List[dict]]:
        return self._perm_buttons(
            self._current_global_mask(), self.inline__switch_perm_bm, ()
        )

    # ------------------------------------------------------------ inline cbs

    async def inline__switch_perm(
        self, call: InlineCall, command: str, group: str, level: bool
    ) -> None:
        cmd = self.allmodules.commands[command]
        bit = security.BITMAP[group.upper()]
        masks = self.ctx.db.get(security.__name__, "masks", {}) or {}
        masks[self._cmd_key(cmd)] = _flip(self._current_cmd_mask(cmd), bit, level)
        self.ctx.db.set(security.__name__, "masks", masks)

        await call.answer("Security value set!")
        await call.edit(
            self.tr("permissions").format(self.prefix, command),
            reply_markup=self._build_markup(cmd),
        )

    async def inline__switch_perm_bm(
        self, call: InlineCall, group: str, level: bool
    ) -> None:
        bit = security.BITMAP[group.upper()]
        new = _flip(self._current_global_mask(), bit, level)
        self.ctx.db.set(security.__name__, "bounding_mask", new)

        await call.answer("Bounding mask value set!")
        await call.edit(self.tr("global"), reply_markup=self._build_markup_global())

    @staticmethod
    async def inline_close(call: InlineCall) -> None:
        await call.delete()

    # --------------------------------------------------------------- command

    async def securitycmd(self, message: Message) -> None:
        """[command] - Configure command's security settings"""
        args = utils.get_args_raw(message).lower().strip()
        if args and args not in self.allmodules.commands:
            await utils.answer(message, self.tr("no_command").format(args))
            return

        if not args:
            await self.inline.form(
                self.tr("global"),
                reply_markup=self._build_markup_global(),
                message=message,
                ttl=5 * 60,
            )
            return

        cmd = self.allmodules.commands[args]
        await self.inline.form(
            self.tr("permissions").format(self.prefix, args),
            reply_markup=self._build_markup(cmd),
            message=message,
            ttl=5 * 60,
        )

    # ------------------------------------------------------------ user mgmt

    async def _resolve_user(self, message: Message) -> Optional[User]:
        reply = await message.get_reply_message()
        args: Union[str, int] = utils.get_args_raw(message)

        if not args and not reply:
            await utils.answer(message, self.tr("no_user"))
            return None

        user = None
        if args:
            try:
                if str(args).isdigit():
                    args = int(args)
                user = await self.ctx.client.get_entity(args)
            except Exception:
                logger.debug("explicit-arg entity lookup failed", exc_info=True)

        if user is None:
            if reply is None:
                await utils.answer(message, self.tr("not_a_user"))
                return None
            try:
                user = await self.ctx.client.get_entity(reply.sender_id)
            except Exception:
                logger.debug("reply entity lookup failed", exc_info=True)
                await utils.answer(message, self.tr("not_a_user"))
                return None

        if not isinstance(user, User):
            await utils.answer(message, self.tr("not_a_user"))
            return None

        if user.id == self._me:
            await utils.answer(message, self.tr("self"))
            return None

        return user

    def _group_add(self, group: str, user_id: int) -> None:
        ids = set(self.ctx.db.get(security.__name__, group, []) or []) | {user_id}
        self.ctx.db.set(security.__name__, group, list(ids))

    def _group_remove(self, group: str, user_id: int) -> None:
        ids = set(self.ctx.db.get(security.__name__, group, []) or []) - {user_id}
        self.ctx.db.set(security.__name__, group, list(ids))

    async def _add_to_group(
        self,
        message: Union[Message, InlineCall],
        group: str,
        confirmed: bool = False,
        user: Optional[Union[int, User]] = None,
    ) -> None:
        entity: User
        if user is None:
            if not isinstance(message, Message):
                return
            resolved = await self._resolve_user(message)
            if resolved is None:
                return
            entity = resolved
        elif isinstance(user, int):
            looked_up = await self.ctx.client.get_entity(user)
            if not isinstance(looked_up, User):
                return
            entity = looked_up
        else:
            entity = user

        if not confirmed:
            await self.inline.form(
                self.tr("warning").format(
                    entity.id, utils.escape_html(get_display_name(entity)), group
                ),
                message=message,
                ttl=10 * 60,
                reply_markup=[
                    [
                        {
                            "text": self.tr("cancel"),
                            "callback": self.inline_close,
                            "style": "danger",
                        },
                        {
                            "text": self.tr("confirm"),
                            "callback": self._add_to_group,
                            "args": (group, True, entity.id),
                            "style": "success",
                        },
                    ]
                ],
            )
            return

        self._group_add(group, entity.id)
        text = self.tr(f"{group}_added").format(
            entity.id, utils.escape_html(get_display_name(entity))
        )
        if isinstance(message, Message):
            await utils.answer(message, text)
        else:
            await message.edit(text)

    async def _remove_from_group(self, message: Message, group: str) -> None:
        user = await self._resolve_user(message)
        if not user:
            return
        self._group_remove(group, user.id)
        await utils.answer(
            message,
            self.tr(f"{group}_removed").format(
                user.id, utils.escape_html(get_display_name(user))
            ),
        )

    async def _list_group(self, message: Message, group: str) -> None:
        ids = self.ctx.db.get(security.__name__, group, []) or []
        if group == "owner":
            ids = ids + [self._me]

        resolved = []
        for uid in ids:
            try:
                resolved.append(await self.ctx.client.get_entity(uid))
            except Exception:
                logger.debug("group %s: entity %s missing", group, uid, exc_info=True)

        if not resolved:
            await utils.answer(message, self.tr(f"no_{group}"))
            return

        body = "\n".join(
            self.tr("li").format(u.id, utils.escape_html(get_display_name(u)))
            for u in resolved
        )
        await utils.answer(message, self.tr(f"{group}_list").format(body))

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
