# `utils` cheatsheet

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
| `get_platform_name()` | Display name for `.info` ("📻 VDS", "📱 Termux", "🐳 Docker", …). Honors `$GTG_PLATFORM`. |
| `run_sync(func, *a, **k)` | Run a blocking call in the default executor. |
| `relocate_entities(entities, offset, text=None)` | Adjust message-entity offsets after slicing text. |
| `merge(a, b)` | Deep-merge two dicts. |
| `rand(n)` | Random alphanumeric string of length *n*. |
| `install_requirements(pkgs, user_install=False)` | Pip-install at runtime, picks `uv pip` when available. |
| `print_web_urls(port)` | Pretty-print all reachable URLs (used at startup). |

For full signatures, read [`friendly_telegram/utils.py`](../friendly_telegram/utils.py).
