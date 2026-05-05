# GeekTG developer docs

Documentation for people writing modules or hacking on the userbot itself.

## Module developers

- **[modules.md](modules.md)** — main guide: lifecycle, commands, watchers,
  strings, config, distribution, best practices. *Start here.*
- [inline.md](inline.md) — inline manager: forms, galleries,
  `*_inline_handler`, `*_callback_handler`, `InlineCall` wrapper, native
  aiogram-3 escape hatches.
- [security.md](security.md) — the 13-bit permission bitmask, decorators,
  bounding mask, runtime overrides, decision flow.
- [database.md](database.md) — the JSON KV store and asset blob storage.
- [utils.md](utils.md) — one-page cheatsheet of `friendly_telegram.utils`.

## User docs

User-facing documentation (commands, screenshots, video tutorials) used to
live at `docs.geektg.tk`. That host is offline. New user docs will land
here as plain Markdown — PRs welcome.

## Codebase tour

The high-impact files when you want to change the bot itself:

| File | What |
| ---- | ---- |
| [`friendly_telegram/main.py`](../friendly_telegram/main.py) | Boot sequence, signal handling, shutdown. |
| [`friendly_telegram/loader.py`](../friendly_telegram/loader.py) | Module base class, registration, lifecycle. |
| [`friendly_telegram/dispatcher.py`](../friendly_telegram/dispatcher.py) | Command parsing, prefix handling, security gates. |
| [`friendly_telegram/security.py`](../friendly_telegram/security.py) | Permission predicates and the `@loader.owner` family. |
| [`friendly_telegram/inline/`](../friendly_telegram/inline/) | Inline-bot manager package: lifecycle/dispatch (`manager.py`), `InlineCall` wrapper and helpers (`types.py`). |
| [`friendly_telegram/database/`](../friendly_telegram/database/) | Local JSON-backed key-value store + asset blobs. |
| [`friendly_telegram/web/`](../friendly_telegram/web/) | First-run web wizard and post-login dashboard. |
| [`friendly_telegram/modules/`](../friendly_telegram/modules/) | Bundled core modules. Best living examples. |
| [`friendly_telegram/utils.py`](../friendly_telegram/utils.py) | Free-floating helpers used everywhere. |

## Build and dev workflow

```sh
uv sync                        # set up .venv from pyproject.toml
uv run gtg                     # boot from source
uv build                       # produce wheel + sdist in dist/
uv pip install dist/*.whl      # install the built wheel
```

Test suite lives in [`tests/`](../tests/) (pytest + pytest-asyncio). Run it
with `uv run pytest`. Linters and formatters wire up via pre-commit:

```sh
uv run pre-commit install        # one-time setup
uv run pre-commit run --all-files
```

isort (`--profile black`), black, and ruff run on every commit.
