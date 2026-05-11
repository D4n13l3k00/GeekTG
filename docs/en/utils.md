# `utils` cheatsheet

`from friendly_telegram import utils` — small helpers used across the
framework and core modules. Touch when writing a module that needs to
parse args, send replies, escape HTML, resolve paths, or shell out.
Source: [`friendly_telegram/utils.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/utils.py).

`Message` below means `telethon.tl.custom.Message` (NOT
`telethon.tl.types.Message` — the custom subclass exposes
`.client`, `.edit`, `.delete`, `.respond`, `.get_reply_message`,
`.is_reply`, `.raw_text`).

This page is grouped by category. Signatures, return shapes and edge cases
are spelt out — copy-pasteable rather than approximate.

---

## Telegram I/O

### `answer(message, response, **kwargs) -> List[Message]` *(async)*

```python
async def answer(message, response, **kwargs) -> List[Message]
```

`message: Union[Message, List[Message]]` — Telethon
`telethon.tl.custom.Message`, or a list whose head is the message to
edit/reply and whose tail is messages to delete first (used by
"working… → done" progress flows).
`response` may be `str`, a Telethon `Message`, raw `bytes`, or a
file-like object.

Behaviour:

- If `message.out` (we sent it), **edit**; otherwise reply with
  `reply_to = message.reply_to_msg_id`.
- HTML/markdown is parsed via `message.client.parse_mode` unless
  `parse_mode=` is passed; `link_preview` defaults to `False`.
- If the rendered text is ≥ 4096 chars (or `asfile=True`), falls back
  to `send_file` with `command_result.txt` and deletes the original
  outgoing message.
- Forwarded kwargs: `parse_mode`, `link_preview`, `asfile`, `filename`,
  `reply_to`, plus anything `client.send_file` accepts.

Always inspect `result[0]` for follow-up edits — the original message
may be gone.

### `get_user(message) -> User | None` *(async)*

Returns the Telethon `User` for the message sender, with cache-miss
recovery: re-iterates dialogs (DMs) or group participants when the entity
isn't cached. Returns `None` (and logs `critical`) if `peer_id` is
malformed or lookup ultimately fails. Handles `BotMethodInvalidError`
when running as a bot.

### `get_chat_id(message) -> int`

Numeric chat ID with the `-100` channel prefix stripped (via Telethon's
`resolve_id`). Useful for serializing IDs into compact strings.

### `get_entity_id(entity) -> int`

Wraps `telethon.utils.get_peer_id()` for any entity-like object.

---

## Argument parsing

### `get_args(message) -> List[str]`

`shlex.split()` on everything after the first whitespace token of
`message.message` (or the string itself).

- Empty / no args → `[]`.
- Malformed quoting → `[tail]` (single-element list of the raw tail —
  safe for `len()` arity checks).
- Zero-length tokens are dropped.

### `get_args_raw(message) -> str`

Everything after the first whitespace as one string. Returns `""` when
there are no args (never `False`/`None` — safe for `.strip()` /
`.split()` without a guard).

### `get_args_split_by(message, sep) -> List[str]`

Splits `get_args_raw()` by `sep`, strips each section, drops blanks
post-strip. Always returns a list.

### `get_target(message, arg_no=0) -> Optional[int]` *(async)*

Resolve a user ID from a message in priority order:

1. First `MessageEntityMentionName` in the message text.
2. The `arg_no`-th word of `get_args(message)` (resolved via
   `get_entity`).
3. Replied-to message sender.
4. Peer user ID if the message is in a DM.

Returns `None` if nothing resolves, or if the candidate isn't a `User`
(filters out chats / channels).

---

## Paths and data dirs

### `get_base_dir() -> str`

Absolute path to the installed `friendly_telegram/` package directory
(read-only on most installs). Computed from `__file__`, no syscalls.

### `get_dir(mod) -> str`

Absolute directory of an arbitrary module (path string or `__file__`).

### `get_data_dir() -> str` *(cached, `lru_cache(maxsize=1)`)*

Writable data directory, resolved in order:

1. `$GTG_DATA_DIR` (or legacy `$FTG_DATA_DIR`).
2. `$XDG_DATA_HOME/friendly-telegram`.
3. `~/.local/share/friendly-telegram`.

Created on first call. Sessions, configs, downloaded modules and assets
all live under this path.

---

## Runtime / platform

### `get_platform_name() -> str`

User-friendly platform tag (`"📻 VDS"`, `"📱 Termux"`, `"🐳 Docker"`,
`"✌️ lavHost <id>"`). Resolution order:

1. `$GTG_PLATFORM` / `$FTG_PLATFORM` override.
2. `$LAVHOST`.
3. Termux (`$PREFIX` contains `com.termux`).
4. Docker (`/.dockerenv` exists).
5. Fallback `"📻 VDS"`.

Not cached — env-var override after import works.

### `install_requirements(requirements, *, user_install=False, record=True) -> int` *(async)*

Best-effort runtime pip install:

1. `uv pip install --python <exe> <pkgs...>` if `uv` is on PATH.
2. `python -m pip install <pkgs...>`.
3. `python -m ensurepip --upgrade` then retry pip.

Returns the subprocess return code (0 on success). On success and if
`record=True`, appends pinned `pkg==version` lines to
`<data_dir>/auto_requirements.txt` so a Docker rebuild can replay them.

### `print_web_urls(port) -> None`

Prints reachable web-UI URLs (localhost + LAN IPs + optional public IP)
in the canonical bracket form for IPv6. Used during the first-run wizard.

---

## Formatting & escaping

### `escape_html(text) -> str`

`&` → `&amp;`, `<` → `&lt;`, `>` → `&gt;`. Coerces input to `str`.

### `escape_quotes(text) -> str`

`escape_html()` plus `"` → `&quot;`.

### `relocate_entities(entities, offset, text=None) -> list[Entity]`

Shift all Telethon `MessageEntity` offsets by `offset`, clipping to the
length of `text`. Drops entities that would become zero-length. Mutates
the input list and returns it. With `text=None` no clipping is applied.

---

## Misc

### `rand(length) -> str`

Random ASCII letters+digits of given length. Used by the inline manager
for unique result IDs.

### `get_version_raw() -> str`

`"4.1.4"`-style version derived from the package's `__version__` tuple.

### `get_git_info() -> [str, str]`

`[short_sha_or_empty, github_url_or_empty]`. Lazy GitPython import; falls
back to `["", ""]` on wheel/Docker installs without `.git`.

### `run_sync(func, *args, **kwargs) -> asyncio.Future`

Runs a blocking function in the default executor. Always `await` it.

```python
url = "https://example.com/big.jpg"
data = await utils.run_sync(requests.get, url)
```

### `run_async(loop, coro) -> Any`

Runs an async coroutine *synchronously* from a non-async context (e.g.
inside a callback registered with a sync API). Uses
`asyncio.run_coroutine_threadsafe` and blocks until the result is ready.

### `censor(obj, to_censor=None, replace_with="redacted_{count}_chars") -> obj`

Scrubs sensitive attributes (`["phone"]` by default) on an object and its
nested `__dict__` — used to keep `/tracebacks` and the web wizard from
leaking `client.phone` etc.

### `merge(a, b) -> dict`

Recursive in-place merge of `a` into `b`. Nested dicts merge recursively;
parallel lists are union-ed; scalar `a` values overwrite `b`.
