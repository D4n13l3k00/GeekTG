"""Post-login dashboard router: /, /me, /me/avatar, /restart, /ping."""

import io
import logging

import aiohttp_jinja2
from aiohttp import web
from telethon.tl.functions.users import GetFullUserRequest

from .context import WebContext

logger = logging.getLogger(__name__)


def _mask_phone(phone: str) -> str:
    """Mask the middle of a phone number, keeping country code and last two."""
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) < 4:
        return f"+{digits}"
    head = digits[:1]  # country code first digit (good enough for masking)
    tail = digits[-2:]
    return f"+{head}{'*' * (len(digits) - 3)}{tail}"


class RootRouter:
    """Handlers behind ``/`` once the user is signed in."""

    def __init__(self, ctx: WebContext):
        self.ctx = ctx

    def register(self, app: web.Application) -> None:
        # ``/`` is owned by InitialSetupRouter — it dispatches between the
        # wizard and our dashboard depending on auth state.
        app.router.add_get("/ping", self.ping)
        # Legacy alias kept for any external pollers (and existing JS).
        app.router.add_get("/is_restart_complete", self.ping)
        app.router.add_post("/restart", self.restart)
        app.router.add_get("/me", self.me)
        app.router.add_get("/me/avatar", self.me_avatar)

    # ---- handlers ------------------------------------------------------

    async def _load_me(self):
        client = self.ctx.first_authed_client()
        if client is None:
            return None
        me = await client.get_me()
        bio = ""
        try:
            full = await client(GetFullUserRequest(me))
            bio = (full.full_user.about or "").strip()
        except Exception:
            logger.debug("GetFullUserRequest failed", exc_info=True)
        self.ctx.me_cache = {
            "id": me.id,
            "first_name": me.first_name or "",
            "last_name": me.last_name or "",
            "username": me.username or "",
            "phone": _mask_phone(me.phone or ""),
            "bio": bio,
            "premium": bool(getattr(me, "premium", False)),
            "has_avatar": bool(me.photo),
        }
        return self.ctx.me_cache

    async def me(self, request):
        data = self.ctx.me_cache or await self._load_me()
        if data is None:
            return web.json_response({"error": "no_client"}, status=503)
        return web.json_response(data)

    async def me_avatar(self, request):
        if self.ctx.avatar_cache is not None:
            body, ctype = self.ctx.avatar_cache
            return web.Response(
                body=body,
                content_type=ctype,
                headers={"Cache-Control": "public, max-age=300"},
            )
        client = self.ctx.first_authed_client()
        if client is None:
            return web.Response(status=503)
        buf = io.BytesIO()
        try:
            await client.download_profile_photo("me", file=buf)
        except Exception:
            logger.debug("avatar download failed", exc_info=True)
            return web.Response(status=404)
        body = buf.getvalue()
        if not body:
            return web.Response(status=404)
        # Telethon writes JPEG by default for profile photos.
        self.ctx.avatar_cache = (body, "image/jpeg")
        return web.Response(
            body=body,
            content_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=300"},
        )

    @aiohttp_jinja2.template("root.jinja2")
    async def root(self, request):
        return {}

    async def ping(self, request):
        """Liveness probe used by the dashboard to detect post-restart boot.

        Returns 200 with no body. During a restart/logout the TCP listener
        is briefly torn down, so callers fail fast (connection refused) and
        retry until this endpoint answers again.
        """
        return web.Response(text="ok")

    async def restart(self, request) -> web.Response:
        # Invalidate caches so the post-restart UI fetches fresh data.
        self.ctx.me_cache = None
        self.ctx.avatar_cache = None
        loader, client, _db = next(iter(self.ctx.client_data.values()))
        m = await client.send_message("me", "<b>Restarting...</b>")
        for mod in loader.modules:
            if mod.__class__.__name__ == "UpdaterMod":
                await mod.restart_common(m)
        # The process is about to exec away — clients usually never see this
        # response, but aiohttp requires handlers to return a StreamResponse.
        return web.Response(status=202)
