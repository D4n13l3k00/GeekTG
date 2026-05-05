"""
█ █ ▀ █▄▀ ▄▀█ █▀█ ▀    ▄▀█ ▀█▀ ▄▀█ █▀▄▀█ ▄▀█
█▀█ █ █ █ █▀█ █▀▄ █ ▄  █▀█  █  █▀█ █ ▀ █ █▀█

Copyright 2022 t.me/hikariatama
Licensed under the GNU GPLv3
"""

# scope: inline

import logging

import aiogram
import git
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
            "🤴 <b>Owner:</b> {owner}\n"
            "🔮 <b>Version:</b> <i>{version}</i>\n"
            "🧱 <b>Build:</b> {build}\n"
            "{upd}\n\n"
            "{platform}"
        ),
    }

    def get(self, *args) -> dict:
        return self._db.get(self.strings["name"], *args)

    def set(self, *args) -> None:
        return self._db.set(self.strings["name"], *args)

    async def client_ready(self, client, db) -> None:
        self._db = db
        self._client = client
        self._me = await client.get_me()

    def __init__(self):
        self.config = loader.ModuleConfig(
            "custom_message",
            False,
            lambda: self.strings("_custom_msg_doc"),
            "custom_buttons",
            {"text": "🤵‍♀️ Support chat", "url": "https://t.me/GeekTGChat"},
            lambda: self.strings("_custom_button_doc"),
            "photo_url",
            "https://i.imgur.com/6FKsFcM.png",
            lambda: self.strings("_photo_url_doc"),
        )

    def build_message(self):
        """
        Build custom message
        """
        try:
            repo = git.Repo()
            diff = repo.git.log(["HEAD..origin", "--oneline"])
            upd = (
                "⚠️ Update required </b><code>.update</code><b>"
                if diff
                else "✅ Up-to-date"
            )
        except Exception:
            upd = ""
        ver, gitlink = utils.get_git_info()
        try:
            return (
                self.config["custom_message"]
                if self.config["custom_message"]
                else self.strings("default_message")
            ).format(
                owner=f'<a href="tg://user?id={self._me.id}">{get_display_name(self._me)}</a>',
                version=utils.get_version_raw(),
                build=f'<a href="{gitlink}">{ver[:8] or "Unknown"}</a>',
                upd=upd,
                platform=utils.get_platform_name(),
            )
        except KeyError:
            return self.strings("default_message").format(
                owner=f'<a href="tg://user?id={self._me.id}">{get_display_name(self._me)}</a>',
                version=utils.get_version_raw(),
                build=f'<a href="{gitlink}">{ver[:8] or "Unknown"}</a>',
                upd=upd,
                platform=utils.get_platform_name(),
            )

    async def info_inline_handler(self, query: GeekInlineQuery) -> None:
        """
        Send userbot info
        @allow: all
        """

        await query.answer(
            [
                aiogram.types.inline_query_result.InlineQueryResultPhoto(
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
