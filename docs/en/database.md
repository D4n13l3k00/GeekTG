# Database & asset storage

A small async-friendly key-value store backed by a JSON file under
`<data_dir>/config-<user_id>.json`, plus a binary blob storage next to
it for media that doesn't fit in JSON. Where `<data_dir>` resolves to is
documented in **[utils.md → `get_data_dir`](utils.md#get_data_dir---str-cached-lru_cachemaxsize1)**.

The `Database` class extends Python's `dict` and partitions storage by
**owner** namespace — convention is to use `__name__` so uninstalling a
module is a clean delete.

---

## Architecture

Two layers:

- **Frontend** ([`database/frontend.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/database/frontend.py))
  — public `Database` class with debounced writes and the asset API.
- **Backend** ([`database/backend.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/database/backend.py))
  — JSON read/write to disk + asset blob persistence. The historical
  cloud backend was removed; everything is local now.

Files on disk:

```text
<data_dir>/
├── config-<user_id>.json         # KV store (per-account)
└── assets/<user_id>/
    ├── 1.bin, 2.bin, …           # binary blobs
    └── .next_id                  # auto-increment counter
```

---

## KV store

```python
@loader.owner
async def bumpcmd(self, message: Message):
    db = self.ctx.db
    n = db.get(__name__, "counter", 0)
    db.set(__name__, "counter", n + 1)
    await utils.answer(message, f"counter is now {n + 1}")
```

Conventions:

- **First argument** (`owner`): use `__name__` for module-private data.
- **Values** must be JSON-serializable.
- Cross-module reads are allowed — keep them rare and document the
  contract on both sides.

### Read operations

| Call | Returns |
| ---- | ------- |
| `db.get(owner, key, default=None)` | Value, or `default` if absent. |
| `db[owner]` | The owner's nested dict (raises `KeyError` if missing). |
| `db.keys()` | All owner namespaces present. |

### Write operations and flush semantics

`db.set(owner, key, value)` is **not strictly async** — it returns a
`NotifyingFuture` you may either fire-and-forget or await:

```python
self.ctx.db.set(__name__, "k", v)            # fire-and-forget (typical)
await self.ctx.db.set(__name__, "k", v)      # waits for the on-disk write
```

Internally, writes are coalesced through a 10 s debounce: the first
unsaved `set` schedules a flush, and subsequent `set`s within the window
piggyback on the same future. Awaiting the future cancels the delay and
flushes immediately.

`await db.save()` forces an immediate flush regardless of pending
debounce — useful in shutdown paths.

Hammering `db.set` in a tight loop is therefore safe; it costs one disk
write per ~10 s, not one per call.

---

## Asset storage

For binary blobs that don't belong in JSON (pictures, voice notes,
archives). Storage is local since the cloud backend was removed.

```python
asset_id = await db.store_asset(b"...")            # bytes/bytearray
asset_id = await db.store_asset("/tmp/cat.jpg")    # filesystem path
asset_id = await db.store_asset(message)           # Telethon Message (downloads media)
asset_id = await db.store_asset("plain text")      # str → utf-8 bytes
db.set(__name__, "cat_id", asset_id)

raw: bytes | None = await db.fetch_asset(db.get(__name__, "cat_id"))
```

`store_asset` returns an auto-incrementing `int`. `fetch_asset` returns
the raw bytes, or `None` if the asset is missing. Both are guarded by an
internal `asyncio.Lock` so concurrent `store_asset` calls can't collide
on the same ID.

> **Migration note.** In older FTG versions `fetch_asset` returned a
> Telethon `Message`. Local storage returns raw bytes. To resend, do
> `await client.send_file(chat, file=raw)`.

---

## Reserved DB keys

These are namespaces / keys that core modules read or write. Avoid
clobbering them from third-party modules.

| Owner (`__name__`) | Key | Purpose |
| ------------------ | --- | ------- |
| `friendly_telegram.main` | `command_prefix` | Command trigger character (default `.`). |
| `friendly_telegram.main` | `blacklist_chats`, `blacklist_users` | Drop messages before any dispatch. |
| `friendly_telegram.main` | `disabled_watchers` | Modules whose `watcher` is muted. |
| `friendly_telegram.main` | `language`, `langpacks` | i18n / langpack settings. |
| `friendly_telegram.security` | `owner`, `sudo`, `support` | Permission groups. |
| `friendly_telegram.security` | `masks` | Per-command permission overrides. |
| `friendly_telegram.security` | `bounding_mask`, `default`, `any_admin` | Global security config. |
| `friendly_telegram.security` | `blacklist_users` | Hard-deny list. |
| `friendly_telegram.modules.help` | `hide` | Modules hidden from `.help`. |
| `geektg.inline` | `bot_token` | Inline-bot Telegram token. |
| `friendly_telegram.modules.corectrl` | `aliases` | User-defined command aliases. |
| `friendly_telegram.modules.loader` | `chosen_preset` | Repo preset (`"none"` by default — no remote fetch). |

The lists are re-read from the DB on every relevant lookup, so changes
take effect immediately without restart.

---

## Edge cases

- **Concurrency.** The frontend assumes a single asyncio event loop —
  it's not thread-safe. Use `asyncio.run_coroutine_threadsafe` if you
  must touch it from another thread.
- **Corruption.** A corrupt `config-<user_id>.json` is silently treated
  as `{}` on load (a backup is *not* taken automatically — back up before
  you experiment).
- **No-op mode.** Tests construct the frontend with `noop=True` /
  `backend=None`; the API works but never persists anything.
