# GeekTG.inline — reference

Detailed reference for `self.inline`, the inline-bot manager: forms,
galleries, inline commands, callback handlers. The short summary lives
in [modules.md → Inline manager](modules.md#inline-manager); this page
is the long-form reference for the current project (GeekTG 4.0+,
aiogram 3.x).

`self.inline` is always a populated `InlineManager` (set before
`client_ready` runs even when `--no-inline`); guard inline use with
`if self.inline.init_complete:` if your code paths might run before
the BotFather handshake completes.

> **What changed in 4.0.** The project switched to `aiogram>=3.13`. Form
> callbacks now receive our `InlineCall` wrapper (not a raw
> `CallbackQuery` — aiogram 3 made its events `frozen` pydantic models,
> so we can't attach helpers to them directly). All examples below are
> v3.

## Scopes

Modules using any inline feature must declare a scope at the top of the
file:

```python
# scope: inline
```

If you do **not** branch on `hasattr(self, 'inline')` for backwards
compatibility with classic FTG, also add:

```python
# scope: geektg_only
```

If you require a minimum GeekTG version:

```python
# scope: geektg_min 4.0.0
```

## Form

Inline form = a message with an inline keyboard managed by the GeekTG
bot. Use `self.inline.form()`.

### Signature

```python
async def form(
    self,
    text: str,
    message: Union[Message, InlineCall, int],
    reply_markup: Optional[List[List[dict]]] = None,
    force_me: bool = True,
    always_allow: Optional[List[int]] = None,
    ttl: Union[int, bool] = False,
    photo: Optional[str] = None,
) -> Union[str, bool]:
```

`Message` here is `telethon.tl.custom.Message`. Returns the `form_uid`
string on success, or `False` on failure (exceptions are **not** raised
— they're logged via `inline.form() failed for uid=…`, and the form
isn't registered).

### Argument semantics

- **`text`** — message body, HTML allowed (parse mode is set globally to
  HTML via `DefaultBotProperties`, so no per-message `parse_mode`).
- **`message`** — Telethon `Message` (the form takes its place — the
  original is deleted), an `InlineCall` (re-uses its source chat), or
  an `int` chat ID (sent fresh).
- **`reply_markup`** — nested `[[dict, dict], [dict]]` button grid.
  Single dict / flat list are auto-wrapped into rows.
- **`force_me=True`** — only owner-class users (the bot's own ID, IDs
  in `db["friendly_telegram.security"]["owner"]`, or anyone in
  `always_allow`) can press buttons. Checked at click time, not
  creation time. Set `False` to make the form public.
- **`always_allow`** — extra user IDs that bypass `force_me`.
- **`ttl`** — seconds before the form auto-expires. Clamped to
  `[10, 86400]`; defaults to 24 h. Once expired the form is deleted from
  the manager's registry; URL buttons keep working but
  `callback`/`input` buttons silently fail.
- **`photo`** — URL to render the form as an `InlineQueryResultPhoto`
  instead of a text article.

### Example

```python
await self.inline.form(
    text="📊 <b>Poll: GeekTG vs FTG</b>\n🕶 GeekTG: 0 votes\n😔 FTG: 0 votes",
    message=message,
    reply_markup=[
        [{"text": "GeekTG", "callback": self.vote, "args": [False]}],
        [{"text": "FTG",    "callback": self.vote, "args": [True]}],
    ],
    force_me=False,
    always_allow=[659800858],
    ttl=30,
)
```

### Button types

**Function callback** (form-stateful — `call.edit/delete/unload/form`
work):

```python
{
    "text": "Click me",
    "callback": self.handler,    # async (self, call, *args, **kwargs)
    "args": (arg1,),
    "kwargs": {"name": "value"},
}
```

**Custom payload** (no form state — handled by your
`*_callback_handler`):

```python
{"text": "Persistent action", "data": "ub/123/456"}
```

**URL** (no callback):

```python
{"text": "Open in browser", "url": "https://example.com"}
```

**Inline-input prompt** (the user is asked to type something via the
inline-bot input field):

```python
{
    "text": "✍️ Enter value",
    "input": "✍️ Enter new configuration value for this option",
    "handler": self.input_handler,   # async (self, call, query: str, *args, **kw)
    "args": (arg1,),
    "kwargs": {"name": "value"},
}
```

## Gallery

A swipeable photo strip with a single "Next ➡️" button:

```python
async def photo() -> str:
    return (await utils.run_sync(requests.get, "https://api.catboys.com/img")).json()["url"]

await self.inline.gallery(
    caption=lambda: random.choice(["Yes", "No"]),
    message=message,
    next_handler=photo,
)
```

Signature:

```python
async def gallery(
    self,
    caption: Union[str, FunctionType],
    message: Union[Message, int],
    next_handler: FunctionType,
    force_me: bool = False,
    always_allow: bool = False,
    ttl: int = False,
) -> Union[bool, str]:
```

- `caption` — string, lambda, or async function returning the caption.
  Called on every "Next" press, so dynamic captions work.
- `next_handler` — async function returning the next photo URL, or
  `False` to end the gallery.

## Click handling: variant 1 (no state, custom `data`)

If the button must "live forever" (persistent unmute/unban), use `data`
instead of `callback`. The handler is *not* tied to a specific form —
register it as `*_callback_handler`:

```python
async def actions_callback_handler(self, call) -> None:
    """
    Handles unmute/unban button clicks.
    @allow: all
    """
    if not re.match(r"[fbmudw]{1,3}/[-0-9]+/[-#0-9]+", call.data):
        return
    action, chat_id, user_id = call.data.split("/")
    # ... do work ...
    await call.answer("done")
```

`call` is an `InlineCall` wrapper. In variant 1 only native aiogram
methods are usable (`call.answer`, `call.from_user`, `call.data`,
`call.bot`, `call.message`) — `call.edit/delete/unload/form` don't work
because the callback isn't bound to a registered form.

## Click handling: variant 2 (`callback`)

When the button uses `callback`, the handler receives an `InlineCall`
with **form state** in addition to native fields:

```python
async def _process_click(self, call, arg1: str) -> None:
    await call.unload()                 # forget the form, leave the message
    await call.delete()                 # delete the message and forget the form

    await call.edit(
        text="Some new text",
        reply_markup=[                  # optional: change buttons;
            [{"text": "OK", "url": "https://ya.ru"}]
        ],                              # omit to remove buttons
        disable_web_page_preview=True,  # optional
        always_allow=[659800858],       # change whitelist
        force_me=False,                 # change privacy mode
    )

    call.form  # dict with form_uid/buttons/chat/message_id
```

`call.edit(reply_markup=[[...]])` accepts our list-of-dict format —
generates the `InlineKeyboardMarkup` itself, refreshes
`_forms[form_uid]["buttons"]`, and calls
`bot.edit_message_text(inline_message_id=...)`. Network errors
(`MessageNotModified`, `RetryAfter`, `MessageIdInvalid`) are handled
internally.

## InlineCall

The wrapper passed to form callbacks. It holds a reference to the
underlying `CallbackQuery` / `ChosenInlineResult` and delegates
attribute access through `__getattr__`.

| Attribute | Source |
| --- | --- |
| `call.delete()`, `call.unload()`, `call.edit(...)`, `call.form` | wrapper (form-stateful helpers) |
| `call.answer(text, show_alert=...)` | native `CallbackQuery.answer` |
| `call.from_user`, `call.data`, `call.id`, `call.message`, `call.inline_message_id`, `call.chat_instance` | underlying event |
| `call.bot` | `aiogram.Bot` instance |

Type-hint:

```python
from friendly_telegram.inline.types import InlineCall

async def _click(self, call: InlineCall) -> None:
    ...
```

## Native aiogram escape hatch

The wrapper doesn't lock you in. Reach for the underlying bot when you
need something we don't expose:

```python
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions

async def _click(self, call: InlineCall) -> None:
    await call.answer("processing")
    await self.inline.bot.edit_message_text(
        text="manual edit",
        inline_message_id=call.inline_message_id,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="OK", callback_data="x")]
        ]),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
```

`self.inline.bot` is a regular `aiogram.Bot` — all Bot API methods are
available. `self.inline._dp` is the `Dispatcher` (underscore = internal,
but you can register your own handlers there if you must).

## Inline commands (`@bot ...`)

Methods whose name ends in `_inline_handler` answer inline-mode queries:

```python
from friendly_telegram.inline import GeekInlineQuery, rand
from aiogram.types import (
    InlineQueryResultArticle,
    InputTextMessageContent,
    LinkPreviewOptions,
)

async def hello_inline_handler(self, query: GeekInlineQuery) -> None:
    """
    Show 'hello' card.
    @allow: all
    """
    await query.answer(
        [
            InlineQueryResultArticle(
                id=rand(20),
                title="Say hello",
                description=f"args: {query.args}",
                input_message_content=InputTextMessageContent(
                    message_text=f"<b>👋 hi {query.args}</b>",
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                ),
                thumbnail_url="https://img.icons8.com/fluency/50/000000/info-squared.png",
                thumbnail_width=128,
                thumbnail_height=128,
            )
        ],
        cache_time=0,
    )
```

`query` is `GeekInlineQuery`, a thin wrapper over
`aiogram.types.InlineQuery` with an extra `query.args` (everything after
the command name). All other fields (`query.from_user`, `query.id`,
`query.answer`) are native.

> **Differences vs aiogram 2.x:**
>
> - `InputTextMessageContent("text", "HTML", disable_web_page_preview=True)` →
>   `InputTextMessageContent(message_text=..., link_preview_options=LinkPreviewOptions(is_disabled=True))`.
>   `parse_mode` is set globally to HTML via `DefaultBotProperties` —
>   no need to pass it on every result.
> - `thumb_url` / `thumb_width` / `thumb_height` →
>   `thumbnail_url` / `thumbnail_width` / `thumbnail_height`.
> - `InlineKeyboardMarkup()` + `.add()` / `.row()` →
>   `InlineKeyboardMarkup(inline_keyboard=[[…]])` (markup is now
>   immutable).

`rand(20)` from `friendly_telegram.inline` gives you a unique result
ID (20 chars).

## `@allow:` directive (inline-handler permissions)

Inline handlers don't go through the same security mask as commands.
Instead, the handler's docstring carries `@allow:` lines that the inline
manager parses on every query:

```python
async def admin_inline_handler(self, query):
    """
    Admin-only inline card.

    @allow: sudo
    """
```

Recognised tokens:

- `all` — anyone (the inline manager skips the check entirely).
- `owner` — IDs in `db["friendly_telegram.security"]["owner"]` (the
  userbot's own ID is always treated as owner).
- `sudo` — IDs in `db["friendly_telegram.security"]["sudo"]`.
- `support` — IDs in `db["friendly_telegram.security"]["support"]`.
- A bare numeric ID (`@allow: 123456789, 987654321`).

You may also use `@restrict:` lines to *deny* matching users — the deny
overrides any prior allow.

If you omit `@allow:` entirely, the handler defaults to **owner-only**.

## `aiogram_watcher`

Modules can receive **all** messages sent privately to the inline bot:

```python
async def aiogram_watcher(self, message):
    if message.text == "ping":
        await message.answer("pong")
```

`message` is a native `aiogram.types.Message`. `message.answer(text)` is
also native (in v2 we injected our own; v3 doesn't need that because
`DefaultBotProperties(parse_mode=HTML)` already gives the right
default). To disable link preview, pass
`link_preview_options=LinkPreviewOptions(is_disabled=True)`.

## BotFather automation

The first time the userbot starts, the inline manager creates and
configures a Telegram bot for itself via BotFather:

1. Sends `/token`. If the user has previously blocked BotFather, an
   `UnblockRequest` is issued first.
2. Looks for an existing `@geektg_<6-chars>_bot` in the response. If
   found, it grabs the token and saves it under
   `db["geektg.inline"]["bot_token"]`.
3. Otherwise creates a new one with `/newbot`, generates a random
   `GeekTG_XXXXXX_Bot` username, and uploads the userbot's avatar.
4. Calls `/setinline` (placeholder text "GeekQuery") and
   `/setinlinefeedback` (Enabled).

Caveats:

- BotFather rate-limits aggressively. The flow inserts ~2 s sleeps
  between steps; failures are retried once.
- If the avatar upload fails, the bot is still created (it just gets the
  default avatar).
- If the bot's polling later returns "unauthorized" (e.g. you revoked
  the token from BotFather), `_dp_revoke_token()` issues a fresh `/token`
  and re-binds.

## Breaking changes (v3 → 4.0+)

For third-party modules being ported from FTG (aiogram 2.x):

1. `from aiogram.utils.exceptions import …` →
   `from aiogram.exceptions import …`. `Unauthorized` →
   `TelegramUnauthorizedError`, `RetryAfter` → `TelegramRetryAfter`
   (and `e.timeout` → `e.retry_after`); the rest collapses into
   `TelegramBadRequest` with substring checks on the message.
2. Don't mutate event objects (`query.something = ...`) — v3 events are
   frozen. Wrap state in your own dict.
3. Type hints: `aiogram.types.CallbackQuery` →
   `friendly_telegram.inline.types.InlineCall`.
4. `InputTextMessageContent` / `InlineQueryResult*` / `bot.send_message`:
   `disable_web_page_preview=True` →
   `link_preview_options=LinkPreviewOptions(is_disabled=True)`.
5. `thumb_*` → `thumbnail_*` on every `InlineQueryResult*`.
6. `InlineKeyboardMarkup()` + `.row()` / `.add()` → constructor with
   `inline_keyboard=[[...]]`.
