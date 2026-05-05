# Database & asset storage

A small async-friendly key-value store backed by a JSON file under
`~/.local/share/friendly-telegram/config-<user_id>.json`, plus a binary blob
storage next to it for media that doesn't fit in JSON.

## KV store

```python
async def client_ready(self, client, db):
    self._db = db

    counter = self._db.get(__name__, "counter", 0)
    self._db.set(__name__, "counter", counter + 1)
```

Conventions:

- **First argument** (`owner`): use `__name__` for module-private data so
  uninstalling the module is a clean delete.
- **Values** must be JSON-serializable.
- `db.set` is *not* async — it returns a future you can await if you need to
  block until the next flush:

  ```python
  await self._db.set(__name__, "k", v)   # waits for the on-disk write
  self._db.set(__name__, "k", v)         # fire-and-forget (typical)
  ```

Writes are batched and flushed every 10 s, so don't worry about hammering it.

Cross-module reads are allowed but keep them rare and document the contract.

## Asset storage

`db.store_asset()` and `db.fetch_asset()` are for binary blobs that don't fit
in JSON (pictures, voice notes, archives). Storage is local since the cloud
backend was removed.

```python
asset_id = await self._db.store_asset(b"...")            # bytes
asset_id = await self._db.store_asset("/tmp/cat.jpg")    # path
asset_id = await self._db.store_asset(message)           # Telethon Message
self._db.set(__name__, "cat_id", asset_id)

raw = await self._db.fetch_asset(self._db.get(__name__, "cat_id"))  # bytes
```

> **Migration note.** In older FTG versions `fetch_asset` returned a
> Telethon `Message`. Local storage returns raw bytes. If you need to send
> them onward, pass them to `client.send_file(chat, file=raw)`.

Files live under `~/.local/share/friendly-telegram/assets/<user_id>/<id>.bin`.
