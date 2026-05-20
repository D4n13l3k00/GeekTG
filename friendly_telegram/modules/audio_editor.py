"""Edit audio files: bass-boost, distort, echo, speed, cut, convert, and more.

Requires the ``media`` extra (pydub, numpy) plus aiohttp and audioop-lts.
Install with: pip install pydub numpy aiohttp audioop-lts
"""

import io
import logging
import math
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Union, cast

import numpy as np
from pydub import AudioSegment, effects
from telethon import TelegramClient, types
from telethon.tl.custom import Message

from .. import loader, utils

logger = logging.getLogger(__name__)

_LEVEL_RE = re.compile(r"^\d+(\.\d+)?$")
_CUT_RE = re.compile(r"^(?P<start>\d+)?:(?P<end>\d+)?$")

Transform = Callable[[AudioSegment], Union[AudioSegment, Awaitable[AudioSegment]]]


def _unwrap(reply) -> Optional[Message]:
    """``utils.answer`` returns list/tuple — unwrap to the first message."""
    if reply is None:
        return None
    if isinstance(reply, (list, tuple)):
        return reply[0] if reply else None
    return reply


@dataclass
class _AudioCtx:
    audio: AudioSegment
    message: Message  # progress message we keep editing
    reply: Message  # original audio message
    duration: int
    voice: bool
    pref: str


def _retime(audio: AudioSegment, factor: float) -> AudioSegment:
    """Change playback speed by ``factor`` while preserving frame rate."""
    spawned = audio._spawn(
        audio.raw_data,
        overrides={"frame_rate": int(audio.frame_rate * factor)},
    )
    return spawned.set_frame_rate(audio.frame_rate)


@loader.tds
class AudioEditorMod(loader.Module):
    """Edit audio: bass, distort, echo, speed, reverse, cut, convert, and more."""

    strings = {
        "name": "AudioEditor",
        "downloading": "<b>[{}]</b> Downloading...",
        "working": "<b>[{}]</b> Working...",
        "exporting": "<b>[{}]</b> Exporting...",
        "set_value": "<b>[{}]</b> Specify the level from {} to {}",
        "reply": "<b>[{}]</b> Reply to an audio message",
        "set_fmt": "<b>[{}]</b> Specify the output audio format (e.g. mp3)",
        "set_time": "<b>[{}]</b> Specify time as start(ms):end(ms)",
    }

    # ------------------------------------------------------------------ helpers

    async def _apply(
        self,
        message: Message,
        pref: str,
        transform: Transform,
        *,
        title: Optional[str] = None,
        fmt: str = "mp3",
        duration_factor: float = 1.0,
    ) -> None:
        """Download replied audio, run ``transform``, send the result."""
        ctx = await self._get_audio(message, pref)
        if not ctx:
            return
        out = transform(ctx.audio)
        if hasattr(out, "__await__"):
            out = await out  # type: ignore[assignment]
        fs = round(ctx.duration * duration_factor) if duration_factor != 1.0 else None
        await self._send_audio(
            ctx, cast(AudioSegment, out), title or ctx.pref, fs=fs, fmt=fmt
        )

    def _parse_level(
        self, args: Optional[str], default: float, label: str
    ) -> Optional[float]:
        """Return parsed float level in (1, 100], or None on bad input."""
        if not args:
            return default
        if _LEVEL_RE.match(args) and 1.0 < float(args) < 100.1:
            return float(args)
        return None

    # ------------------------------------------------------------------ commands

    @loader.owner
    async def basscmd(self, message: Message) -> None:
        """.bass [2-100] — BassBoost (default 2)"""
        args = utils.get_args_raw(message)
        lvl = self._parse_level(args, 2.0, "BassBoost")
        if lvl is None:
            await utils.answer(
                message,
                self.tr("set_value", message).format("BassBoost", 2.0, 100.0),
            )
            return

        def _bass(audio: AudioSegment) -> AudioSegment:
            samples = list(audio.get_array_of_samples())
            cutoff = int(
                round((3 * np.std(samples) / math.sqrt(2) - np.mean(samples)) * 0.005)
            )
            return audio.overlay(audio.low_pass_filter(cutoff) + lvl)  # type: ignore[attr-defined]

        await self._apply(message, "BassBoost", _bass, title=f"BassBoost {lvl}lvl")

    @loader.owner
    async def fvcmd(self, message: Message) -> None:
        """.fv [2-100] — Distort (default 25)"""
        args = utils.get_args_raw(message)
        lvl = self._parse_level(args, 25.0, "Distort")
        if lvl is None:
            await utils.answer(
                message,
                self.tr("set_value", message).format("Distort", 2.0, 100.0),
            )
            return
        await self._apply(
            message, "Distort", lambda a: a + lvl, title=f"Distort {lvl}lvl"
        )

    @loader.owner
    async def echoscmd(self, message: Message) -> None:
        """.echos — Echo effect"""

        def _echo(audio: AudioSegment) -> AudioSegment:
            out = audio
            offset = 200
            for _ in range(5):
                out = out.overlay(audio - 10, position=offset)
                offset += 200
            return out

        await self._apply(message, "Echo", _echo)

    @loader.owner
    async def volupcmd(self, message: Message) -> None:
        """.volup — Volume +10 dB"""
        await self._apply(message, "+10dB", lambda a: a + 10)

    @loader.owner
    async def voldwcmd(self, message: Message) -> None:
        """.voldw — Volume -10 dB"""
        await self._apply(message, "-10dB", lambda a: a - 10)

    @loader.owner
    async def revscmd(self, message: Message) -> None:
        """.revs — Reverse audio"""
        await self._apply(message, "Reverse", lambda a: a.reverse())

    @loader.owner
    async def repscmd(self, message: Message) -> None:
        """.reps — Repeat audio 2×"""
        await self._apply(message, "Repeat", lambda a: a * 2)

    @loader.owner
    async def slowscmd(self, message: Message) -> None:
        """.slows — Slow down 0.5×"""
        await self._apply(
            message, "SlowDown", lambda a: _retime(a, 0.5), duration_factor=2.0
        )

    @loader.owner
    async def fastscmd(self, message: Message) -> None:
        """.fasts — Speed up 1.5×"""
        await self._apply(
            message, "SpeedUp", lambda a: _retime(a, 1.5), duration_factor=0.5
        )

    @loader.owner
    async def rightscmd(self, message: Message) -> None:
        """.rights — Pan to right channel"""
        await self._apply(message, "Right channel", lambda a: effects.pan(a, +1.0))

    @loader.owner
    async def leftscmd(self, message: Message) -> None:
        """.lefts — Pan to left channel"""
        await self._apply(message, "Left channel", lambda a: effects.pan(a, -1.0))

    @loader.owner
    async def normscmd(self, message: Message) -> None:
        """.norms — Normalize audio level"""
        await self._apply(message, "Normalization", effects.normalize)

    @loader.owner
    async def tovscmd(self, message: Message) -> None:
        """.tovs — Convert to voice message"""
        ctx = await self._get_audio(message, "Voice")
        if not ctx:
            return
        ctx.voice = True
        await self._send_audio(ctx, ctx.audio, ctx.pref)

    @loader.owner
    async def convscmd(self, message: Message) -> None:
        """.convs [format] — Convert to audio format (e.g. mp3, ogg, flac)"""
        args = utils.get_args(message)
        if not args:
            await utils.answer(message, self.tr("set_fmt", message).format("Converter"))
            return
        fmt = args[0].lower()
        ctx = await self._get_audio(message, "Converter")
        if not ctx:
            return
        await self._send_audio(ctx, ctx.audio, f"Converted to {fmt}", fmt=fmt)

    @loader.owner
    async def cutscmd(self, message: Message) -> None:
        """.cuts start(ms):end(ms) — Cut audio to a time range"""
        args = utils.get_args_raw(message)
        match = _CUT_RE.match(args)
        if not match:
            await utils.answer(message, self.tr("set_time", message).format("Cut"))
            return
        start = int(match["start"]) if match["start"] else 0
        end = int(match["end"]) if match["end"] else 0

        def _cut(a: AudioSegment) -> AudioSegment:
            return cast(AudioSegment, a[start : end or len(a) - 1])

        await self._apply(message, "Cut", _cut)

    # ------------------------------------------------------------------ I/O

    async def _get_audio(self, message: Message, pref: str) -> Optional[_AudioCtx]:
        reply = await message.get_reply_message()
        if not (reply and reply.file and reply.file.mime_type):
            await utils.answer(message, self.tr("reply", message).format(pref))
            return None

        kind = reply.file.mime_type.split("/", 1)[0]
        if kind not in ("audio", "video"):
            await utils.answer(message, self.tr("reply", message).format(pref))
            return None

        document = reply.document
        attrs = getattr(document, "attributes", []) or []
        attr = next(
            (a for a in attrs if isinstance(a, types.DocumentAttributeAudio)),
            None,
        )
        voice = bool(attr and attr.voice) if kind == "audio" else False
        duration = attr.duration if attr else 0

        progress = _unwrap(
            await utils.answer(message, self.tr("downloading", message).format(pref))
        )
        raw = await reply.download_media(bytes)
        audio = AudioSegment.from_file(io.BytesIO(raw))
        progress = _unwrap(
            await utils.answer(progress, self.tr("working", message).format(pref))
        )
        if progress is None:
            return None

        return _AudioCtx(
            audio=audio,
            message=progress,
            reply=reply,
            duration=duration,
            voice=voice,
            pref=pref,
        )

    async def _send_audio(
        self,
        ctx: _AudioCtx,
        out: AudioSegment,
        title: str,
        *,
        fs: Optional[int] = None,
        fmt: str = "mp3",
    ) -> None:
        if ctx.voice:
            out = out.split_to_mono()[0]

        out_file = io.BytesIO()
        out_file.name = "audio.ogg" if ctx.voice else f"audio.{fmt}"

        placeholder = _unwrap(
            await utils.answer(
                ctx.message, self.tr("exporting", ctx.message).format(ctx.pref)
            )
        )
        if placeholder is None:
            return

        out.export(
            out_file,
            format="ogg" if ctx.voice else fmt,
            bitrate="64k" if ctx.voice else None,
            codec="libopus" if ctx.voice else None,
        )
        out_file.seek(0)

        attributes = (
            []
            if ctx.voice
            else [
                types.DocumentAttributeAudio(
                    duration=fs or ctx.duration,
                    title=title,
                    performer="AudioEditor",
                )
            ]
        )

        client: TelegramClient = placeholder.client  # type: ignore[assignment]
        if client is None:
            logger.warning("AudioEditor: placeholder has no client; aborting send")
            return

        try:
            await client.send_file(
                utils.get_chat_id(placeholder),
                out_file,
                reply_to=ctx.reply.id,
                voice_note=ctx.voice,
                attributes=attributes,
            )
        except Exception:
            logger.exception("AudioEditor: send_file failed")
            return
        await placeholder.delete()
