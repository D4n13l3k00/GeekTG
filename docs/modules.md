# Writing modules

Modules are the unit of extension for GeekTG. Each module is a single Python
file that defines one class with userbot commands, message watchers, inline
handlers and persistent state. The loader picks them up at startup or on
demand via `.loadmod`.

This doc covers the canonical module layout, the lifecycle, every helper
the framework exposes, and the small foot-guns that aren't obvious from the
code.

> Russian-language legacy notes live in [`mods.md`](mods.md). The page you're
> reading supersedes them.

---

## Table of contents

1. [The five-minute module](#the-five-minute-module)
2. [Anatomy of a module](#anatomy-of-a-module)
3. [Lifecycle hooks](#lifecycle-hooks)
4. [Commands](#commands)
5. [Watchers (passive handlers)](#watchers-passive-handlers)
6. [Inline manager: forms, galleries, callbacks](#inline-manager-forms-galleries-callbacks)
7. [Strings and translations](#strings-and-translations)
8. [Config (`ModuleConfig`)](#config-moduleconfig)
9. [Database](#database)
10. [Asset storage](#asset-storage)
11. [The `utils` cheatsheet](#the-utils-cheatsheet)
12. [Security: how command permissions work](#security-how-command-permissions-work)
13. [Module headers and metadata directives](#module-headers-and-metadata-directives)
14. [Distribution and loading](#distribution-and-loading)
15. [Best practices and pitfalls](#best-practices-and-pitfalls)

---

## The five-minute module

Save this as `~/.local/share/friendly-telegram/loaded_modules/HelloMod.py` (or
load it from a URL via `.loadmod`):

```python
# meta developer: @your_handle
# requires: pillow

from telethon.tl.types import Message
from friendly_telegram import loader, utils


@loader.tds
class HelloMod(loader.Module):
    """Says hi to the sender."""

    strings = {
        "name": "Hello",
        "hi": "👋 <b>Hello, {name}!</b>",
    }

    @loader.unrestricted
    async def hicmd(self, message: Message):
        """Say hi to whoever sent the message."""
        sender = await message.get_sender()
        await utils.answer(
            message,
            self.strings("hi", message).format(name=sender.first_name),
        )
```

Run `.loadmod` on the file or restart the bot. Then:

```text
> .hi
👋 Hello, John!
```

That's everything required: a `loader.Module` subclass whose name ends with
`Mod`, decorated with `@loader.tds`, exposing one method whose name ends with
`cmd`.

---

## Anatomy of a module

```
┌────────────────────────────────┐
│  metadata directives           │  # meta developer:, # requires:, # scope:
├────────────────────────────────┤
│  imports                       │  telethon, friendly_telegram, your deps
├────────────────────────────────┤
│  helpers / pure functions      │  define outside the class when self isn't used
├────────────────────────────────┤
│  @loader.tds                   │
│  class FooMod(loader.Module):  │
│      strings  = {...}          │  user-facing text (translatable)
│      config   = ModuleConfig() │  runtime-tunable settings (optional)
│      __init__                  │  config setup only
│      client_ready              │  async init, called once everything is wired
│      on_unload                 │  async tear-down, ≤ 5 s budget
│      *cmd, watcher,            │
│      *_inline_handler,         │
│      *_callback_handler        │
└────────────────────────────────┘
```

The class **name must end with `Mod`** — that's how the loader finds it.
There is exactly one `Mod` class per file.

---

## Lifecycle hooks

The loader calls these in order. None of them are mandatory, but most
non-trivial modules implement at least `client_ready`.

| Hook | Signature | When |
| ---- | --------- | ---- |
| `__init__` | `(self) -> None` | When the file is imported. **Sync** — don't do I/O here. The only normal use is `self.config = loader.ModuleConfig(...)`. |
| `config_complete` | `(self) -> None` | After `self.config` has been merged with persisted DB values. Sync. Use to validate config invariants. |
| `client_ready` | `async (self, client, db)` | After every client is connected and the inline manager is initialized. Save references, start background tasks here. |
| `on_unload` | `async (self) -> None` | On `.unloadmod`, reload, or shutdown. Hard 5-second timeout — cancel your tasks here, do not call `await client.send_message(...)` for cleanup. |

Background tasks: hold a strong reference. The framework's GC may otherwise
collect a fire-and-forget `asyncio.ensure_future(...)`.

```python
async def client_ready(self, client, db):
    self._db = db
    self._task = asyncio.create_task(self._loop())  # keep the ref!

async def on_unload(self):
    self._task.cancel()
```

---

## Commands

Any **coroutine** method whose name ends with `cmd` becomes a command. The
prefix-stripped method name is the command itself: `mycoolcmd` →
`.mycool`.

```python
async def echocmd(self, message: Message):
    """Echo the args back."""
    await utils.answer(message, utils.get_args_raw(message) or "(empty)")
```

Conventions used by `.help` and the framework:

- The **docstring** is the help text. Keep it ≤ 1 line.
- A `<args>` placeholder convention helps users: `"""<text> — Echo back."""`.
- Prefix the method with a [security decorator](#security-how-command-permissions-work) unless
  the command is genuinely safe for *anyone in any chat* (then
  `@loader.unrestricted`).
- Always reply via `utils.answer(message, …)` — it edits when the bot is the
  sender and replies otherwise, returns a list of resulting messages.

### Argument parsing

```python
utils.get_args_raw(message)              # "foo bar baz"
utils.get_args(message)                  # ["foo", "bar", "baz"] (shell-like)
utils.get_args_split_by(message, "|")    # split by custom separator
utils.get_target(message, arg_no=0)      # resolves a user — by reply, @username,
                                         # numeric ID, or message arg
```

`utils.get_args` does shell-style splitting (`shlex`) — wrap multi-word
arguments in quotes.

---

## Watchers (passive handlers)

A method literally named `watcher` is called for **every incoming message
that is not from the userbot itself**, including service messages
(joins, edits, etc.). Use sparingly — every message in every chat hits it.

```python
async def watcher(self, message: Message):
    if isinstance(message, types.MessageService):
        return
    if "🔔" in (message.raw_text or ""):
        await message.react("🤖")
```

Throw exceptions liberally — they are logged and don't crash the dispatcher.

---

## Inline manager: forms, galleries, callbacks

The inline manager (`self.inline`, available after `client_ready`) lets your
module render Telegram inline keyboards backed by an automatic `@BotFather`
bot.

### Inline forms

```python
@loader.owner
async def menucmd(self, message: Message):
    await self.inline.form(
        text="Pick an option:",
        message=message,
        reply_markup=[
            [{"text": "🟢 Yes", "callback": self._yes}],
            [{"text": "🔴 No",  "callback": self._no}],
        ],
        ttl=300,                 # seconds, default 24 h
        force_me=True,           # only the userbot owner can press
    )

async def _yes(self, call):
    await call.answer("You said yes!")
    await call.edit("✅ Confirmed.")
```

Each row is a list of buttons. A button is a dict with one of:

- `callback` — a coroutine `async def(call)`; receives an aiogram `CallbackQuery`.
- `url` — open URL.
- `input` — start a one-shot text-input flow; pair with `handler` callback.

### Inline galleries

```python
await self.inline.gallery(
    message=message,
    caption=lambda i: f"Page {i + 1}",
    next_handler=self._next_page,    # async (i) -> str | bytes (URL or photo)
    init_state=0,
    force_me=True,
)
```

### Inline-mode handlers

Methods ending with `_inline_handler` answer the bot's `inline_query`:

```python
async def myquery_inline_handler(self, query):
    if not query.query.startswith("hello"):
        return
    await query.answer([
        InlineQueryResultArticle(
            id=str(uuid.uuid4()),
            title="Say hi",
            input_message_content=InputTextMessageContent("hi!"),
        )
    ])
```

Methods ending with `_callback_handler` receive callback queries that
weren't bound to a specific form button.

See [`inline.md`](inline.md) for legacy notes on the inline API.

---

## Strings and translations

`strings` is *not* a plain dict at runtime — `@loader.tds` rewrites it into a
`Strings` object that:

- exposes attribute lookup (`self.strings["hi"]`) **and** call lookup
  (`self.strings("hi", message)`),
- merges in translations from any langpack registered with `.langpack`,
- fills `_cmd_doc_<name>` and `_cls_doc` with command/class docstrings
  automatically so they are translatable too.

```python
strings = {
    "name": "MyMod",                    # required, shown in .help
    "ok":   "✅ <b>Done.</b>",
    "fail": "🚫 <b>Couldn't: {}</b>",
}

await utils.answer(message, self.strings("ok", message))
await utils.answer(
    message,
    self.strings("fail", message).format(reason),
)
```

Always pass `message` as the second argument so per-chat language
preferences apply.

### Style guide

The project uses a single style for all user-facing strings:

- **Pattern**: `<emoji> <b>text</b>` — emoji *outside* the bold.
- **Semantics**:
  - `✅` success, `🚫` refusal/error, `⚠️` warning, `❓` prompt
  - `🔄` in-progress / restart, `📥` download, `📤` upload, `🔍` search
  - `ℹ️` info, `🤖` bot status, `🗑` delete

Run the project's lint to verify:

```sh
uv run python -c "
import ast, glob
for path in glob.glob('friendly_telegram/modules/*.py'):
    with open(path) as f: src = f.read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict): continue
        for k, v in zip(node.keys, node.values):
            if not isinstance(k, ast.Constant) or not isinstance(v, ast.Constant): continue
            if k.value == 'name' or k.value.startswith('_'): continue
            if v.value.startswith('<b>') and not v.value.startswith('<b><'):
                print(path, k.lineno, repr(v.value)[:60])
"
```

---

## Config (`ModuleConfig`)

For runtime-tunable settings (URLs, thresholds, feature flags) use
`loader.ModuleConfig`:

```python
def __init__(self):
    self.config = loader.ModuleConfig(
        "GREETING", "Hello",       lambda m: self.strings("greeting_doc", m),
        "MAX_TRIES", 3,            "How many times to retry on failure",
    )

async def client_ready(self, client, db):
    msg = self.config["GREETING"]            # current value
    default = self.config.getdef("GREETING") # original default
    doc = self.config.getdoc("GREETING")     # description for .config
```

The user adjusts these via `.config <ModuleName> <KEY> <value>`. Values are
persisted in the database under the module's `__module__` namespace.

---

## Database

A small async-friendly key-value store (JSON file under
`~/.local/share/friendly-telegram/config-<user_id>.json`).

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

---

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

> **Migration note**: in older FTG versions `fetch_asset` returned a
> Telethon `Message`. Local storage returns raw bytes. If you need to send
> them onward, pass them to `client.send_file(chat, file=raw)`.

Files live under `~/.local/share/friendly-telegram/assets/<user_id>/<id>.bin`.

---

## The `utils` cheatsheet

Imported as `from friendly_telegram import utils`.

| Helper | Purpose |
| ------ | ------- |
| `answer(message, text, **kwargs)` | Edit if our message, reply otherwise. Returns a list of resulting messages. |
| `get_args(message)` / `get_args_raw` | Parsed / raw argument string. |
| `get_args_split_by(message, sep)` | Split by custom separator. |
| `get_chat_id(message)` | Numeric chat ID without the `-100` channel prefix. |
| `get_target(message, arg_no=0)` | Resolve a user from reply / username / arg / ID. Returns `int` or `None`. |
| `get_user(message)` | Sender as a Telethon `User`. Resolves cache misses. |
| `escape_html(text)` | Escape `<`, `>`, `&`. |
| `escape_quotes(text)` | Same plus `"`. |
| `get_base_dir()` | Installed package directory (read-only). |
| `get_data_dir()` | Writable data directory (sessions, configs, modules, assets). |
| `get_platform_name()` | Display name for `.info` ("📻 VDS", "📱 Termux", …). Honors `$GTG_PLATFORM`. |
| `run_sync(func, *a, **k)` | Run a blocking call in the default executor. |
| `relocate_entities(entities, offset, text=None)` | Adjust message-entity offsets after slicing text. |
| `merge(a, b)` | Deep-merge two dicts. |
| `rand(n)` | Random alphanumeric string of length *n*. |
| `install_requirements(pkgs, user_install=False)` | Pip-install at runtime, picks `uv pip` when available. |
| `print_web_urls(port)` | Pretty-print all reachable URLs (used at startup). |

For full signatures, read [`friendly_telegram/utils.py`](../friendly_telegram/utils.py).

---

## Security: how command permissions work

Permissions are a **13-bit bitmask** stored on each command function as
`func.security`. Before dispatching the command, `SecurityManager.check()`
([`friendly_telegram/security.py`](../friendly_telegram/security.py))
combines that mask with runtime overrides and decides whether the caller
is allowed.

### The 13 flags

| Flag | Meaning |
| ---- | ------- |
| `OWNER` | The userbot account itself, plus user IDs in the `owner` group. |
| `SUDO` | User IDs in the `sudo` group. |
| `SUPPORT` | User IDs in the `support` group. |
| `GROUP_OWNER` | Creator of the chat/channel where the command was sent. |
| `GROUP_ADMIN_ADD_ADMINS` / `..._CHANGE_INFO` / `..._BAN_USERS` / `..._DELETE_MESSAGES` / `..._PIN_MESSAGES` / `..._INVITE_USERS` | Admin who has the matching Telegram admin right. |
| `GROUP_ADMIN` | Any admin (no specific right required). |
| `GROUP_MEMBER` | Any participant of the current group. |
| `PM` | Private messages only. |

### Decorators

Each decorator just sets a bit on `func.security`. They are additive
(`@loader.sudo` is `OWNER | SUDO`, not just `SUDO`).

| Decorator | Bits set |
| --------- | -------- |
| `@loader.owner` | `OWNER` |
| `@loader.sudo` | `OWNER \| SUDO` |
| `@loader.support` | `OWNER \| SUDO \| SUPPORT` |
| `@loader.group_owner` | `OWNER \| SUDO \| GROUP_OWNER` |
| `@loader.group_admin` | `OWNER \| SUDO \| GROUP_ADMIN` |
| `@loader.group_admin_<right>` | `OWNER \| SUDO \| GROUP_ADMIN_<RIGHT>` |
| `@loader.group_member` | `OWNER \| SUDO \| GROUP_MEMBER` |
| `@loader.pm` | `OWNER \| SUDO \| PM` |
| `@loader.unrestricted` | All 13 bits |

Stacking is allowed — apply two decorators and their bits OR together:

```python
@loader.group_admin_ban_users
@loader.pm
async def kickcmd(self, message): ...
```

If you don't apply any decorator, the command falls back to
`DEFAULT_PERMISSIONS` = `OWNER | SUDO`.

### Runtime overrides (per-command)

The user can rebind any command's mask without restarting via
`.security <command>` (an inline keyboard from the
[`GeekSecurity`](../friendly_telegram/modules/geek_security.py) module).
The override is stored at `db["security"]["masks"][f"{module}.{func}"]`
and **replaces** the decorator value on every check. Your decorator is
just the default — never assume it's still in effect at runtime.

### Bounding mask (global ceiling)

`db["security"]["bounding_mask"]` (default `OWNER | SUDO`) is AND-ed over
the final mask of every command. If a bit is cleared here, no command
honours it anywhere — useful for "lock everything down to owner-only"
without touching individual commands. Configured via `.security` (with
no argument).

Effective mask:

```text
effective = (override or func.security or DEFAULT_PERMISSIONS) & bounding_mask
```

### User groups: `owner`, `sudo`, `support`

Three lists of Telegram user IDs in the database:

- `db["security"]["owner"]` — extra owners. The userbot account itself
  is *always* treated as owner; this list is for adding co-owners.
- `db["security"]["sudo"]` — sudoers. The userbot account is auto-added
  on every check.
- `db["security"]["support"]` — read-only/support users.

Managed by:

```text
.owneradd / .ownerrm / .ownerlist
.sudoadd  / .sudorm  / .sudolist
.supportadd / .supportrm / .supportlist
```

Adding to any group goes through an inline confirmation prompt because
it grants real access to the userbot.

The lists are re-read from the DB on **every** permission check, so
changes take effect immediately.

### Decision flow

When `SecurityManager.check(message, func)` runs:

1. Compute the effective mask. If `0` → deny.
2. If `OWNER` bit set and `sender_id` is the userbot or in `owner`
   list → **allow**.
3. Same for `SUDO`/`sudo` list and `SUPPORT`/`support` list.
4. If `sender_id` is in `db["main"]["blacklist_users"]` → **deny**
   (overrides everything below).
5. If `PM` bit set and the message is a DM → **allow**.
6. If `GROUP_MEMBER` bit set and the message is in a group → **allow**.
7. Channel/supergroup: query the participant via
   `GetParticipantRequest`, then:
   - `ChannelParticipantCreator` satisfies `GROUP_OWNER`.
   - `ChannelParticipantAdmin` satisfies `GROUP_ADMIN_<RIGHT>` only if
     the participant's `admin_rights.<right>` is true. `GROUP_ADMIN`
     matches any admin.
   - The toggle `db["security"]["any_admin"]` (`False` by default)
     loosens this so any admin satisfies any `GROUP_ADMIN_*` flag.
8. Legacy chat: same idea with `GetFullChatRequest` /
   `ChatParticipantCreator` / `ChatParticipantAdmin`.
9. Otherwise → **deny** (and the dispatcher silently drops the command).

### Picking the right decorator

- **Mutating, sensitive, or account-wide commands** (eval, restart,
  config, account settings): `@loader.owner` or `@loader.sudo`.
- **Group moderation**: the matching `@loader.group_admin_*` so a
  co-admin can use it where they have rights, and only there.
- **Public read-only commands** (`.alive`, `.ping`, fun/info modules):
  `@loader.unrestricted` *unless* you want them limited to your
  contacts via the bounding mask.
- **Anything that takes user input as a target** (e.g. fetch info about
  another user): pair the decorator with `@loader.ratelimit` to make
  it harder to abuse.

### Rate limiting

`@loader.ratelimit` is **orthogonal** to security — it enforces a
per-user cooldown on top of whatever permission check applies. Always
apply a security decorator as well; rate-limit alone does not gate
access.

---

## Module headers and metadata directives

The loader scans the **first comments** of a module file for directives:

```python
# meta developer: @your_handle
# meta desc: One-line module description shown by some module browsers.
# meta pic: https://example.com/preview.png

# requires: pillow numpy ffmpeg-python

# scope: ffmpeg
# scope: geektg_min 4.0.0
```

| Directive | Effect |
| --------- | ------ |
| `# meta developer:` | Author handle, displayed by `.help` and module-browser modules. |
| `# meta desc:` / `# meta pic:` | Optional metadata for browsers. |
| `# requires: <pkg> <pkg>...` | The loader auto-installs these via `uv pip` (or `pip` fallback) on import error. |
| `# scope: ffmpeg` | The loader refuses to load the module if `ffmpeg` isn't on PATH. |
| `# scope: geektg_min X.Y.Z` | Refuses to load on older GeekTG versions. |

The directives must be in the file header (before the first `import`).

---

## Distribution and loading

A user installs your module in one of three ways:

1. **`.loadmod` reply / file**: reply to a `.py` file with `.loadmod`, or
   send the file with `.loadmod` as the caption. The loader saves it under
   `loaded_modules/<ClassName>.py`.
2. **`.loadmod <url>`**: a raw URL to a `.py` file (GitHub raw, gist, …).
3. **`.dlmod <name>`**: search and install from a configured module
   repository (see `.cfg loader REPO_CONFIG_URL`).

Modules persist across restarts because the `.py` source itself is stored
on disk. To uninstall: `.unloadmod <ClassName>` (removes the file too).

---

## Best practices and pitfalls

- **Hold strong refs to background tasks.** `asyncio.ensure_future(...)`
  with no return-value capture *will* be GC'd in Python 3.11+. Save the
  task on `self`.
- **Don't block the loop.** Wrap blocking SDK calls in `await
  utils.run_sync(func, *args)`.
- **Don't import the package as `friendly-telegram`** (with the dash). Use
  `friendly_telegram` or relative imports (`from .. import utils`). The
  hyphenated name is shimmed for backwards compat but new code should be
  clean.
- **`message` arg style**: every command and watcher receives a Telethon
  `Message`. After `await utils.answer(...)` the *original* message is gone
  if the bot edited it; use the return value for follow-ups.
- **Ratelimit your own background work.** Telegram's flood thresholds are
  surprisingly tight. Use `await asyncio.sleep(...)` between bulk
  operations.
- **Test on a throwaway account first.** Userbots violate Telegram's ToS.
- **Restart vs reload.** `.loadmod` with the same class name reloads in
  place — your `on_unload` runs and a fresh instance is created. Some state
  (open sockets, aiogram handlers) survives only across full `.restart`.
- **Logging.** `import logging; logger = logging.getLogger(__name__)`.
  Default visible level is `INFO` — use `logger.debug` for noisy traces.

---

## Where to look in the codebase

- [`friendly_telegram/loader.py`](../friendly_telegram/loader.py) — the
  `Module` base class, `tds` decorator, registration logic.
- [`friendly_telegram/dispatcher.py`](../friendly_telegram/dispatcher.py) —
  command parsing, security checks.
- [`friendly_telegram/security.py`](../friendly_telegram/security.py) —
  permission predicates behind `@loader.owner` & friends.
- [`friendly_telegram/inline.py`](../friendly_telegram/inline.py) — inline
  forms, galleries, callback handling.
- [`friendly_telegram/modules/`](../friendly_telegram/modules/) — bundled
  core modules. Best living examples.

When in doubt, copy a small core module (`bot_token.py`, `nocollisions.py`)
and modify from there.
