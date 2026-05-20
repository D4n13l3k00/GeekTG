<div align="center">

# GeekTG · Friendly Telegram Refork (by GeekTG)

[🇷🇺 Russian version](README.md)

[![Python](https://img.shields.io/badge/python-3.11%20%E2%80%93%203.14-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Version](https://img.shields.io/badge/version-4.4.3-informational)](https://github.com/D4n13l3k00/GeekTG/releases)
[![License](https://img.shields.io/badge/license-AGPL--3.0--or--later-green)](LICENSE)
[![Telethon](https://img.shields.io/badge/telethon-1.40%2B-blue?logo=telegram&logoColor=white)](https://github.com/LonamiWebs/Telethon)
[![uv](https://img.shields.io/badge/uv-ready-blueviolet?logo=astral)](https://github.com/astral-sh/uv)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000)](https://github.com/psf/black)

</div>

> ⚠️ Userbots violate Telegram's ToS. Run them on a number you can afford to lose. Don't use the default API credentials in production — get your own at [my.telegram.org/apps](https://my.telegram.org/apps).

Telegram **userbot** with an inline-bot companion, a small web UI for initial setup, and a third-party module system.

Originally based on [friendly-telegram/friendly-telegram](https://github.com/friendly-telegram/friendly-telegram), forked by GeekTG ([GeekTG/Friednly-Telegram](https://github.com/GeekTG/Friednly-Telegram)), then abandoned after the team lost interest. I picked up the last release and updated it for modern dependencies and tooling.

---

## 🔀 What changed in this fork

The module API changed slightly (old modules still work) — see the [documentation](/docs/).
Docs are also available on [GitHub Pages](https://d4n13l3k00.github.io/GeekTG).

**What's new?** Quite a lot: updated web UI, animated emoji support, Pylance typings. Most importantly, the bot can now be installed via uv as a package with full typing support for module development.

---

## 📦 Installation

### Option A — `uv` (recommended)

```bash
uv tool install git+https://github.com/D4n13l3k00/GeekTG # --python 3.13 to pin a specific version
gtg
```

`uv` is a single-binary Python toolchain — installer at [astral.sh/uv](https://astral.sh/uv). Pins the exact Python version, builds a wheel, and isolates dependencies. To update: `uv tool upgrade gtg`.

### Option B — From source

```bash
git clone https://github.com/D4n13l3k00/GeekTG
cd GeekTG
uv sync
uv run gtg
```

### Option C — Docker / Compose

```bash
docker compose up -d --build
docker compose logs -f gtg
```

[`docker-compose.yml`](docker-compose.yml) mounts a named volume on the data directory so sessions survive `docker compose down`.

---

## 🚀 First run

Prints a banner with the data directory and opens a web wizard on a free port:

```yaml
🌐 Web UI is ready. Open one of:
  • http://localhost:8888       (this machine only)
  • http://192.168.1.42:8888    (local network)
  • http://203.0.113.7:8888     (public — make sure the port is open)
```

The wizard walks you through:

1. **API credentials** — get them at [my.telegram.org/apps](https://my.telegram.org/apps).
2. **Phone number** — international format, e.g. `+19991234567`.
3. **Confirmation code** — Telegram sends it to another logged-in session (the "Telegram" chat), otherwise by SMS.
4. **2FA password**, if enabled.

After that the dashboard shows your profile and a button to open *Saved Messages* — type commands there like `.help`, `.info`, `.loadmod`.

---

## ⚙️ CLI flags

| Flag | What it does |
| ---- | ------------ |
| `gtg --print-data-dir` | Print the data directory and exit |
| `gtg --data-root /path` | Override the data directory |
| `gtg --platform "My VPS"` | Override the platform name in `.info` (or `$GTG_PLATFORM`) |
| `gtg --port 8888` | Fix the web UI port (random by default) |
| `gtg --no-web` | No web UI |
| `gtg --no-inline` | Disable the inline bot |
| `gtg --root` / `-R` | Allow running as `root` (containers only) |
| `gtg --setup` | Enter the configurator with an existing session |

Full list — `gtg --help`.

---

## 📁 Data layout

Default data root — `~/.local/share/friendly-telegram` (`$XDG_DATA_HOME/friendly-telegram`). Override via `$GTG_DATA_DIR` or `--data-root`.

```shell
~/.local/share/friendly-telegram/
├── config.json                      # global + per-user config
├── api_token.txt                    # api_id / api_hash
├── config-<user_id>.json            # per-account module DB
├── friendly-telegram-+1…1234.session
├── loaded_modules/                  # third-party .py files loaded via .loadmod
└── assets/<user_id>/                # binary blobs from store_asset()
```

Backup and restore are available directly in the web UI. Or manually: `tar czf gtg.tgz ~/.local/share/friendly-telegram/` — unpack on a new host and run `gtg`.

---

## 🧩 Writing modules

See the [documentation](https://d4n13l3k00.github.io/GeekTG/modules/).

---

## 🗺️ Status & roadmap

This is a maintenance/modernization fork. Goals in order:

1. ✅ Install and run on Python 3.10 – 3.14.
2. ✅ Drop external dependencies that no longer exist (Heroku, Okteto, Telethon-Mod).
3. ✅ Local-only storage, friendlier first-run experience.
4. ✅ Better DX for module authors — type hints across core, ruff/black/isort via pre-commit, `inline.py` split into `inline/`.
5. 🟡 Real self-update for wheel installs (currently a stub pointing to `uv tool upgrade`).
6. ✅ Documentation — bilingual docs under [`docs/`](docs/), MkDocs Material site, deployed to [d4n13l3k00.github.io/GeekTG](https://d4n13l3k00.github.io/GeekTG/) on push to `master`.

Issues and PRs are welcome. If a third-party module broke after an update — open an issue with a traceback.

---

## 📄 License

GNU AGPL v3 — see [`LICENSE`](LICENSE).
Originally Copyright © 2018-2022 The Friendly-Telegram Authors, forked by GeekTG, refreshed by the current maintainer.
