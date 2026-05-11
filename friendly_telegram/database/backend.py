"""Local-only database backend.

Replaces the historic ``CloudBackend`` which stored config in a Telegram
channel (``friendly-<uid>-data``) and assets in another (``friendly-<uid>-
assets``). Everything now lives under :func:`utils.get_data_dir`:

* config — ``config-<user_id>.json`` (one file per logged-in account)
* assets — ``assets/<user_id>/<id>.bin`` (binary blobs keyed by an
  auto-incrementing integer)

The class is still named ``CloudBackend`` so existing imports keep working.
"""

import asyncio
import logging
import os
from typing import Optional, Union

from telethon.tl.custom import Message as CustomMessage
from telethon.tl.types import Message

from .. import utils

logger = logging.getLogger(__name__)


class CloudBackend:
    """Per-account JSON file + on-disk asset store."""

    def __init__(self, client):
        self._client = client
        self._me = None
        # Populated by ``init()``; methods below assert non-None before use.
        self._db_path: Optional[str] = None
        self._assets_dir: Optional[str] = None
        self._counter_path: Optional[str] = None
        self._asset_lock = asyncio.Lock()
        self.db = None  # legacy attribute, kept for any external readers
        self.close = lambda: None

    async def init(self, trigger_refresh):
        self._me = await self._client.get_me(True)
        root = utils.get_data_dir()
        self._db_path = os.path.join(root, f"config-{self._me.user_id}.json")
        self._assets_dir = os.path.join(root, "assets", str(self._me.user_id))
        self._counter_path = os.path.join(self._assets_dir, ".next_id")
        os.makedirs(self._assets_dir, exist_ok=True)
        # Reload-on-edit (used by the cloud impl for cross-device sync) is
        # meaningless locally; keep callback for API compat but never call.
        self._callback = trigger_refresh

    async def do_download(self) -> str:
        """Return the JSON-encoded database (as a string)."""
        assert self._db_path is not None, "init() must run before do_download()"
        try:
            with open(self._db_path, "r", encoding="utf-8") as f:
                return f.read() or "{}"
        except FileNotFoundError:
            return "{}"
        except Exception:
            logger.exception("Database read failed, returning empty")
            return "{}"

    async def do_upload(self, data: str) -> bool:
        """Atomically persist *data* (JSON string) to disk."""
        assert self._db_path is not None, "init() must run before do_upload()"
        tmp = f"{self._db_path}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(data or "{}")
            os.replace(tmp, self._db_path)
        except Exception:
            logger.exception("Database save failed")
            raise
        return True

    # -- assets --------------------------------------------------------------
    #
    # Historical API: ``store_asset(msg_or_file)`` returned a Telegram message
    # ID; ``fetch_asset(id)`` returned the Message. We now return an integer
    # ID and the raw bytes. Third-party modules that treated assets as opaque
    # blobs keep working; ones that introspected ``.media`` of the returned
    # Message would need to be updated. None of the in-tree modules do.

    def _next_id(self) -> int:
        assert self._counter_path is not None, "init() must run before _next_id()"
        try:
            with open(self._counter_path, "r") as f:
                cur = int(f.read().strip() or "0")
        except (FileNotFoundError, ValueError):
            cur = 0
        cur += 1
        with open(self._counter_path, "w") as f:
            f.write(str(cur))
        return cur

    async def store_asset(self, message) -> int:
        async with self._asset_lock:
            assert self._assets_dir is not None, "init() must run before store_asset()"
            asset_id = self._next_id()
            path = os.path.join(self._assets_dir, f"{asset_id}.bin")
            data = await self._to_bytes(message)
            with open(path, "wb") as f:
                f.write(data)
            return asset_id

    async def fetch_asset(self, id_: int) -> Optional[bytes]:
        assert self._assets_dir is not None, "init() must run before fetch_asset()"
        path = os.path.join(self._assets_dir, f"{id_}.bin")
        try:
            with open(path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None

    async def _to_bytes(
        self, src: Union[bytes, str, "Message", "CustomMessage"]
    ) -> bytes:
        if isinstance(src, (bytes, bytearray)):
            return bytes(src)
        if isinstance(src, str) and os.path.isfile(src):
            with open(src, "rb") as f:
                return f.read()
        if isinstance(src, str):
            return src.encode("utf-8")
        if isinstance(src, (Message, CustomMessage)):
            # Download the media payload of a Telegram message into memory.
            return await self._client.download_media(src, file=bytes)
        raise TypeError(f"unsupported asset source: {type(src).__name__}")
