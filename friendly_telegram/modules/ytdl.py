"""YouTube-Dl module — download audio/video from supported sites via yt-dlp."""

# requires: yt-dlp

import asyncio
import contextlib
import functools
import os
import re
from typing import Any, Dict, List, Optional, Tuple

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

# Audio-only quick-pick presets used by the legacy .ripa command and as a
# fallback when a site exposes no per-format audio streams.
_AUDIO_PRESETS = [
    ("64 kbps", "64"),
    ("128 kbps", "128"),
    ("192 kbps", "192"),
    ("256 kbps", "256"),
    ("320 kbps", "320"),
]

_QUIET_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "logtostderr": False,
    "noprogress": True,
}


def _probe_opts() -> dict:
    return {
        **_QUIET_OPTS,
        "skip_download": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
    }


def _video_opts(fmt: str) -> dict:
    return {
        **_QUIET_OPTS,
        "format": fmt,
        "addmetadata": True,
        "key": "FFmpegMetadata",
        "prefer_ffmpeg": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
        "merge_output_format": "mp4",
        "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
        "outtmpl": "%(id)s.%(ext)s",
    }


def _audio_opts(quality: str = "320", fmt_id: Optional[str] = None) -> dict:
    return {
        **_QUIET_OPTS,
        "format": fmt_id or "bestaudio",
        "addmetadata": True,
        "key": "FFmpegMetadata",
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
    }


def _human_size(n: Optional[float]) -> str:
    if not n:
        return ""
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    n = float(n)
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    return f"{n:.1f}{units[i]}"


def _human_duration(secs: Optional[int]) -> str:
    if not secs:
        return ""
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _video_label(fmt: dict) -> str:
    """Human-friendly label for one video format dict from yt-dlp."""
    h = fmt.get("height") or 0
    fps = fmt.get("fps") or 0
    ext = fmt.get("ext") or ""
    size = _human_size(fmt.get("filesize") or fmt.get("filesize_approx"))
    parts: List[str] = []
    if h > 0:
        parts.append(f"{h}p{int(fps)}" if fps and fps > 30 else f"{h}p")
    if ext:
        parts.append(ext)
    if size:
        parts.append(size)
    if not parts:
        # Last-ditch label so the button at least shows *something*.
        parts.append(fmt.get("format_note") or fmt.get("format_id") or "video")
    return " · ".join(parts)


def _audio_label(fmt: dict) -> str:
    abr = fmt.get("abr") or 0
    ext = fmt.get("ext") or ""
    size = _human_size(fmt.get("filesize") or fmt.get("filesize_approx"))
    parts = []
    if abr:
        parts.append(f"{int(abr)}k")
    if ext:
        parts.append(ext)
    if size:
        parts.append(size)
    return " · ".join(parts) if parts else fmt.get("format_id", "?")


def _classify_formats(info: dict) -> Tuple[List[dict], List[dict]]:
    """Split yt-dlp ``formats`` into (video, audio-only).

    Video entries are deduped by (height, fps) so we don't get a wall of
    50 buttons. When height is unknown we keep the entry under a synthetic
    ``-1`` bucket so single-stream sources (Instagram reels, plain mp4s,
    etc.) still surface in the picker.
    """
    formats = info.get("formats") or []
    video_by_key: Dict[Tuple[int, int], dict] = {}
    audio: List[dict] = []
    for f in formats:
        vcodec = f.get("vcodec") or "none"
        acodec = f.get("acodec") or "none"
        if vcodec != "none":
            h = f.get("height") or -1
            fps = int(f.get("fps") or 0)
            key = (h, fps)
            cur = video_by_key.get(key)
            if cur is None:
                video_by_key[key] = f
                continue
            cur_has_a = (cur.get("acodec") or "none") != "none"
            new_has_a = acodec != "none"
            if new_has_a and not cur_has_a:
                video_by_key[key] = f
                continue
            if cur_has_a and not new_has_a:
                continue
            cur_size = cur.get("filesize") or cur.get("filesize_approx") or 0
            new_size = f.get("filesize") or f.get("filesize_approx") or 0
            if new_size > cur_size:
                video_by_key[key] = f
        elif acodec != "none":
            audio.append(f)

    # Some extractors don't expose a ``formats`` array at all — they just
    # set the top-level ``url``/``ext`` fields. Treat that as a single
    # "best available" video entry so the picker still works.
    if not video_by_key and not audio and info.get("url"):
        return [info], []

    videos = sorted(video_by_key.values(), key=lambda f: f.get("height") or 0)
    audios = sorted(audio, key=lambda f: f.get("abr") or 0)
    return videos, audios


@loader.tds
class YtDlMod(loader.Module):
    """Youtube-Dl Module"""

    strings = {
        "name": "Youtube-Dl",
        "switch": "<b>[YouTube-Dl]</b> AutoDownload is <b>{}</b>",
        "not_chat": "<b>[YouTube-Dl]</b> This command available only in a chat",
        "preparing": "<b>[YouTube-Dl]</b> Preparing...",
        "probing": "<b>[YouTube-Dl]</b> Probing formats...",
        "downloading": "<b>[YouTube-Dl]</b> Downloading...",
        "noargs": "<b>[YouTube-Dl]</b> No args!",
        "no_formats": "<b>[YouTube-Dl]</b> No downloadable formats found",
        "pick_kind": (
            "<b>[YouTube-Dl]</b> <b>{title}</b>\n"
            "👤 <i>{uploader}</i>"
            "{duration}"
            "\n\n<code>{url}</code>\n\nWhat to download?"
        ),
        "pick_video": "<b>[YouTube-Dl]</b> <b>{title}</b>\n\nVideo quality:",
        "pick_audio": "<b>[YouTube-Dl]</b> <b>{title}</b>\n\nAudio bitrate:",
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

    async def _show_error(self, m: Message, key: str, *args) -> None:
        """Print an error and leave it on screen. Don't auto-delete — the
        user needs to *see* what went wrong."""
        await utils.answer(m, self.strings(key, m).format(*args))

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
        """.ytdl <link / reply_to_link> - probe formats and pick via inline buttons"""
        url = await self._resolve_url(m, is_watcher=False)
        if not url:
            return await utils.answer(m, self.strings("noargs", m))

        reply = await m.get_reply_message()
        reply_id = reply.id if reply else None

        progress = await utils.answer(m, self.strings("probing"))
        if isinstance(progress, list):
            progress = progress[0]

        info = await self._probe(progress, url)
        if info is None:
            # _probe → _extract already wrote the error onto ``progress``.
            return

        videos, audios = _classify_formats(info)
        if not videos and not audios:
            return await utils.answer(progress, self.strings("no_formats"))

        # Stash so the inline callbacks (which only carry args) can find it.
        token = info.get("id") or os.urandom(8).hex()
        self._cache[token] = {
            "url": url,
            "info": info,
            "videos": videos,
            "audios": audios,
        }
        # Best-effort eviction of the oldest entry once we hit the cap.
        if len(self._cache) > 32:
            self._cache.pop(next(iter(self._cache)))

        title = utils.escape_html(info.get("title") or "Untitled")
        uploader = utils.escape_html(info.get("uploader") or "Unknown")
        duration = info.get("duration")
        duration_str = (
            f"\n⏱ <code>{_human_duration(duration)}</code>" if duration else ""
        )
        # Photo captions are capped at 1024 chars; long share-links with
        # tracking params (Instagram ?igsh=…) can blow past that. Strip the
        # query string for display and ellipsize as a final guard.
        display_url = url.split("?", 1)[0]
        if len(display_url) > 200:
            display_url = display_url[:197] + "..."

        caption = self.strings("pick_kind").format(
            title=title,
            uploader=uploader,
            duration=duration_str,
            url=utils.escape_html(display_url),
        )

        # Keep the placeholder until the inline form really lands — the form
        # call replaces it implicitly when message=m_orig is the same one.
        # We pass ``progress`` (already an out-message) so the form swap
        # happens cleanly without leaving an orphan "Probing..." behind.
        markup = self._kind_markup(token, reply_id, videos, audios)
        thumb = info.get("thumbnail")
        result = await self.inline.form(
            caption,
            message=progress,
            reply_markup=markup,
            photo=thumb or None,
        )
        # Some sites hand out thumbnail URLs that BotAPI rejects (CDN auth,
        # bad cert, redirect, >5MB). Fall back to a text-only form so the
        # picker still works.
        if result is False and thumb:
            result = await self.inline.form(
                caption,
                message=progress,
                reply_markup=markup,
            )
        if result is False:
            # inline.form already printed its own error onto ``progress``.
            self._cache.pop(token, None)

    async def watcher(self, m: Message):
        if not isinstance(m, Message):
            return
        if m.chat_id in self._chats():
            url = await self._resolve_url(m, is_watcher=True)
            if not url:
                return
            await self._download_video(m, url, "best", reply=None)

    # ---------------------------------------------------- inline keyboards

    def _chunk(self, buttons: list, per_row: int = 2) -> list:
        return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]

    def _kind_markup(
        self,
        token: str,
        reply_id: Optional[int],
        videos: List[dict],
        audios: List[dict],
    ) -> list:
        rows = []
        if videos:
            rows.append(
                [
                    {
                        "text": f"🎬 Video ({len(videos)} options)",
                        "callback": self._inline_show_video,
                        "args": (token, reply_id),
                    }
                ]
            )
        # mp3 path is always available via FFmpegExtractAudio fallback.
        n = len(audios) if audios else len(_AUDIO_PRESETS)
        rows.append(
            [
                {
                    "text": f"🎵 Audio ({n} options)",
                    "callback": self._inline_show_audio,
                    "args": (token, reply_id),
                }
            ]
        )
        rows.append([{"text": "✖ Cancel", "callback": self._inline_cancel}])
        return rows

    def _video_markup(
        self, token: str, reply_id: Optional[int], videos: List[dict]
    ) -> list:
        buttons = [
            {
                "text": f"🎬 {_video_label(f)}",
                "callback": self._inline_pick,
                "args": (token, "video", f["format_id"], reply_id),
            }
            for f in videos
        ]
        rows = self._chunk(buttons, 2)
        rows.append(
            [
                {
                    "text": "« Back",
                    "callback": self._inline_back,
                    "args": (token, reply_id),
                },
                {"text": "✖ Cancel", "callback": self._inline_cancel},
            ]
        )
        return rows

    def _audio_markup(
        self, token: str, reply_id: Optional[int], audios: List[dict]
    ) -> list:
        if audios:
            buttons = [
                {
                    "text": f"🎵 {_audio_label(f)}",
                    "callback": self._inline_pick,
                    "args": (token, "audio", f["format_id"], reply_id),
                }
                for f in audios
            ]
        else:
            # No per-format audio streams — fall back to bestaudio + transcode
            # to the requested mp3 bitrate (preset-based path).
            buttons = [
                {
                    "text": f"🎵 {label}",
                    "callback": self._inline_pick,
                    "args": (token, "audio_preset", quality, reply_id),
                }
                for label, quality in _AUDIO_PRESETS
            ]
        rows = self._chunk(buttons, 2)
        rows.append(
            [
                {
                    "text": "« Back",
                    "callback": self._inline_back,
                    "args": (token, reply_id),
                },
                {"text": "✖ Cancel", "callback": self._inline_cancel},
            ]
        )
        return rows

    # -------------------------------------------------------- inline callbacks

    async def _inline_cancel(self, call: InlineCall) -> None:
        await call.answer("Cancelled")
        with contextlib.suppress(Exception):
            await call.delete()

    def _entry(self, token: str) -> Optional[Dict[str, Any]]:
        return self._cache.get(token)

    async def _inline_back(
        self, call: InlineCall, token: str, reply_id: Optional[int]
    ) -> None:
        await call.answer()
        entry = self._entry(token)
        if not entry:
            with contextlib.suppress(Exception):
                await call.delete()
            return
        info = entry["info"]
        title = utils.escape_html(info.get("title") or "Untitled")
        uploader = utils.escape_html(info.get("uploader") or "Unknown")
        duration = info.get("duration")
        duration_str = (
            f"\n⏱ <code>{_human_duration(duration)}</code>" if duration else ""
        )
        with contextlib.suppress(Exception):
            await call.edit(
                self.strings("pick_kind").format(
                    title=title,
                    uploader=uploader,
                    duration=duration_str,
                    url=utils.escape_html(entry["url"]),
                ),
                reply_markup=self._kind_markup(
                    token, reply_id, entry["videos"], entry["audios"]
                ),
            )

    async def _inline_show_video(
        self, call: InlineCall, token: str, reply_id: Optional[int]
    ) -> None:
        await call.answer()
        entry = self._entry(token)
        if not entry:
            return
        title = utils.escape_html(entry["info"].get("title") or "Untitled")
        with contextlib.suppress(Exception):
            await call.edit(
                self.strings("pick_video").format(title=title),
                reply_markup=self._video_markup(token, reply_id, entry["videos"]),
            )

    async def _inline_show_audio(
        self, call: InlineCall, token: str, reply_id: Optional[int]
    ) -> None:
        await call.answer()
        entry = self._entry(token)
        if not entry:
            return
        title = utils.escape_html(entry["info"].get("title") or "Untitled")
        with contextlib.suppress(Exception):
            await call.edit(
                self.strings("pick_audio").format(title=title),
                reply_markup=self._audio_markup(token, reply_id, entry["audios"]),
            )

    async def _inline_pick(
        self,
        call: InlineCall,
        token: str,
        kind: str,
        param: str,
        reply_id: Optional[int],
    ) -> None:
        await call.answer(f"Downloading {kind}...")
        entry = self._entry(token)
        url = entry["url"] if entry else None

        form = getattr(call, "form", None) or {}
        chat = (
            form.get("chat") or getattr(call.message, "chat", None) or call.from_user.id
        )
        with contextlib.suppress(Exception):
            await call.delete()

        if not url:
            return

        status = await self.ctx.client.send_message(chat, self.strings("preparing"))
        reply = None
        if reply_id is not None:
            with contextlib.suppress(Exception):
                reply = await self.ctx.client.get_messages(chat, ids=reply_id)

        if kind == "video":
            # Pair the chosen video stream with the best audio so we always
            # get muxed mp4 even if the picked format is video-only.
            await self._download_video(status, url, f"{param}+bestaudio/{param}", reply)
        elif kind == "audio":
            await self._download_audio(status, url, "320", reply, fmt_id=param)
        else:  # audio_preset
            await self._download_audio(status, url, param, reply)

        # Drop cache entry once the user committed to a download.
        self._cache.pop(token, None)

    # ----------------------------------------------------------------- core

    async def client_ready(self, _, __):
        # token → {url, info, videos, audios}; bounded, evicted FIFO.
        self._cache: Dict[str, Dict[str, Any]] = {}

    async def _probe(self, m: Message, url: str) -> Optional[dict]:
        return await self._extract(m, url, _probe_opts(), status_key="probing")

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
        self,
        m: Message,
        url: str,
        quality: str,
        reply: Optional[Message],
        fmt_id: Optional[str] = None,
    ) -> None:
        m = await utils.answer(m, self.strings("preparing", m))
        if isinstance(m, list):
            m = m[0]
        rip_data = await self._extract(m, url, _audio_opts(quality, fmt_id))
        if rip_data is None:
            return
        await self._send_audio(m, rip_data, reply)

    async def _extract(
        self, m: Message, url: str, opts: dict, status_key: str = "downloading"
    ) -> Optional[dict]:
        loop = asyncio.get_event_loop()
        try:
            await utils.answer(m, self.strings(status_key, m))
            with YoutubeDL(opts) as rip:
                return await loop.run_in_executor(
                    None, functools.partial(rip.extract_info, url)
                )
        except DownloadError as e:
            await self._show_error(m, "err", str(e))
        except ContentTooShortError:
            await self._show_error(m, "content_too_short")
        except GeoRestrictedError:
            await self._show_error(m, "geoban")
        except MaxDownloadsReached:
            await self._show_error(m, "maxdlserr")
        except PostProcessingError:
            await self._show_error(m, "pperr")
        except UnavailableVideoError:
            await self._show_error(m, "noformat")
        except XAttrMetadataError as e:
            await self._show_error(m, "xameerr", e)
        except ExtractorError:
            await self._show_error(m, "exporterr")
        except Exception as e:
            await self._show_error(m, "err2", type(e).__name__, str(e))
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
        # merge_output_format=mp4 + FFmpegVideoConvertor land the file as
        # <id>.mp4; if the source was already mp4-compatible yt-dlp may skip
        # the convertor and leave the original ext. Probe both.
        candidates = [f"{rip_data['id']}.mp4"]
        for ext in ("webm", "mkv", "mov"):
            candidates.append(f"{rip_data['id']}.{ext}")
        path = next((p for p in candidates if os.path.exists(p)), None)
        if not path:
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
