"""Quickly create private channels, groups and supergroups with one command.

Commands
--------
.newchannel [title] — create a private channel
.newgroup    [title] — create a basic group (up to 200 members)
.newsuper    [title] — create a supergroup (unlimited members)

Inline
------
@bot newchat — interactive form to pick the type and create the chat
"""

# scope: inline

import logging

from telethon.tl.custom import Message
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.tl.functions.messages import CreateChatRequest

from .. import loader, utils

logger = logging.getLogger(__name__)

_DEFAULT_TITLES = {
    "channel": "New Channel",
    "group": "New Group",
    "supergroup": "New Supergroup",
}


async def _create_channel(client, title: str) -> str:
    """Create a private broadcast channel; return its t.me link."""
    result = await client(CreateChannelRequest(title=title, about="", megagroup=False))
    ch = result.chats[0]
    return f"https://t.me/c/{ch.id}/1"


async def _create_group(client, title: str) -> str:
    """Create a basic group (legacy chat); return placeholder link."""
    result = await client(CreateChatRequest(users=[], title=title))
    chat = result.chats[0]
    return f"https://t.me/c/{chat.id}/1"


async def _create_supergroup(client, title: str) -> str:
    """Create a supergroup (megagroup channel); return its t.me link."""
    result = await client(CreateChannelRequest(title=title, about="", megagroup=True))
    ch = result.chats[0]
    return f"https://t.me/c/{ch.id}/1"


@loader.tds
class ChatCreatorMod(loader.Module):
    """Create private channels, groups and supergroups instantly."""

    strings = {
        "name": "ChatCreator",
        "creating": "⏳ <b>Creating {type}</b> <i>{title}</i>…",
        "done_channel": (
            "📢 <b>Channel created!</b>\n\n"
            "📌 <b>Title:</b> <code>{title}</code>\n"
            "🔗 <b>Link:</b> {link}"
        ),
        "done_group": (
            "👥 <b>Group created!</b>\n\n"
            "📌 <b>Title:</b> <code>{title}</code>\n"
            "🔗 <b>Link:</b> {link}"
        ),
        "done_supergroup": (
            "🌐 <b>Supergroup created!</b>\n\n"
            "📌 <b>Title:</b> <code>{title}</code>\n"
            "🔗 <b>Link:</b> {link}"
        ),
        "error": "🚫 <b>Failed to create:</b> <code>{err}</code>",
        "no_title": "❓ <b>Specify a title:</b> <code>{usage}</code>",
        # inline
        "inline_pick": "🗂 <b>What do you want to create?</b>",
        "inline_title_prompt": (
            "✏️ <b>Send a title for the new {type}</b>\n\n"
            "📌 <b>Current title:</b> <code>{title}</code>"
        ),
        "btn_channel": "📢 Channel",
        "btn_group": "👥 Group",
        "btn_super": "🌐 Supergroup",
        "btn_default": "✅ Use default title",
        "btn_custom": "✏️ Enter title",
        "btn_back": "⬅️ Back",
        "cancelled": "✖️ <b>Cancelled.</b>",
    }

    # ------------------------------------------------------------------ commands

    @loader.owner
    async def newchannelcmd(self, message: Message) -> None:
        """.newchannel <title> — create a private channel"""
        await self._create_and_reply(message, "channel", ".newchannel <title>")

    @loader.owner
    async def newgroupcmd(self, message: Message) -> None:
        """.newgroup <title> — create a basic group"""
        await self._create_and_reply(message, "group", ".newgroup <title>")

    @loader.owner
    async def newsupercmd(self, message: Message) -> None:
        """.newsuper <title> — create a supergroup"""
        await self._create_and_reply(message, "supergroup", ".newsuper <title>")

    @loader.owner
    async def newchatcmd(self, message: Message) -> None:
        """.newchat — open an inline form to create a chat"""
        await self.inline.form(
            text=self.tr("inline_pick", message),
            message=message,
            reply_markup=self._pick_markup(),
            ttl=300,
        )

    # ------------------------------------------------------------------ form callbacks

    def _pick_markup(self) -> list:
        return [
            [
                {
                    "text": self.tr("btn_channel"),
                    "callback": self._stage_two,
                    "args": ("channel",),
                },
                {
                    "text": self.tr("btn_group"),
                    "callback": self._stage_two,
                    "args": ("group",),
                },
            ],
            [
                {
                    "text": self.tr("btn_super"),
                    "callback": self._stage_two,
                    "args": ("supergroup",),
                },
            ],
        ]

    async def _stage_two(self, call, chat_type: str) -> None:
        """Second step: ask for default-or-custom title."""
        type_label = {
            "channel": self.tr("btn_channel"),
            "group": self.tr("btn_group"),
            "supergroup": self.tr("btn_super"),
        }[chat_type]
        default_title = _DEFAULT_TITLES[chat_type]
        await call.edit(
            text=self.tr("inline_title_prompt").format(
                type=type_label, title=utils.escape_html(default_title)
            ),
            reply_markup=[
                [
                    {
                        "text": self.tr("btn_default"),
                        "callback": self._do_create_cb,
                        "args": (chat_type, default_title),
                    },
                ],
                [
                    {
                        "text": self.tr("btn_custom"),
                        "input": self.tr("inline_title_prompt").format(
                            type=type_label, title=utils.escape_html(default_title)
                        ),
                        "handler": self._title_input,
                        # ``inline_message_id`` is required so call.edit() can
                        # locate the form after the user types — without it
                        # aiogram raises "message identifier is not specified".
                        "args": (chat_type, call.inline_message_id),
                    },
                ],
                [
                    {"text": self.tr("btn_back"), "callback": self._stage_one},
                ],
            ],
        )

    async def _stage_one(self, call) -> None:
        await call.edit(
            text=self.tr("inline_pick"),
            reply_markup=self._pick_markup(),
        )

    async def _title_input(
        self, call, query, chat_type: str, inline_message_id: str
    ) -> None:
        """User typed a title in response to the inline 'input' button."""
        title = (query or "").strip() or _DEFAULT_TITLES[chat_type]
        await self._do_create_cb(call, chat_type, title, inline_message_id)

    async def _do_create_cb(
        self,
        call,
        chat_type: str,
        title: str,
        inline_message_id: str = None,
    ) -> None:
        """Run creation from inline; edit the form with the result."""
        edit_kwargs = (
            {"inline_message_id": inline_message_id} if inline_message_id else {}
        )
        await call.edit(
            text=self.tr("creating").format(
                type=chat_type.capitalize(), title=utils.escape_html(title)
            ),
            **edit_kwargs,
        )
        try:
            link = await self._do_create(chat_type, title)
        except Exception as e:
            logger.exception("ChatCreator inline: failed to create %s", chat_type)
            await call.edit(
                text=self.tr("error").format(err=utils.escape_html(str(e))),
                **edit_kwargs,
            )
            return
        await call.edit(
            text=self.tr(f"done_{chat_type}").format(
                title=utils.escape_html(title), link=link
            ),
            **edit_kwargs,
        )

    # ------------------------------------------------------------------ helpers

    async def _create_and_reply(
        self, message: Message, chat_type: str, usage: str
    ) -> None:
        title = (utils.get_args_raw(message)).strip()
        if not title:
            await utils.answer(
                message,
                self.tr("no_title", message).format(usage=utils.escape_html(usage)),
            )
            return
        prog = await utils.answer(
            message,
            self.tr("creating", message).format(
                type=chat_type.capitalize(), title=utils.escape_html(title)
            ),
        )
        if isinstance(prog, (list, tuple)):
            prog = prog[0]
        try:
            link = await self._do_create(chat_type, title)
        except Exception as e:
            logger.exception("ChatCreator: failed to create %s", chat_type)
            await utils.answer(
                prog,
                self.tr("error", message).format(err=utils.escape_html(str(e))),
            )
            return
        await utils.answer(
            prog,
            self.tr(f"done_{chat_type}", message).format(
                title=utils.escape_html(title), link=link
            ),
        )

    async def _do_create(self, chat_type: str, title: str) -> str:
        """Dispatch to the correct Telethon creator; return a t.me link."""
        client = self.ctx.client
        if chat_type == "channel":
            return await _create_channel(client, title)
        if chat_type == "group":
            return await _create_group(client, title)
        if chat_type == "supergroup":
            return await _create_supergroup(client, title)
        raise ValueError(f"Unknown chat type: {chat_type!r}")
