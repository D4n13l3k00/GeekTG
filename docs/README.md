# GeekTG developer docs

Documentation for people writing modules or hacking on the userbot itself.

## Module developers

- **[modules.md](modules.md)** — full guide: lifecycle, commands, watchers,
  inline forms, strings, config, database, asset storage, security
  decorators, the `utils` cheatsheet, distribution, and best practices.
  *Start here.*
- [inline.md](inline.md) — legacy notes on the inline manager API. The
  current canonical reference is the *Inline manager* section of
  [modules.md](modules.md#inline-manager-forms-galleries-callbacks);
  this file is kept for now because some external module authors still link
  to it.
- [mods.md](mods.md) — the original Russian-language module guide. Kept
  as historical reference; the English [modules.md](modules.md) supersedes
  it.

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
| [`friendly_telegram/inline.py`](../friendly_telegram/inline.py) | Inline-bot manager, forms, galleries, callbacks. |
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

There's no test suite yet — patches that add one are very welcome.
