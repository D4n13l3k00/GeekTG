"""Status + backup/restore + logout endpoints.

Exposed as ``StatusRouter`` (composition-style) — register routes
against a shared ``aiohttp.web.Application`` via ``.register(app)``.
"""

import asyncio
import atexit
import functools
import io
import logging
import os
import secrets
import shutil
import signal
import sys
import tempfile
import time
import zipfile

from aiohttp import web

from .. import __version__, utils
from .context import WebContext

logger = logging.getLogger(__name__)


_RESOURCE_CACHE_TTL = 3.0
_BACKUP_EXCLUDE_SUFFIXES = (".session-journal",)
_RESTORE_MAX_BYTES = 64 * 1024 * 1024  # 64 MiB hard limit on uploads
_BACKUP_CODE_TTL = 300  # 5 min — TG-delivered code lifetime
_BACKUP_TOKEN_TTL = 300  # action-token window after confirm (5 min)


def _try_psutil():
    try:
        import psutil  # noqa: WPS433
    except Exception:
        return None
    return psutil


class _CodeGate:
    """Single-slot 2FA: DM a code to Saved Messages, verify, mint a token.

    Used to gate backup downloads, restore uploads and logout — anything
    that touches the on-disk session bytes or revokes the auth key.
    """

    def __init__(self, label: str, prompt: str):
        self.label = label  # noun phrase: "скачивания бэкапа", "восстановления"
        self.prompt = prompt  # extra explanatory line for the TG message
        self._pending = None  # dict|None: code, expires, msg_id, client
        self._token = None  # dict|None: token, expires

    async def request(self, client) -> bool:
        await self.discard()
        code = f"{secrets.randbelow(1_000_000):06d}"
        text = (
            f"🔐 <b>Код для {self.label}:</b> <code>{code}</code>\n\n"
            f"{self.prompt}\n\n"
            "Никому не показывайте этот код. Действителен 5 минут. "
            "Сообщение удалится автоматически после ввода."
        )
        try:
            msg = await client.send_message("me", text, parse_mode="html")
        except Exception:
            logger.exception("code-gate %s: send failed", self.label)
            return False
        self._pending = {
            "code": code,
            "expires": time.monotonic() + _BACKUP_CODE_TTL,
            "msg_id": msg.id,
            "client": client,
        }
        return True

    async def discard(self):
        pending = self._pending
        self._pending = None
        if pending is None:
            return
        try:
            await pending["client"].delete_messages("me", [pending["msg_id"]])
        except Exception:
            logger.debug("code-gate %s: cleanup failed", self.label, exc_info=True)

    async def confirm(self, code: str):
        """Return ``("ok", token)`` or ``(error_str, None)``."""
        pending = self._pending
        if pending is None:
            return ("no_pending", None)
        if time.monotonic() > pending["expires"]:
            await self.discard()
            return ("expired", None)
        if not secrets.compare_digest(code, pending["code"]):
            return ("wrong", None)
        await self.discard()
        token = secrets.token_urlsafe(24)
        self._token = {
            "token": token,
            "expires": time.monotonic() + _BACKUP_TOKEN_TTL,
        }
        return ("ok", token)

    def consume(self, presented: str) -> bool:
        """Validate the token. Stays usable until ``expires`` — not one-shot,
        so a flaky download / retry within the window still works."""
        slot = self._token
        if slot is None:
            return False
        if time.monotonic() > slot["expires"]:
            self._token = None
            return False
        if not presented or not secrets.compare_digest(presented, slot["token"]):
            return False
        return True


def _data_dir_size(path: str) -> int:
    """Sum of regular-file sizes under ``path``. Skips broken symlinks."""
    total = 0
    for root, _dirs, files in os.walk(path, followlinks=False):
        for name in files:
            fp = os.path.join(root, name)
            try:
                total += os.path.getsize(fp)
            except OSError:
                continue
    return total


class StatusRouter:
    """Mounts /status, backup/restore/logout endpoints on a shared app."""

    def __init__(self, ctx: WebContext):
        self.ctx = ctx
        self._resource_cache = (0.0, None)
        self._proc = None  # lazy psutil.Process

        ctx.backup_gate = _CodeGate(
            label="скачивания бэкапа",
            prompt=(
                "Введите этот код в веб-интерфейсе, чтобы подтвердить, "
                "что бэкап скачиваете именно вы."
            ),
        )
        ctx.restore_gate = _CodeGate(
            label="восстановления из бэкапа",
            prompt=(
                "Введите этот код в веб-интерфейсе, чтобы подтвердить, "
                "что хотите перезаписать данные юзербота."
            ),
        )
        ctx.logout_gate = _CodeGate(
            label="выхода из юзербота",
            prompt=(
                "Введите этот код в веб-интерфейсе, чтобы завершить "
                "сессию Telegram и перезапустить юзербот."
            ),
        )

    def register(self, app: web.Application) -> None:
        app.router.add_get("/status", self.status)
        app.router.add_post("/backup/request", self.backup_request)
        app.router.add_post("/backup/confirm", self.backup_confirm)
        app.router.add_get("/backup", self.backup)
        app.router.add_post("/restore/request", self.restore_request)
        app.router.add_post("/restore/confirm", self.restore_confirm)
        app.router.add_post("/restore", self.restore)
        app.router.add_post("/logout/request", self.logout_request)
        app.router.add_post("/logout/confirm", self.logout_confirm)
        app.router.add_post("/logout", self.logout_perform)

    # ---- helpers -------------------------------------------------------

    def _bot_info(self):
        loader = self.ctx.first_loader()
        if loader is None:
            return {"configured": False, "ready": False, "username": None}
        inline = getattr(loader, "inline", None)
        if inline is None:
            return {"configured": False, "ready": False, "username": None}
        return {
            "configured": bool(getattr(inline, "_token", None)),
            "ready": bool(getattr(inline, "init_complete", False)),
            "username": getattr(inline, "bot_username", None),
        }

    def _resources(self):
        now = time.monotonic()
        ts, cached = self._resource_cache
        if cached is not None and now - ts < _RESOURCE_CACHE_TTL:
            return cached

        psutil = _try_psutil()
        out = {"available": False}

        if psutil is not None:
            if self._proc is None:
                self._proc = psutil.Process(os.getpid())
            try:
                with self._proc.oneshot():
                    rss = self._proc.memory_info().rss
                    # Non-blocking sample: returns 0.0 the very first time but
                    # populates an internal counter so subsequent calls are
                    # accurate. The 3-second cache amortises the warmup.
                    cpu = self._proc.cpu_percent(interval=None)
                out.update(
                    {
                        "available": True,
                        "rss_bytes": int(rss),
                        "cpu_percent": round(float(cpu), 1),
                    }
                )
            except Exception:
                logger.debug("psutil sample failed", exc_info=True)

        data_dir = self.ctx.effective_data_dir()
        try:
            usage = shutil.disk_usage(data_dir)
            out["disk"] = {
                "total_bytes": int(usage.total),
                "free_bytes": int(usage.free),
                "used_by_us_bytes": int(_data_dir_size(data_dir)),
            }
        except OSError:
            logger.debug("disk_usage failed for %s", data_dir, exc_info=True)

        self._resource_cache = (now, out)
        return out

    # ---- handlers ------------------------------------------------------

    async def status(self, request):
        sha, sha_url = utils.get_git_info()
        return web.json_response(
            {
                "version": ".".join(map(str, __version__)),
                "git": {"sha": sha, "url": sha_url},
                "platform": utils.get_platform_name(),
                "data_dir": self.ctx.effective_data_dir(),
                "uptime_seconds": int(time.time() - self.ctx.started_at),
                "started_at": int(self.ctx.started_at),
                "resources": self._resources(),
                "bot": self._bot_info(),
                "authorized": bool(self.ctx.client_data),
            }
        )

    async def _gate_request(self, gate):
        client = self.ctx.first_authed_client()
        if client is None:
            return web.json_response({"error": "no_client"}, status=503)
        ok = await gate.request(client)
        if not ok:
            return web.json_response({"error": "send_failed"}, status=502)
        return web.json_response({"ok": True, "ttl": _BACKUP_CODE_TTL})

    async def _gate_confirm(self, gate, request):
        body = (await request.text()).strip()
        if not body.isdigit() or len(body) != 6:
            return web.json_response({"error": "bad_format"}, status=400)
        result, payload = await gate.confirm(body)
        if result == "ok":
            return web.json_response({"ok": True, "token": payload})
        status = {"wrong": 403, "expired": 410, "no_pending": 410}.get(result, 400)
        return web.json_response({"error": result}, status=status)

    async def backup_request(self, request):
        return await self._gate_request(self.ctx.backup_gate)

    async def backup_confirm(self, request):
        return await self._gate_confirm(self.ctx.backup_gate, request)

    async def restore_request(self, request):
        return await self._gate_request(self.ctx.restore_gate)

    async def restore_confirm(self, request):
        return await self._gate_confirm(self.ctx.restore_gate, request)

    async def logout_request(self, request):
        return await self._gate_request(self.ctx.logout_gate)

    async def logout_confirm(self, request):
        return await self._gate_confirm(self.ctx.logout_gate, request)

    async def logout_perform(self, request):
        """Revoke Telegram session(s) and re-exec the process.

        After ``log_out()`` the .session file is gone, so the next boot
        lands the user back on the initial-setup wizard. ``api_token.txt``
        is intentionally preserved — the API credentials belong to the
        user, not the session.
        """
        if not self.ctx.logout_gate.consume(request.query.get("token", "")):
            return web.Response(status=403, text="confirmation required")
        if not self.ctx.client_data:
            return web.Response(status=503, text="no client")

        # Hand the actual logout off to a background task so we can flush
        # the 200 to the browser before the process tears itself down.
        asyncio.create_task(self._do_logout())
        return web.json_response({"ok": True})

    async def _do_logout(self):
        # Brief grace so aiohttp finishes writing the response.
        await asyncio.sleep(0.4)

        for _loader, client, _db in list(self.ctx.client_data.values()):
            try:
                await client.send_message(
                    "me",
                    "🔓 <b>Выход из юзербота</b>\n\nСессия Telegram завершена.",
                    parse_mode="html",
                )
            except Exception:
                logger.warning("logout: goodbye message failed", exc_info=True)
            try:
                # log_out() revokes the auth key on Telegram's side, removes
                # the .session file, and disconnects the client.
                await client.log_out()
            except Exception:
                logger.exception("logout: client.log_out() failed")

        # Re-exec ourselves once the asyncio loop unwinds. Mirrors what
        # modules/updater.py does on .restart, minus its TG-message
        # roundtrip (we just logged out — no client to talk to).
        atexit.register(
            functools.partial(
                os.execl,
                sys.executable,
                sys.executable,
                "-m",
                "friendly_telegram",
                *sys.argv[1:],
            )
        )
        # Nudge the loop to exit. SIGTERM is the same signal main.py's
        # graceful-shutdown handler installs in _async_main.
        os.kill(os.getpid(), signal.SIGTERM)

    async def backup(self, request):
        """Stream a zip of the data dir (sessions, config, modules, db).

        Requires ``?token=`` from a successful /backup/confirm round-trip.
        """
        if not self.ctx.backup_gate.consume(request.query.get("token", "")):
            return web.Response(status=403, text="confirmation required")

        data_dir = self.ctx.effective_data_dir()
        if not os.path.isdir(data_dir):
            return web.Response(status=404, text="data dir missing")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(data_dir, followlinks=False):
                for name in files:
                    if name.endswith(_BACKUP_EXCLUDE_SUFFIXES):
                        continue
                    fp = os.path.join(root, name)
                    try:
                        arcname = os.path.relpath(fp, data_dir)
                        zf.write(fp, arcname=arcname)
                    except OSError:
                        logger.warning("backup: skipping unreadable %s", fp)

        body = buf.getvalue()
        ts = time.strftime("%Y%m%d-%H%M%S")
        return web.Response(
            body=body,
            content_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="geektg-backup-{ts}.zip"',
                "Content-Length": str(len(body)),
            },
        )

    async def restore(self, request):
        """Replace data-dir contents with files from an uploaded zip.

        Post-auth, requires ``?token=`` from /restore/confirm — restore
        is destructive (overwrites the live session). Pre-auth (no
        client yet, e.g. fresh install) doesn't need TG confirmation
        because there's no account state to protect with.

        Path-traversal guarded: every member resolves under the data
        dir or the whole archive is rejected.
        """
        if self.ctx.first_authed_client() is not None:
            if not self.ctx.restore_gate.consume(request.query.get("token", "")):
                return web.Response(status=403, text="confirmation required")

        if not request.body_exists:
            return web.Response(status=400, text="no body")

        reader = await request.multipart()
        field = await reader.next()
        if field is None or field.name != "backup":
            return web.Response(status=400, text="missing 'backup' field")

        data_dir = self.ctx.effective_data_dir()
        os.makedirs(data_dir, exist_ok=True)

        # Buffer to disk so we don't blow up RAM on a multi-MB zip.
        with tempfile.NamedTemporaryFile(
            suffix=".zip", dir=data_dir, delete=False
        ) as tmp:
            total = 0
            try:
                while True:
                    chunk = await field.read_chunk(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _RESTORE_MAX_BYTES:
                        return web.Response(status=413, text="too large")
                    tmp.write(chunk)
                tmp_path = tmp.name
            except Exception:
                os.unlink(tmp.name)
                raise

        try:
            try:
                zf = zipfile.ZipFile(tmp_path)
            except zipfile.BadZipFile:
                return web.Response(status=400, text="not a zip")

            with zf:
                resolved_dir = os.path.realpath(data_dir)
                for member in zf.namelist():
                    if member.endswith("/"):
                        continue
                    target = os.path.realpath(os.path.join(data_dir, member))
                    if target != resolved_dir and not target.startswith(
                        resolved_dir + os.sep
                    ):
                        return web.Response(
                            status=400,
                            text=f"unsafe path in archive: {member}",
                        )
                zf.extractall(data_dir)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return web.json_response({"ok": True, "restart_required": True})
