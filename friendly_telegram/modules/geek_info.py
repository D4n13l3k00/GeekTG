"""
█ █ ▀ █▄▀ ▄▀█ █▀█ ▀    ▄▀█ ▀█▀ ▄▀█ █▀▄▀█ ▄▀█
█▀█ █ █ █ █▀█ █▀▄ █ ▄  █▀█  █  █▀█ █ ▀ █ █▀█

Copyright 2022 t.me/hikariatama
Licensed under the GNU GPLv3
"""

# scope: inline

import logging

import git
from aiogram.types import InlineQueryResultPhoto
from telethon.utils import get_display_name

from .. import loader, utils
from ..inline import GeekInlineQuery, rand

logger = logging.getLogger(__name__)


@loader.tds
class GeekInfoMod(loader.Module):
    """Show userbot info (geek3.1.0alpha+)"""

    strings = {
        "name": "GeekInfo",
        "_custom_msg_doc": "Custom message must have {owner}, {version}, {build}, {upd}, {platform} keywords",
        "_custom_button_doc": "Custom buttons.",
        "_photo_url_doc": "You can set your own photo to geek info.",
        "default_message": (
            "🕶 <b>GeekTG Userbot</b>\n\n"
            "<tg-emoji emoji-id='5217822164362739968'>🤴</tg-emoji> <b>Owner:</b> {owner}\n"
            "<tg-emoji emoji-id='5361837567463399422'>🔮</tg-emoji> <b>Version:</b> <i>{version}</i>\n"
            "<tg-emoji emoji-id='5436275698664759373'>🧱</tg-emoji> <b>Build:</b> {build}\n"
            "{upd}\n\n"
            "{platform}"
        ),
    }

    async def client_ready(self, client, db) -> None:
        self._me = await client.get_me()

    def __init__(self):
        self.config = loader.ModuleConfig(
            "custom_message",
            False,
            lambda: self.tr("_custom_msg_doc"),
            "custom_buttons",
            {"text": "🤵‍♀️ Support chat", "url": "https://t.me/GeekTGChat"},
            lambda: self.tr("_custom_button_doc"),
            "photo_url",
            "https://i.ibb.co/nMtdQXPn/maskot.jpg",
            lambda: self.tr("_photo_url_doc"),
        )

    def _update_status(self) -> str:
        """HTML snippet describing whether the working copy is behind origin."""
        try:
            repo = git.Repo()
            diff = repo.git.log(["HEAD..origin", "--oneline"])
        except Exception:
            logger.debug("git status check failed", exc_info=True)
            return ""
        if diff:
            return "<tg-emoji emoji-id='5213205860498549992'>⚠️</tg-emoji> <b>Update required:</b> <code>.update</code>"
        return (
            "<tg-emoji emoji-id='5427009714745517609'>✅</tg-emoji> <b>Up-to-date</b>"
        )

    def _owner_html(self) -> str:
        return (
            f'<a href="tg://user?id={self._me.id}">'
            f"{utils.escape_html(get_display_name(self._me) or '')}</a>"
        )

    def _build_html(self) -> str:
        ver, gitlink = utils.get_git_info()
        sha = utils.escape_html((ver or "")[:8] or "Unknown")
        return f'<a href="{utils.escape_html(gitlink or "")}">{sha}</a>'

    def build_message(self) -> str:
        """Render the .info caption using the configured (or default) template."""
        ctx = {
            "owner": self._owner_html(),
            "version": utils.escape_html(utils.get_version_raw()),
            "build": self._build_html(),
            "upd": self._update_status(),
            "platform": utils.get_platform_name(),
        }
        fmt = self.config["custom_message"] or self.tr("default_message")
        try:
            return fmt.format(**ctx)
        except (KeyError, IndexError):
            # User-provided template referenced an unknown placeholder — fall
            # back to the bundled default so the command keeps working.
            return self.tr("default_message").format(**ctx)

    async def info_inline_handler(self, query: GeekInlineQuery) -> None:
        """
        Send userbot info
        @allow: all
        """

        await query.answer(
            [
                InlineQueryResultPhoto(
                    id=rand(20),
                    photo_url=self.config["photo_url"],
                    title="Send userbot info",
                    description="ℹ This will not compromise any sensitive data",
                    caption=self.build_message(),
                    parse_mode="HTML",
                    thumbnail_url="https://github.com/D4n13l3k00/GeekTG/raw/master/friendly-telegram/bot_avatar.png",  # noqa: E501
                    reply_markup=self.inline._generate_markup(
                        self.config["custom_buttons"]
                    ),
                )
            ],
            cache_time=0,
        )

    async def infocmd(self, message):
        """
        Send userbot info
        """
        return await self.inline.form(
            message=message,
            text=self.build_message(),
            reply_markup=self.config["custom_buttons"],
            photo=self.config["photo_url"],
        )
