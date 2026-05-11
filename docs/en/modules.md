# Writing modules

Modules are the unit of extension for GeekTG. Each module is a single Python
file that defines one class with userbot commands, message watchers, inline
handlers and persistent state. The loader picks them up at startup or on
demand via `.loadmod`.

This doc covers the canonical module layout, the lifecycle, and the small
foot-guns that aren't obvious from the code. Topics with their own pages
(inline forms, security, database, utils) are linked inline.

> Use `from telethon.tl.custom import Message` for handler signatures.
> The `tl.types.Message` class lacks `.edit`, `.delete`, `.respond`,
> `.get_reply_message`, `.is_reply`, `.raw_text` — the ones every
> handler in the codebase relies on.

---

## Table of contents

1. [The five-minute module](#the-five-minute-module)
2. [Anatomy of a module](#anatomy-of-a-module)
3. [Lifecycle hooks](#lifecycle-hooks)
4. [`self.ctx` — unified DI bundle](#selfctx--unified-di-bundle)
5. [Commands](#commands)
6. [Watchers (passive handlers)](#watchers-passive-handlers)
7. [Inline manager](#inline-manager) — see also **[inline.md](inline.md)**
8. [Strings and translations](#strings-and-translations)
9. [Config (`ModuleConfig`)](#config-moduleconfig)
10. [Database and assets](#database-and-assets) — see **[database.md](database.md)**
11. [Utils cheatsheet](#utils-cheatsheet) — see **[utils.md](utils.md)**
12. [Security](#security) — see **[security.md](security.md)**
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

from telethon.tl.custom import Message
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
            self.tr("hi", message).format(name=sender.first_name),
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

```text
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
| `client_ready` | `async (self, client, db)` | After every client is connected and the inline manager is initialized. Optional — modern code reads `self.ctx` directly. Override only when you need to start background tasks or do async one-time setup. |
| `on_unload` | `async (self) -> None` | On `.unloadmod`, reload, or shutdown. Hard 5-second timeout — cancel your tasks here, do not call `await client.send_message(...)` for cleanup. |

Background tasks: hold a strong reference. The framework's GC may otherwise
collect a fire-and-forget `asyncio.ensure_future(...)`.

```python
async def client_ready(self, client, db):
    self._task = asyncio.create_task(self._loop())  # keep the ref!

async def on_unload(self):
    self._task.cancel()
```

---

## `self.ctx` — unified DI bundle

The framework populates `self.ctx` (a frozen `ModuleContext` dataclass)
**before `client_ready` runs**, so it's available everywhere a module's
methods can possibly execute: commands, watchers, inline handlers,
callback handlers, form callbacks, background tasks.

```python
@dataclass(frozen=True)
class ModuleContext:
    client:     TelegramClient        # the userbot's main client
    db:         Database              # KV store + asset blobs
    inline:     InlineManager         # same object as self.inline
    modules:    Modules               # loader (other modules, watchers, …)
    allclients: Sequence[TelegramClient]
    log:        Callable[..., Any]    # framework log helper
    origin:     str                   # "<file>" or load source
```

Prefer reading `self.ctx.X` over copying things into `self._client = client`
inside `client_ready` — that boilerplate is legacy. The frozen dataclass
also means a misbehaving module can't swap the loader's view of the world
out from under itself.

```python
@loader.tds
class FooMod(loader.Module):
    """Demo of self.ctx usage."""

    @loader.owner
    async def hellocmd(self, message: Message):
        # In commands you can use either message.client or self.ctx.client —
        # they're the same object. Use self.ctx when there's no message.
        me = await self.ctx.client.get_me()
        self.ctx.db.set(__name__, "last_run_by", me.id)
        await utils.answer(message, f"Hi, {me.first_name}!")

    async def on_btn(self, call):
        # Inline-form callbacks don't have a Telethon Message — self.ctx
        # is how you reach the client and DB from here.
        await self.ctx.client.send_message("me", "Button pressed!")
```

### When to still override `client_ready`

- Starting background tasks (`asyncio.create_task(...)`) — you need
  somewhere to put the spawn call, and `client_ready` is the canonical
  place. Hold the task on `self`.
- Async one-time setup that depends on the client being connected
  (e.g. `self._me = await client.get_me()` if you need it eagerly).
- Legacy modules that still do `self._db = db; self._client = client` —
  these keep working but should migrate to `self.ctx` over time.

You do **not** need to override it just to "save references" any more.

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
- Prefix the method with a [security decorator](security.md#decorators) unless
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

### `aiogram_watcher` (private DMs to the inline bot)

A separate hook fires for **messages sent privately to the inline bot**
(not the userbot). Use it for state machines, FSM-like flows, or
"send the next photo" prompts after an inline form.

```python
async def aiogram_watcher(self, message):
    # message is a native aiogram.types.Message
    if message.text == "ping":
        await message.answer("pong")
```

The bot's `parse_mode` defaults to `HTML` (set globally via
`DefaultBotProperties`), so `message.answer("<b>hi</b>")` works without
extra arguments.

### Disabling watchers per-instance

The user can disable any watcher with `.watcherbl <ModuleName>`; the list
lives at `db["friendly_telegram.main"]["disabled_watchers"]`. The
dispatcher consults it on every dispatch, so toggling is instant.

---

## Inline manager

The inline manager (`self.inline`, available after `client_ready`) lets your
module render Telegram inline keyboards backed by an automatic `@BotFather`
bot — forms, galleries, `*_inline_handler` and `*_callback_handler` methods.

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
        ttl=300,
        force_me=True,
    )

async def _yes(self, call):     # call: friendly_telegram.inline.types.InlineCall
    await call.answer("You said yes!")
    await call.edit("✅ Confirmed.")
```

Form callbacks receive an `InlineCall` wrapper (not a raw aiogram
`CallbackQuery` — aiogram-3 events are frozen pydantic models). On it:

- `call.delete()` / `call.unload()` / `call.edit(...)` / `call.form` — our
  form-stateful helpers.
- Native aiogram attributes (`call.answer`, `call.from_user`, `call.data`,
  `call.message`, `call.bot`, …) are delegated through.

Use `self.inline.bot` (a normal `aiogram.Bot`) when you need to call the Bot
API directly.

The full reference — button types, gallery / `_inline_handler` /
`_callback_handler` examples, the v2-→-v3 migration notes — lives in
**[inline.md](inline.md)**.

---

## Strings and translations

Class-level `strings` is a `dict` literal at definition time. After
`@loader.tds` runs (during `send_config_one`) the framework swaps it
for a `Strings` object that:

- exposes attribute lookup (`self.strings["hi"]`) **and** call lookup
  (`self.strings("hi", message)`),
- merges in translations from any langpack registered with `.langpack`,
- fills `_cmd_doc_<name>` and `_cls_doc` with command/class docstrings
  automatically so they are translatable too.

Because the type changes underfoot, type checkers can't follow
`self.strings(...)`. Use **`self.tr(key, message=None)`** in module
code — it's a real method that wraps `self.strings(key, message)`:

```python
strings = {
    "name": "MyMod",                    # required, shown in .help
    "ok":   "✅ <b>Done.</b>",
    "fail": "🚫 <b>Couldn't: {}</b>",
}

await utils.answer(message, self.tr("ok", message))
await utils.answer(
    message,
    self.tr("fail", message).format(reason),
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
        "GREETING", "Hello",       lambda m: self.tr("greeting_doc", m),
        "MAX_TRIES", 3,            "How many times to retry on failure",
    )

async def client_ready(self, client, db):
    msg = self.config["GREETING"]            # current value
    default = self.config.getdef("GREETING") # original default
    doc = self.config.getdoc("GREETING")     # description for .config
```

Entries are passed in `(KEY, default, doc)` triples (positionally; the
`ModuleConfig.__init__` chunks them by `i % 3`). `doc` may be a string
or a `callable(message)` returning a string for translatable docs.

The user adjusts these via `.config <ModuleName> <KEY> <value>`. Values are
persisted in the database under the module's `__module__` namespace.

---

## Database and assets

JSON KV store + binary blob storage. Use `db.get(__name__, key, default)` /
`db.set(__name__, key, value)` for module-private state, `db.store_asset()` /
`db.fetch_asset()` for media.

```python
@loader.owner
async def bumpcmd(self, message: Message):
    db = self.ctx.db
    db.set(__name__, "counter", db.get(__name__, "counter", 0) + 1)
```

Full reference: **[database.md](database.md)**.

---

## Utils cheatsheet

`from friendly_telegram import utils` exposes `answer`, `get_args`,
`escape_html`, `get_chat_id`, `run_sync`, `merge`, `rand`, `get_data_dir`,
`install_requirements`, `get_platform_name`, and a few more. The full table
with one-line descriptions: **[utils.md](utils.md)**.

---

## Security

Permissions are a **13-bit bitmask** stored on each command function as
`func.security`, AND-ed with the global `bounding_mask` and possibly
overridden per-command at runtime via `.security <command>`. Default for an
undecorated command is `OWNER | SUDO`. Decorators set bits:

```python
@loader.owner          # OWNER only
@loader.sudo           # OWNER | SUDO
@loader.unrestricted   # everyone
@loader.group_admin_ban_users
@loader.pm
async def kickcmd(self, message): ...
```

Decorators stack (their bits OR together). `@loader.ratelimit` is
orthogonal — it doesn't gate access, it only throttles.

Full reference (all 13 flags, decorators, decision flow, bounding mask, user
groups): **[security.md](security.md)**.

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

### Internal registration flow

When the loader picks up a module file (boot or `.loadmod`):

1. **Import.** The `.py` is imported via `importlib`, registered in
   `sys.modules` under a synthetic name (`friendly_telegram.modules.<name>`
   for bundled modules, `loaded_modules.<ClassName>` for user files).
2. **Class discovery.** The loader scans for a class ending in `Mod` that
   subclasses `loader.Module`. There must be exactly one — extras are
   ignored.
3. **Replace existing.** If a module with the same class name is already
   loaded, `on_unload()` runs on the old instance (5 s timeout) and its
   commands/watchers are removed from the global dispatcher.
4. **`config_complete`.** `mod.config` is hydrated from DB / env / defaults
   and `config_complete()` is invoked. `@loader.tds` injects translated
   docstrings here.
5. **`ctx` set.** `mod.ctx = ModuleContext(...)` — the unified DI bundle.
6. **`client_ready`.** All modules' `client_ready` run in parallel
   (`asyncio.gather`). After they all finish, `_client_ready2` runs (also
   in parallel) — internal hook for core modules only.
7. **Handler discovery.** `*cmd`, `*_inline_handler`, `*_callback_handler`,
   `watcher`, `aiogram_watcher` are introspected and registered with the
   dispatcher / inline manager.

`.unloadmod` reverses steps 7 → 3 in order: deregister handlers, run
`on_unload`, drop from `sys.modules`, delete the source file.

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

- [`friendly_telegram/loader.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/loader.py) — the
  `Module` base class, `tds` decorator, registration logic.
- [`friendly_telegram/dispatcher.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/dispatcher.py) —
  command parsing, security checks.
- [`friendly_telegram/security.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/security.py) —
  permission predicates behind `@loader.owner` & friends.
- [`friendly_telegram/inline/`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/inline/) — inline
  manager package: `manager.py` (lifecycle/dispatch), `types.py` (the
  `InlineCall` wrapper, helpers).
- [`friendly_telegram/modules/`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/modules/) — bundled
  core modules. Best living examples.

When in doubt, copy a small core module (`bot_token.py`, `nocollisions.py`)
and modify from there.
