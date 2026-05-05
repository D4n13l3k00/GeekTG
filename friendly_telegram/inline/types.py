"""Helpers for the InlineManager: light-weight wrappers and the
``edit`` / ``delete`` / ``unload`` / ``answer`` / ``custom_next_handler``
functions that get bound onto callback / inline-query objects via
``functools.partial(self=manager, ...)``.

These are stateless on their own — they receive the manager instance
through the ``self`` kwarg at call time, so they're safe to live in
their own module without circular imports.
"""

import asyncio
import io
import logging
import random
from importlib.resources import files
from types import FunctionType
from typing import Any, List, Union

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InputMediaPhoto,
    LinkPreviewOptions,
)
from aiogram.types import Message as AiogramMessage


def _is_not_modified(exc: TelegramBadRequest) -> bool:
    return "message is not modified" in (exc.message or "").lower()


def _is_invalid_query(exc: TelegramBadRequest) -> bool:
    msg = (exc.message or "").lower()
    return "query is too old" in msg or "query_id_invalid" in msg


def _is_message_id_invalid(exc: TelegramBadRequest) -> bool:
    return "message_id_invalid" in (exc.message or "").lower()


logger = logging.getLogger(__name__)


_AVATAR_URL = (
    "https://github.com/D4n13l3k00/GeekTG/raw/master/"
    "friendly_telegram/web/static/bot_avatar.png"
)
_avatar_bytes: "bytes | None" = None


def _load_avatar() -> "io.BytesIO":
    """Return a fresh ``BytesIO`` of the inline-bot avatar.

    Lazy: the bytes are only read on first call (typically during
    ``@BotFather`` bot creation, not at every startup). Prefers the file
    bundled with the package and only hits the network if it's missing —
    so an offline boot or a custom build without static assets still
    works without freezing on import.
    """
    global _avatar_bytes
    if _avatar_bytes is None:
        try:
            _avatar_bytes = (
                files("friendly_telegram.web")
                .joinpath("static/bot_avatar.png")
                .read_bytes()
            )
        except (FileNotFoundError, ModuleNotFoundError, OSError):
            logger.warning("Bundled avatar not found, downloading from GitHub")
            import requests

            _avatar_bytes = requests.get(_AVATAR_URL, timeout=10).content
    buf = io.BytesIO(_avatar_bytes)
    buf.name = "avatar.png"
    return buf


class InlineCall:
    def __init__(self):
        self.delete = None
        self.unload = None
        self.edit = None
        super().__init__()


class BotMessage(AiogramMessage):
    pass


class GeekInlineQuery:
    def __init__(self, inline_query: InlineQuery) -> None:
        self.inline_query = inline_query

        # Inherit original `InlineQuery` attributes for easy access
        for attr in dir(inline_query):
            if attr.startswith("__") and attr.endswith("__"):
                continue  # ignore magic attrs

            try:
                setattr(self, attr, getattr(inline_query, attr))
            except AttributeError:
                pass  # some native attrs aren't writable; skip silently

        self.args = (
            self.inline_query.query.split(maxsplit=1)[1]
            if len(self.inline_query.query.split()) > 1
            else ""
        )


def rand(size: int) -> str:
    """Return a random alphanumeric string of length ``size``."""
    return "".join(
        [random.choice("abcdefghijklmnopqrstuvwxyz1234567890") for _ in range(size)]
    )


def array_sum(array: list) -> Any:
    """Flatten one level of nested lists."""
    result = []
    for item in array:
        result += item
    return result


async def edit(
    text: str,
    reply_markup: List[List[dict]] = None,
    force_me: Union[bool, None] = None,
    always_allow: Union[List[int], None] = None,
    self: Any = None,
    query: Any = None,
    form: Any = None,
    form_uid: Any = None,
    inline_message_id: Union[str, None] = None,
    disable_web_page_preview: bool = True,
) -> None:
    """Edit an inline message via the bot.

    Do not pass ``self``, ``query``, ``form``, ``form_uid`` —
    they're injected by the manager via ``functools.partial``.
    """
    if reply_markup:
        if isinstance(reply_markup, dict):
            reply_markup = [[reply_markup]]
        if isinstance(reply_markup[0], dict):
            reply_markup = [[_] for _ in reply_markup]
    if reply_markup is None:
        reply_markup = []

    if not isinstance(text, str):
        logger.error("Invalid type for `text`")
        return False

    if isinstance(reply_markup, list):
        form["buttons"] = reply_markup
    if isinstance(force_me, bool):
        form["force_me"] = force_me
    if isinstance(always_allow, list):
        form["always_allow"] = always_allow
    try:
        await self.bot.edit_message_text(
            text=text,
            inline_message_id=inline_message_id or query.inline_message_id,
            link_preview_options=LinkPreviewOptions(
                is_disabled=disable_web_page_preview
            ),
            reply_markup=self._generate_markup(form_uid),
        )
    except TelegramRetryAfter as e:
        logger.info(f"Sleeping {e.retry_after}s on aiogram FloodWait...")
        await asyncio.sleep(e.retry_after)
        return await edit(
            text,
            reply_markup,
            force_me,
            always_allow,
            self,
            query,
            form,
            form_uid,
            inline_message_id,
        )
    except TelegramBadRequest as e:
        if _is_not_modified(e):
            try:
                await query.answer()
            except TelegramBadRequest as e2:
                if not _is_invalid_query(e2):
                    raise
        elif _is_message_id_invalid(e):
            try:
                await query.answer(
                    "I should have edited some message, but it is deleted :("
                )
            except TelegramBadRequest as e2:
                if not _is_invalid_query(e2):
                    raise
        else:
            raise


async def custom_next_handler(
    call: CallbackQuery,
    caption: str = None,
    btn_call_data: str = None,
    self=None,
    func: FunctionType = None,
) -> None:
    try:
        new_url = await func()
        if not isinstance(new_url, (str, bool)):
            raise Exception(
                f"Invalid type returned by `next_handler`."
                f"Expected `str` or `False`, got `{type(new_url)}`"
            )
    except Exception:
        logger.exception("Exception while trying to parse new photo")
        await call.answer("Error occurred", show_alert=True)
        return

    if not new_url:
        await call.answer("No photos left", show_alert=True)
        return

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Next ➡️", callback_data=btn_call_data)]
        ]
    )

    _caption = (
        caption if isinstance(caption, str) or not callable(caption) else caption()
    )

    try:
        await self.bot.edit_message_media(
            inline_message_id=call.inline_message_id,
            media=InputMediaPhoto(media=new_url, caption=_caption),
            reply_markup=markup,
        )
    except Exception:
        logger.exception("Exception while trying to edit media")
        await call.answer("Error occurred", show_alert=True)
        return


async def delete(self: Any = None, form: Any = None, form_uid: Any = None) -> bool:
    """Internal helper: delete the form's chat message and forget the form.

    ``self``, ``form``, ``form_uid`` are injected by the manager.
    """
    try:
        await self._client.delete_messages(form["chat"], [form["message_id"]])
        del self._forms[form_uid]
    except Exception:
        return False
    return True


async def unload(self: Any = None, form_uid: Any = None) -> bool:
    """Internal helper: forget the form without deleting the chat message."""
    try:
        del self._forms[form_uid]
    except Exception:
        return False
    return True


async def answer(
    text: str = None,
    mod: Any = None,
    message: AiogramMessage = None,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
    **kwargs,
) -> bool:
    try:
        await mod.bot.send_message(
            chat_id=message.chat.id,
            text=text,
            parse_mode=parse_mode,
            link_preview_options=LinkPreviewOptions(
                is_disabled=disable_web_page_preview
            ),
            **kwargs,
        )
    except Exception:
        return False
    return True
