"""Manage the inline bot token used by InlineManager.

Adds three commands:

* ``.bottoken``       — show current bot's @username (token is never echoed)
* ``.setbottoken <token>`` — replace the inline bot with one of your own
* ``.resetbottoken``  — drop the saved token; on next restart InlineManager
  will create a fresh bot via @BotFather

Note: token strings are stored only in the local config DB
(``~/.local/share/friendly-telegram/config-<uid>.json``) — they are not
forwarded anywhere.
"""

import logging
import re

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramUnauthorizedError,
)
from telethon.tl.types import Message

from .. import loader, utils

logger = logging.getLogger(__name__)

_DB_NS = "geektg.inline"
_DB_KEY = "bot_token"
_TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")


def _redact(token: str) -> str:
    """Return a safe representation of the token for log/UI."""
    if not token or ":" not in token:
        return "<invalid>"
    bot_id, secret = token.split(":", 1)
    return f"{bot_id}:{'*' * 6}{secret[-3:]}"


@loader.tds
class BotTokenMod(loader.Module):
    """Manages the inline bot token of GeekTG."""

    strings = {
        "name": "BotToken",
        "current": "🤖 <b>Inline bot:</b> @{username}\n<code>{redacted}</code>",
        "no_token": "🤖 <b>No inline bot is configured yet.</b>",
        "no_arg": (
            "🚫 <b>Provide a token from @BotFather.</b>\n"
            "Example: <code>.setbottoken 123456:ABC-DEF…</code>"
        ),
        "bad_format": "🚫 <b>That does not look like a bot token.</b>",
        "bad_token": "🚫 <b>Telegram rejected the token:</b> <code>{err}</code>",
        "saved": (
            "✅ <b>Token saved.</b> Inline bot: @{username}.\n"
            "🔁 Run <code>.restart</code> to switch over immediately."
        ),
        "reset": (
            "🗑 <b>Token cleared.</b> A fresh bot will be created via "
            "@BotFather on the next restart."
        ),
        "no_inline": "🚫 <b>InlineManager is unavailable (started with --no-inline?).</b>",
    }

    @loader.owner
    async def bottokencmd(self, message: Message) -> None:
        """Show the currently configured inline bot."""
        token = self._db.get(_DB_NS, _DB_KEY, None)
        if not token:
            await utils.answer(message, self.strings("no_token", message))
            return
        username = await self._username_for(token)
        await utils.answer(
            message,
            self.strings("current", message).format(
                username=username or "?", redacted=_redact(token)
            ),
        )

    @loader.owner
    async def setbottokencmd(self, message: Message) -> None:
        """<token> — Replace the inline bot with your own (from @BotFather)."""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings("no_arg", message))
            return
        token = args.strip()
        if not _TOKEN_RE.match(token):
            await utils.answer(message, self.strings("bad_format", message))
            return

        username = await self._username_for(token)
        if username is None:
            await utils.answer(
                message,
                self.strings("bad_token", message).format(err="Unauthorized"),
            )
            return

        self._db.set(_DB_NS, _DB_KEY, token)
        # Hot-swap into running InlineManager so reload isn't strictly required;
        # ``.restart`` is still recommended to re-bind handlers cleanly.
        inline = getattr(self, "inline", None)
        if inline is not None:
            inline._token = token
            try:
                await inline._stop()
            except Exception:
                logger.debug("inline._stop failed", exc_info=True)
        await utils.answer(
            message, self.strings("saved", message).format(username=username)
        )

    @loader.owner
    async def resetbottokencmd(self, message: Message) -> None:
        """Forget the saved bot token (will create a new bot on next restart)."""
        self._db.set(_DB_NS, _DB_KEY, None)
        inline = getattr(self, "inline", None)
        if inline is not None:
            inline._token = False
            try:
                await inline._stop()
            except Exception:
                logger.debug("inline._stop failed", exc_info=True)
        await utils.answer(message, self.strings("reset", message))

    async def _username_for(self, token: str):
        """Validate *token* via Bot.get_me; return @username or None."""
        bot = Bot(token=token)
        try:
            me = await bot.get_me()
            return me.username
        except (TelegramUnauthorizedError, TelegramBadRequest) as exc:
            logger.warning("token validation rejected: %s", exc)
            return None
        except Exception:
            logger.exception("Bot.get_me failed")
            return None
        finally:
            try:
                await bot.session.close()
            except Exception:
                pass

    async def client_ready(self, client, db):
        self._db = db
        self._client = client
