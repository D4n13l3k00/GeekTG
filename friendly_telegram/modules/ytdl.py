"""YouTube-Dl module — download audio/video from supported sites via yt-dlp."""

# requires: yt-dlp

import asyncio
import contextlib
import functools
import os
import re
from typing import List, Optional

from telethon.tl.types import (
    DocumentAttributeAudio,
    DocumentAttributeVideo,
    Message,
)
from yt_dlp import YoutubeDL
from yt_dlp.utils import (
    ContentTooShortError,
    DownloadError,
    ExtractorError,
    GeoRestrictedError,
    MaxDownloadsReached,
    PostProcessingError,
    UnavailableVideoError,
    XAttrMetadataError,
)

from .. import loader, utils
from ..inline.types import InlineCall

_YT_RE = re.compile(r"^(https?://)?(www\.)?(youtube\.com|youtu\.?be)/.+$")
_DB_NAME = "YtDl"

# (label, yt-dlp format selector). ``None`` = audio-only path.
_VIDEO_QUALITIES = [
    ("144p", "bestvideo[height<=144]+bestaudio/best[height<=144]"),
    ("360p", "bestvideo[height<=360]+bestaudio/best[height<=360]"),
    ("720p", "bestvideo[height<=720]+bestaudio/best[height<=720]"),
    ("1080p", "bestvideo[height<=1080]+bestaudio/best[height<=1080]"),
    ("2K", "bestvideo[height<=1440]+bestaudio/best[height<=1440]"),
    ("4K", "bestvideo[height<=2160]+bestaudio/best[height<=2160]"),
    ("Best", "bestvideo+bestaudio/best"),
]

# (label, mp3 bitrate kbit/s as string — accepted by FFmpegExtractAudio).
_AUDIO_QUALITIES = [
    ("64k", "64"),
    ("128k", "128"),
    ("192k", "192"),
    ("256k", "256"),
    ("320k", "320"),
]


def _video_opts(fmt: str = "best") -> dict:
    return {
        "format": fmt,
        "addmetadata": True,
        "key": "FFmpegMetadata",
        "prefer_ffmpeg": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
        "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
        "outtmpl": "%(id)s.mp4",
        "logtostderr": False,
        "quiet": True,
        "no_warnings": True,
    }


def _audio_opts(quality: str = "320") -> dict:
    return {
        "format": "bestaudio",
        "addmetadata": True,
        "key": "FFmpegMetadata",
        "writethumbnail": True,
        "prefer_ffmpeg": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": quality,
            }
        ],
        "outtmpl": "%(id)s.mp3",
        "quiet": True,
        "logtostderr": False,
        "no_warnings": True,
    }


@loader.tds
class YtDlMod(loader.Module):
    """Youtube-Dl Module"""

    strings = {
        "name": "Youtube-Dl",
        "switch": "<b>[YouTube-Dl]</b> AutoDownload is <b>{}</b>",
        "not_chat": "<b>[YouTube-Dl]</b> This command available only in a chat",
        "preparing": "<b>[YouTube-Dl]</b> Preparing...",
        "downloading": "<b>[YouTube-Dl]</b> Downloading...",
        "noargs": "<b>[YouTube-Dl]</b> No args!",
        "pick_kind": "<b>[YouTube-Dl]</b> What to download?\n<code>{}</code>",
        "pick_video": "<b>[YouTube-Dl]</b> Video quality:\n<code>{}</code>",
        "pick_audio": "<b>[YouTube-Dl]</b> Audio bitrate:\n<code>{}</code>",
        "content_too_short": "<b>[YouTube-Dl]</b> Downloading content too short!",
        "geoban": (
            "<b>[YouTube-Dl]</b> The video is not available "
            "for your geographical location due to geographical "
            "restrictions set by the website!"
        ),
        "maxdlserr": "<b>[YouTube-Dl]</b> Download limit reached",
        "pperr": "<b>[YouTube-Dl]</b> Error in post-processing!",
        "noformat": (
            "<b>[YouTube-Dl]</b> Media is not available in the requested format"
        ),
        "xameerr": "<b>[YouTube-Dl]</b> {0.code}: {0.msg}\n{0.reason}",
        "exporterr": "<b>[YouTube-Dl]</b> Error when exporting video",
        "err": "<b>[YouTube-Dl]</b> {}",
        "err2": "<b>[YouTube-Dl]</b> {}: {}",
    }

    # ---------------------------------------------------------------- helpers

    def _chats(self) -> List[int]:
        return self.ctx.db.get(_DB_NAME, "chats", [])

    def _save_chats(self, chats: List[int]) -> None:
        self.ctx.db.set(_DB_NAME, "chats", chats)

    async def _resolve_url(self, m: Message, is_watcher: bool) -> Optional[str]:
        if is_watcher:
            text = m.raw_text or ""
            return text if _YT_RE.match(text) else None
        reply = await m.get_reply_message()
        args = utils.get_args_raw(m)
        return args or (reply.raw_text if reply else None) or None

    async def _show_error_and_dismiss(self, m: Message, key: str, *args) -> None:
        err_msg = await utils.answer(m, self.strings(key, m).format(*args))
        if isinstance(err_msg, list):
            await asyncio.sleep(5)
            for msg in err_msg:
                with contextlib.suppress(Exception):
                    await msg.delete()
        elif err_msg is not None:
            with contextlib.suppress(Exception):
                await err_msg.delete()

    # --------------------------------------------------------------- commands

    async def swripcmd(self, m: Message):
        "Switch autodownload in the chat"
        if not m.chat:
            return await utils.answer(m, self.strings("not_chat"))
        chats = self._chats()
        if m.chat_id in chats:
            chats.remove(m.chat_id)
            is_on = False
        else:
            chats.append(m.chat_id)
            is_on = True
        self._save_chats(chats)
        await utils.answer(m, self.strings("switch").format("ON" if is_on else "OFF"))

    async def ripvcmd(self, m: Message):
        """.ripv <link / reply_to_link> - download video (best quality)"""
        url = await self._resolve_url(m, is_watcher=False)
        if not url:
            return await utils.answer(m, self.strings("noargs", m))
        await self._download_video(m, url, "best", reply=await m.get_reply_message())

    async def ripacmd(self, m: Message):
        """.ripa <link / reply_to_link> - download audio (mp3 320k)"""
        url = await self._resolve_url(m, is_watcher=False)
        if not url:
            return await utils.answer(m, self.strings("noargs", m))
        await self._download_audio(m, url, "320", reply=await m.get_reply_message())

    async def ytdlcmd(self, m: Message):
        """.ytdl <link / reply_to_link> - choose quality via inline buttons"""
        url = await self._resolve_url(m, is_watcher=False)
        if not url:
            return await utils.answer(m, self.strings("noargs", m))

        reply = await m.get_reply_message()
        reply_id = reply.id if reply else None

        await self.inline.form(
            self.strings("pick_kind").format(utils.escape_html(url)),
            message=m,
            reply_markup=self._kind_markup(url, reply_id),
        )

    # ---------------------------------------------------- inline keyboards

    def _chunk(self, buttons: list, per_row: int = 2) -> list:
        return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]

    def _kind_markup(self, url: str, reply_id: Optional[int]) -> list:
        return [
            [
                {
                    "text": "🎬 Video",
                    "callback": self._inline_show_video,
                    "args": (url, reply_id),
                },
                {
                    "text": "🎵 Audio",
                    "callback": self._inline_show_audio,
                    "args": (url, reply_id),
                },
            ],
            [{"text": "✖ Cancel", "callback": self._inline_cancel}],
        ]

    def _video_markup(self, url: str, reply_id: Optional[int]) -> list:
        buttons = [
            {
                "text": f"🎬 {label}",
                "callback": self._inline_pick,
                "args": (url, "video", fmt, reply_id),
            }
            for label, fmt in _VIDEO_QUALITIES
        ]
        rows = self._chunk(buttons, 2)
        rows.append(
            [
                {
                    "text": "« Back",
                    "callback": self._inline_back,
                    "args": (url, reply_id),
                },
                {"text": "✖ Cancel", "callback": self._inline_cancel},
            ]
        )
        return rows

    def _audio_markup(self, url: str, reply_id: Optional[int]) -> list:
        buttons = [
            {
                "text": f"🎵 {label}",
                "callback": self._inline_pick,
                "args": (url, "audio", quality, reply_id),
            }
            for label, quality in _AUDIO_QUALITIES
        ]
        rows = self._chunk(buttons, 2)
        rows.append(
            [
                {
                    "text": "« Back",
                    "callback": self._inline_back,
                    "args": (url, reply_id),
                },
                {"text": "✖ Cancel", "callback": self._inline_cancel},
            ]
        )
        return rows

    async def watcher(self, m: Message):
        if not isinstance(m, Message):
            return
        if m.chat_id in self._chats():
            url = await self._resolve_url(m, is_watcher=True)
            if not url:
                return
            await self._download_video(m, url, "best", reply=None)

    # -------------------------------------------------------- inline callbacks

    async def _inline_cancel(self, call: InlineCall) -> None:
        await call.answer("Cancelled")
        with contextlib.suppress(Exception):
            await call.delete()

    async def _inline_back(
        self, call: InlineCall, url: str, reply_id: Optional[int]
    ) -> None:
        await call.answer()
        with contextlib.suppress(Exception):
            await call.edit(
                self.strings("pick_kind").format(utils.escape_html(url)),
                reply_markup=self._kind_markup(url, reply_id),
            )

    async def _inline_show_video(
        self, call: InlineCall, url: str, reply_id: Optional[int]
    ) -> None:
        await call.answer()
        with contextlib.suppress(Exception):
            await call.edit(
                self.strings("pick_video").format(utils.escape_html(url)),
                reply_markup=self._video_markup(url, reply_id),
            )

    async def _inline_show_audio(
        self, call: InlineCall, url: str, reply_id: Optional[int]
    ) -> None:
        await call.answer()
        with contextlib.suppress(Exception):
            await call.edit(
                self.strings("pick_audio").format(utils.escape_html(url)),
                reply_markup=self._audio_markup(url, reply_id),
            )

    async def _inline_pick(
        self,
        call: InlineCall,
        url: str,
        kind: str,
        param: Optional[str],
        reply_id: Optional[int],
    ) -> None:
        await call.answer(f"Downloading {kind}...")
        # form dict is injected by the inline manager; falls back to the
        # callback's own chat if absent (defensive — should not happen).
        form = getattr(call, "form", None) or {}
        chat = (
            form.get("chat") or getattr(call.message, "chat", None) or call.from_user.id
        )
        with contextlib.suppress(Exception):
            await call.delete()

        status = await self.ctx.client.send_message(chat, self.strings("preparing"))
        reply = None
        if reply_id is not None:
            with contextlib.suppress(Exception):
                reply = await self.ctx.client.get_messages(chat, ids=reply_id)

        if kind == "audio":
            await self._download_audio(status, url, param or "320", reply=reply)
        else:
            await self._download_video(status, url, param or "best", reply=reply)

    # ----------------------------------------------------------------- core

    async def _download_video(
        self, m: Message, url: str, fmt: str, reply: Optional[Message]
    ) -> None:
        m = await utils.answer(m, self.strings("preparing", m))
        if isinstance(m, list):
            m = m[0]
        rip_data = await self._extract(m, url, _video_opts(fmt))
        if rip_data is None:
            return
        await self._send_video(m, rip_data, reply)

    async def _download_audio(
        self, m: Message, url: str, quality: str, reply: Optional[Message]
    ) -> None:
        m = await utils.answer(m, self.strings("preparing", m))
        if isinstance(m, list):
            m = m[0]
        rip_data = await self._extract(m, url, _audio_opts(quality))
        if rip_data is None:
            return
        await self._send_audio(m, rip_data, reply)

    async def _extract(self, m: Message, url: str, opts: dict) -> Optional[dict]:
        loop = asyncio.get_event_loop()
        try:
            await utils.answer(m, self.strings("downloading", m))
            with YoutubeDL(opts) as rip:
                return await loop.run_in_executor(
                    None, functools.partial(rip.extract_info, url)
                )
        except DownloadError as e:
            await self._show_error_and_dismiss(m, "err", str(e))
        except ContentTooShortError:
            await self._show_error_and_dismiss(m, "content_too_short")
        except GeoRestrictedError:
            await self._show_error_and_dismiss(m, "geoban")
        except MaxDownloadsReached:
            await self._show_error_and_dismiss(m, "maxdlserr")
        except PostProcessingError:
            await self._show_error_and_dismiss(m, "pperr")
        except UnavailableVideoError:
            await self._show_error_and_dismiss(m, "noformat")
        except XAttrMetadataError as e:
            await self._show_error_and_dismiss(m, "xameerr", e)
        except ExtractorError:
            await self._show_error_and_dismiss(m, "exporterr")
        except Exception as e:
            await self._show_error_and_dismiss(m, "err2", type(e).__name__, str(e))
        return None

    async def _send_audio(
        self, m: Message, rip_data: dict, reply: Optional[Message]
    ) -> None:
        # yt-dlp's ExtractAudio postprocessor produces ``<id>.mp3.mp3`` because
        # ``outtmpl`` already ends in ``.mp3``. Detect both forms.
        candidates = [f"{rip_data['id']}.mp3.mp3", f"{rip_data['id']}.mp3"]
        path = next((p for p in candidates if os.path.exists(p)), None)
        if not path:
            return await utils.answer(m, self.strings("err").format("file not found"))

        try:
            with open(path, "rb") as f:
                await utils.answer(
                    m,
                    f,
                    supports_streaming=True,
                    reply_to=reply.id if reply else None,
                    attributes=(
                        DocumentAttributeAudio(
                            duration=int(rip_data.get("duration") or 0),
                            title=str(rip_data.get("title") or ""),
                            performer=str(rip_data.get("uploader") or "Unknown"),
                        ),
                    ),
                )
        finally:
            with contextlib.suppress(OSError):
                os.remove(path)

    async def _send_video(
        self, m: Message, rip_data: dict, reply: Optional[Message]
    ) -> None:
        path = f"{rip_data['id']}.mp4"
        if not os.path.exists(path):
            return await utils.answer(m, self.strings("err").format("file not found"))

        downloads = rip_data.get("requested_downloads") or [{}]
        try:
            with open(path, "rb") as f:
                await utils.answer(
                    m,
                    f,
                    reply_to=reply.id if reply else None,
                    supports_streaming=True,
                    attributes=(
                        DocumentAttributeVideo(
                            w=downloads[0].get("width") or 0,
                            h=downloads[0].get("height") or 0,
                            duration=int(rip_data.get("duration") or 0),
                        ),
                    ),
                )
        finally:
            with contextlib.suppress(OSError):
                os.remove(path)
