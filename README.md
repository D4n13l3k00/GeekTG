# GeekTG · Friendly Telegram, refreshed

A Telegram **userbot** with an inline-bot companion, a tiny web UI for first-time
setup, and a pluggable third-party module system.

Originally based on
[friendly-telegram/friendly-telegram](https://github.com/friendly-telegram/friendly-telegram),
forked by GeekTG, then frozen for a couple of years. I picked the codebase up
because it still beats most modern alternatives at *being a userbot*: small,
hackable, no telemetry, no SaaS — and brought it back to life on top of the
2026 Python toolchain.

> ⚠️ Userbots violate Telegram's ToS. Run them on a number you can afford to
> lose. Don't use the default API credentials in production — get your own at
> [my.telegram.org/apps](https://my.telegram.org/apps).

---

## What changed in this refresh

Nothing user-visible was rewritten — the module API, the inline manager, the
security/rate-limit decorators, the dispatcher are all intact. **Third-party
modules keep working** thanks to a shim that exposes the package under the
historic ``friendly-telegram`` name.

What did change:

- 🐍 **Python** packaging on `pyproject.toml` (hatchling) instead of the old
  bash installer / `requirements.txt`. Builds a normal wheel, ships an `gtg`
  console script.
- 📦 **`uv` / `pipx` install** — one command, no manual venvs, no system pip
  needed (we bootstrap it lazily for third-party modules that bring their own
  deps).
- 🪪 **Telethon 1.43** (upstream, not the Mod fork) with a current
  Pixel/Android device fingerprint so Telegram delivers login codes reliably.
- 🗂 **Local-only storage** — config, sessions, modules and assets live under
  `~/.local/share/friendly-telegram/` (XDG-compliant). The cloud channels
  (`friendly-<uid>-data`, `friendly-<uid>-assets`) are gone — no more rogue
  channels in your chat list, no Telegram-flood-wait on every config write.
- 🌐 **Web UI rewritten** — clean two-step wizard in Russian, animated aurora
  background, dark SweetAlerts, profile card on the dashboard with
  masked phone (`+7********10`) and a "Open Saved Messages" button.
- 🛡 **Graceful Ctrl-C / SIGTERM** — no more 20-line tracebacks on shutdown.
- 🧹 **Removed**: Heroku/Okteto deploy paths, install.sh / install.ps1,
  `meval`-based Python eval (still around as a module, but the ambient one is
  gone), git-based self-update (replaced with a stub pointing at
  `uv tool upgrade`).
- 🩹 **Quality fixes** — circular import broken, `asyncio.run()` instead of
  `get_event_loop()`, hot-path `SuperList` lookup no longer rebuilds closures
  on every attribute access, `on_unload` tasks held by strong refs so they
  don't get GC'd mid-flight, structured logging defaults.

Full notes: [`CHANGELOG`](docs/) (forthcoming) — for now `git log` is the
authoritative source.

---

## Install

### Option A — `uv` (recommended)

```sh
uv tool install git+https://github.com/GeekTG/Friendly-Telegram
gtg
```

`uv` is a single-binary Python toolchain — installer at
[astral.sh/uv](https://astral.sh/uv). It pins the exact Python version, builds
the wheel and isolates dependencies. Upgrades are `uv tool upgrade gtg`.

### Option B — `pipx`

```sh
pipx install git+https://github.com/GeekTG/Friendly-Telegram
gtg
```

### Option C — Docker / Compose

```sh
docker compose up -d --build
docker compose logs -f gtg
```

The provided [`docker-compose.yml`](docker-compose.yml) mounts a named volume
at the data directory so sessions survive `docker compose down`.

### Option D — From source

```sh
git clone https://github.com/GeekTG/Friendly-Telegram
cd Friendly-Telegram
uv sync
uv run gtg
```

---

## First run

```sh
gtg
```

Prints a startup banner with the resolved data directory, then opens a small
web wizard on a free local port. The URL is shown on stdout — for example:

```text
🌐 Web UI is ready. Open one of:
  • http://localhost:8888       (this machine only)
  • http://192.168.1.42:8888    (local network)
  • http://203.0.113.7:8888     (public — make sure port is open)
```

The wizard walks you through:

1. **API keys** — get them at [my.telegram.org/apps](https://my.telegram.org/apps).
2. **Phone number** — international format, e.g. `+79991234567`.
3. **Confirmation code** — Telegram delivers it to *another logged-in
   Telegram session* if you have one (in the chat with “Telegram”), otherwise
   via SMS.
4. **2FA password** if your account has cloud password enabled.

After that, the dashboard shows your profile and a single button to open
*Saved Messages* (your chat-with-self) in Telegram so you can start running
commands like `.help`, `.info`, `.loadmod`.

---

## Useful CLI flags

| Flag | What |
| ---- | ---- |
| `gtg --print-data-dir` | Print the resolved data directory and exit |
| `gtg --data-root /path` | Override the data directory for this run |
| `gtg --platform "My VPS"` | Override platform name shown in `.info` (also `$GTG_PLATFORM`) |
| `gtg --port 8888` | Pin the web port (random free port by default) |
| `gtg --no-web` | Skip the web UI; configure via terminal |
| `gtg --no-inline` | Disable the inline-bot companion |
| `gtg --root` / `-R` | Allow running as `root` (don't, unless in a container) |
| `gtg --setup` | Re-enter the configurator with the existing session |

Full list: `gtg --help`.

---

## Where everything lives

Default data root is `$XDG_DATA_HOME/friendly-telegram` (typically
`~/.local/share/friendly-telegram`). Override with `$GTG_DATA_DIR` or
`--data-root`.

```text
~/.local/share/friendly-telegram/
├── config.json                      # global + per-user app config
├── api_token.txt                    # api_id / api_hash
├── config-<user_id>.json            # per-account module DB (was the cloud channel)
├── friendly-telegram-+7…1234.session
├── loaded_modules/                  # third-party .py modules saved by .loadmod
└── assets/<user_id>/                # binary blobs stored by store_asset()
```

Backup = `tar czf gtg.tgz ~/.local/share/friendly-telegram/`. Restore =
extract on the new host, run `gtg`. No Telegram-side state to migrate.

---

## Inline bot

`InlineManager` registers an inline-mode bot via `@BotFather` automatically on
first run, used by core/third-party modules for inline buttons, galleries and
forms. To use your own bot instead:

```text
.setbottoken 123456789:AA…
.restart
```

Other commands: `.bottoken` (show current bot, token redacted),
`.resetbottoken` (clear and recreate on next start).

---

## Writing modules

Modules are plain `.py` files; the loader picks up classes whose names end
with `Mod` and inherit from `friendly_telegram.loader.Module`. The historic
package alias is preserved, so existing modules with `from .. import loader,
utils` keep working.

Minimal example:

```python
# requires: pillow
from telethon.tl.types import Message
from .. import loader, utils

@loader.tds
class HelloMod(loader.Module):
    """Friendly hello."""

    strings = {
        "name": "Hello",
        "hi": "👋 <b>Hello, {}!</b>",
    }

    @loader.unrestricted
    async def hicmd(self, message: Message):
        """Say hi."""
        await utils.answer(message, self.strings("hi", message).format(
            (await message.client.get_me()).first_name,
        ))
```

Drop it in `~/.local/share/friendly-telegram/loaded_modules/HelloMod.py`
(or load via `.loadmod` from a URL/file). The `# requires: pillow` directive
auto-installs missing pip dependencies into the active environment — works
in `uv tool` venvs that don't ship pip.

---

## Status & roadmap

This is a maintenance / modernization fork. Goals, in order:

1. ✅ Make it install and boot on Python 3.11 / 3.12 (done).
2. ✅ Drop external dependencies that no longer exist (Heroku, Okteto, Telethon-Mod).
3. ✅ Local-only data store, friendlier first-run experience.
4. 🟡 Better module developer UX — type hints, ruff/black, smaller monoliths
   (`inline.py`, `dispatcher.py`).
5. 🟡 Real self-update path that works for wheel installs (currently a stub
   pointing at `uv tool upgrade`).
6. 🟡 Documentation refresh — the upstream `docs.geektg.tk` is offline; new
   docs will live under [`docs/`](docs/).

Issues and PRs welcome. If you maintained a third-party FTG module and
something broke after this refresh, open an issue with a stack trace —
backwards compatibility is a hard goal, not a soft one.

---

## License

GNU AGPL v3 — see [`LICENSE`](LICENSE).
Originally Copyright © 2018-2022 The Friendly-Telegram Authors, modded by the
GeekTG team, refresh by the current maintainer.
