"""Status + backup/restore endpoints."""

import io
import logging
import os
import shutil
import tempfile
import time
import zipfile

from aiohttp import web

from .. import __version__, utils

logger = logging.getLogger(__name__)


_RESOURCE_CACHE_TTL = 3.0
_BACKUP_EXCLUDE_SUFFIXES = (".session-journal",)
_RESTORE_MAX_BYTES = 64 * 1024 * 1024  # 64 MiB hard limit on uploads


def _try_psutil():
    try:
        import psutil  # noqa: WPS433
    except Exception:
        return None
    return psutil


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


class Web:
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app.router.add_get("/status", self.status)
        self.app.router.add_get("/backup", self.backup)
        self.app.router.add_post("/restore", self.restore)
        self._resource_cache = (0.0, None)
        self._proc = None  # lazy psutil.Process

    def _data_dir(self) -> str:
        return self.data_root or utils.get_data_dir()

    def _bot_info(self):
        """Return inline-bot status for the first client, if available."""
        if not self.client_data:
            return {"configured": False, "ready": False, "username": None}
        loader = next(iter(self.client_data.values()))[0]
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
                out.update({
                    "available": True,
                    "rss_bytes": int(rss),
                    "cpu_percent": round(float(cpu), 1),
                })
            except Exception:
                logger.debug("psutil sample failed", exc_info=True)

        data_dir = self._data_dir()
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

    async def status(self, request):
        sha, sha_url = utils.get_git_info()
        return web.json_response({
            "version": ".".join(map(str, __version__)),
            "git": {"sha": sha, "url": sha_url},
            "platform": utils.get_platform_name(),
            "data_dir": self._data_dir(),
            "uptime_seconds": int(time.time() - self.started_at),
            "started_at": int(self.started_at),
            "resources": self._resources(),
            "bot": self._bot_info(),
            "authorized": bool(self.client_data),
        })

    async def backup(self, request):
        """Stream a zip of the data dir (sessions, config, modules, db)."""
        data_dir = self._data_dir()
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

        Strategy: extract to a sibling ``.restore-tmp`` directory, validate
        every member stays inside it, then move entries on top of the live
        data dir. We do *not* wipe the existing dir first — if the zip is a
        partial backup, the user keeps whatever wasn't overwritten. They
        should restart the process afterwards (we can't safely hot-swap the
        Telethon session while it's connected).
        """
        if not request.body_exists:
            return web.Response(status=400, text="no body")

        reader = await request.multipart()
        field = await reader.next()
        if field is None or field.name != "backup":
            return web.Response(status=400, text="missing 'backup' field")

        data_dir = self._data_dir()
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
                # Path-traversal guard: every member, after normalisation,
                # must resolve inside data_dir. Reject the whole archive on
                # any miss.
                resolved_dir = os.path.realpath(data_dir)
                for member in zf.namelist():
                    if member.endswith("/"):
                        continue
                    target = os.path.realpath(os.path.join(data_dir, member))
                    if (
                        target != resolved_dir
                        and not target.startswith(resolved_dir + os.sep)
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
