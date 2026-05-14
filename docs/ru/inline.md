# GeekTG.inline — справочник

Подробная документация по `self.inline` — менеджеру inline-бота: формы,
галереи, inline-команды, обработка нажатий. Краткая выжимка — в
[modules.md → Inline manager](modules.md#inline-manager); эта страница —
расширенный референс под актуальную версию проекта (GeekTG 4.0+,
aiogram 3.x).

`self.inline` — всегда живой `InlineManager` (выставляется до
`client_ready`, даже при `--no-inline`); если код может выполниться
до завершения BotFather-handshake'а, проверяй
`if self.inline.init_complete:` перед использованием.

> **Что изменилось в 4.0.** Проект перешёл на `aiogram>=3.13`. В
> коллбэки форм теперь приходит наша обёртка `InlineCall` (а не сырой
> `CallbackQuery` — aiogram 3 сделал свои события `frozen`
> pydantic-моделями, мы не можем навешивать на них хелперы). Все
> примеры ниже — под v3.

## Скопы

Модули, использующие любые возможности этого режима, должны содержать
скопу (комментарий в начале файла):

```python
# scope: inline
```

Если ты **не обрабатываешь** возможность использования модуля на
классическом FTG (`if hasattr(self, 'inline')`), укажи также:

```python
# scope: geektg_only
```

Если требуется минимальная версия GeekTG:

```python
# scope: geektg_min 4.0.0
```

## Создание формы

Для inline-кнопок в сообщении используй `self.inline.form()`.

### Сигнатура

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

`Message` здесь — `telethon.tl.custom.Message`. Возвращает строку с
`form_uid` либо `False` при ошибке (исключение **не** поднимается — в
лог летит `inline.form() failed for uid=…`, форма не регистрируется).

### Семантика аргументов

- **`text`** — тело сообщения, HTML разрешён (parse-mode выставлен
  глобально в HTML через `DefaultBotProperties`, так что
  `parse_mode` per-message не нужен).
- **`message`** — Telethon `Message` (форма заменит его — оригинал
  будет удалён), `InlineCall` (повторно использует чат-источник) или
  `int` chat-ID (отправит свежее).
- **`reply_markup`** — вложенный `[[dict, dict], [dict]]`-грид кнопок.
  Один dict / плоский list автоматически оборачиваются в строки.
- **`force_me=True`** — только owner-class юзеры (ID самого бота, ID из
  `db["friendly_telegram.security"]["owner"]` или кто-то из
  `always_allow`) могут жать кнопки. Проверяется на клик, не при
  создании. Поставь `False`, чтобы форма была публичной.
- **`always_allow`** — extra-юзер-ID, обходящие `force_me`.
- **`ttl`** — секунд до автоистечения формы. Кламп `[10, 86400]`,
  дефолт 24 ч. После истечения форма удаляется из реестра менеджера;
  URL-кнопки продолжают работать, `callback`/`input` молча падают.
- **`photo`** — URL для рендера формы как `InlineQueryResultPhoto`
  вместо текстовой статьи.

### Пример

```python
await self.inline.form(
    text="📊 <b>Опрос: GeekTG vs FTG</b>\n🕶 GeekTG: 0 голосов\n😔 FTG: 0 голосов",
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

### Типы кнопок

**Function callback** (form-stateful — `call.edit/delete/unload/form`
работают):

```python
{
    "text": "Жми меня",
    "callback": self.handler,    # async (self, call, *args, **kwargs)
    "args": (arg1,),
    "kwargs": {"name": "value"},
}
```

**Custom payload** (без form-state — обрабатывается твоим
`*_callback_handler`):

```python
{"text": "Persistent action", "data": "ub/123/456"}
```

**URL** (без callback):

```python
{"text": "Открыть в браузере", "url": "https://example.com"}
```

**Inline-input prompt** (юзера просят набрать что-то через input-поле
inline-бота):

```python
{
    "text": "✍️ Введи значение",
    "input": "✍️ Введи новое значение конфига",
    "handler": self.input_handler,   # async (self, call, query: str, *args, **kw)
    "args": (arg1,),
    "kwargs": {"name": "value"},
}
```

### Стилизация (Bot API 9.4)

Кнопка может нести одно опциональное поле стиля:

- `style` — `"primary"` (синяя), `"success"` (зелёная), `"danger"`
  (красная). Любое другое значение логируется и игнорируется.

```python
{"text": "Удалить", "callback": self.do_delete, "style": "danger"}
{"text": "Подтвердить", "callback": self.confirm, "style": "success"}
```

> Bot API также определяет поле `icon_custom_emoji_id`, но Telegram
> разрешает его только для premium-ботов (с username, купленным через
> Fragment). Наш @BotFather-бот таким не является, поэтому менеджер
> намеренно отбрасывает это поле. Используй обычный emoji в подписи
> кнопки, а анимированную премиум-разметку `<tg-emoji>` ставь в
> **тексте сообщения** — там она работает (Telethon шлёт от твоего
> юзера, а у юзера-premium на это есть права).

Оба значения уходят в aiogram как есть и валидируются на сервере.

## Галереи

Inline-галерея — пролистываемые фото с одной кнопкой "Next ➡️":

```python
async def photo() -> str:
    return (await utils.run_sync(requests.get, "https://api.catboys.com/img")).json()["url"]

await self.inline.gallery(
    caption=lambda: random.choice(["Да", "Нет"]),
    message=message,
    next_handler=photo,
)
```

Сигнатура:

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

- `caption` — строка, лямбда или async-функция, возвращающая текст
  подписи. Зовётся на каждый "Next", так что динамические caption'ы
  работают.
- `next_handler` — async-функция, возвращающая URL следующего фото или
  `False` для конца галереи.

## Обработка нажатий: вариант 1 (без памяти, через `data`)

Если кнопка должна "жить вечно" (например, persistent unmute/unban),
используй `data` вместо `callback`. Тогда коллбэк не привязан к
конкретной форме — обрабатывай вручную через `*_callback_handler`:

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

`call` здесь — `InlineCall`-обёртка над `CallbackQuery`. Для variant 1
на ней доступны только нативные aiogram-методы (`call.answer`,
`call.from_user`, `call.data`, `call.bot`, `call.message`) —
`call.edit/delete/unload/form` не работают, потому что коллбэк не
привязан к зарегистрированной форме.

## Обработка нажатий: вариант 2 (через `callback`)

Когда в кнопку передаётся `callback`, обработчик получает `InlineCall`
со **стейтом формы** в довесок к нативным полям:

```python
async def _process_click(self, call, arg1: str) -> None:
    await call.unload()                 # забыть форму, оставить сообщение
    await call.delete()                 # удалить исходное сообщение и забыть форму

    await call.edit(
        text="Some new text",
        reply_markup=[                  # опционально: сменить кнопки;
            [{"text": "OK", "url": "https://ya.ru"}]
        ],                              # пропусти, чтобы убрать кнопки
        disable_web_page_preview=True,  # опционально
        always_allow=[659800858],       # сменить whitelist
        force_me=False,                 # сменить privacy mode
    )

    call.form  # dict с form_uid/buttons/chat/message_id
```

`call.edit(reply_markup=[[...]])` принимает наш list-of-dict формат —
сам сгенерит `InlineKeyboardMarkup`, обновит
`_forms[form_uid]["buttons"]`, и вызовет
`bot.edit_message_text(inline_message_id=...)`. Сетевые ошибки
(`MessageNotModified`, `RetryAfter`, `MessageIdInvalid`) хелпер
обрабатывает сам.

## InlineCall

Wrapper, который приходит в коллбэки форм. Хранит ссылку на underlying
`CallbackQuery` / `ChosenInlineResult` и делегирует через `__getattr__`
всё, чего на нём нет напрямую.

| Атрибут | Источник |
| --- | --- |
| `call.delete()`, `call.unload()`, `call.edit(...)`, `call.form` | wrapper (form-stateful хелперы) |
| `call.answer(text, show_alert=...)` | нативный `CallbackQuery.answer` |
| `call.from_user`, `call.data`, `call.id`, `call.message`, `call.inline_message_id`, `call.chat_instance` | underlying event |
| `call.bot` | `aiogram.Bot` инстанс |

Type-hint в коде:

```python
from friendly_telegram.inline.types import InlineCall

async def _click(self, call: InlineCall) -> None:
    ...
```

## Использование нативного aiogram

Wrapper не запирает. Если нужно — иди мимо:

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

`self.inline.bot` — полноценный `aiogram.Bot`. Через него доступны все
методы Bot API. `self.inline._dp` — `Dispatcher` (префикс `_` =
внутреннее, но технически можно регистрировать свои хендлеры).

## Inline-команды (@bot ...)

Методы, имя которых заканчивается на `_inline_handler`, отвечают на
inline-режим бота:

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

`query` — `GeekInlineQuery`, тонкая обёртка над
`aiogram.types.InlineQuery` с дополнительным полем `query.args`
(то, что после имени команды). Все остальные поля
(`query.from_user`, `query.id`, `query.answer`) — нативные.

> **Изменения по сравнению с aiogram 2.x в этих примерах:**
>
> - `InputTextMessageContent("text", "HTML", disable_web_page_preview=True)` →
>   `InputTextMessageContent(message_text=..., link_preview_options=LinkPreviewOptions(is_disabled=True))`.
>   `parse_mode` глобально установлен в `HTML` через
>   `DefaultBotProperties` — указывать его в каждом результате не
>   нужно.
> - `thumb_url`/`thumb_width`/`thumb_height` →
>   `thumbnail_url`/`thumbnail_width`/`thumbnail_height`.
> - `InlineKeyboardMarkup()` + `.add()`/`.row()` →
>   `InlineKeyboardMarkup(inline_keyboard=[[…]])` (markup стал
>   immutable).

`rand(20)` импортируется из `friendly_telegram.inline` и нужен для
уникального `id` каждого ответа.

## Директива `@allow:` (права inline-обработчиков)

Inline-обработчики не идут через ту же security-маску, что и команды.
Вместо этого их docstring несёт `@allow:`-строки, которые inline-менеджер
парсит на каждом запросе:

```python
async def admin_inline_handler(self, query):
    """
    Admin-only inline card.

    @allow: sudo
    """
```

Признаваемые токены:

- `all` — вообще все (inline-менеджер пропускает проверку).
- `owner` — ID из `db["friendly_telegram.security"]["owner"]` (сам ID
  юзербота всегда трактуется как owner).
- `sudo` — ID из `db["friendly_telegram.security"]["sudo"]`.
- `support` — ID из `db["friendly_telegram.security"]["support"]`.
- Голый числовой ID (`@allow: 123456789, 987654321`).

Можно использовать `@restrict:`-строки чтобы *запретить* подходящих
юзеров — deny override'ит любой предыдущий allow.

Если `@allow:` опущен полностью, обработчик дефолтится на
**owner-only**.

## `aiogram_watcher`

Модули могут получать **все** сообщения, прилетевшие inline-боту в
private:

```python
async def aiogram_watcher(self, message):
    if message.text == "ping":
        await message.answer("pong")
```

`message` — нативный `aiogram.types.Message`. `message.answer(text)` —
тоже нативный (в v2 мы инжектили свой; в v3 это убрано, потому что
`DefaultBotProperties(parse_mode=HTML)` уже даёт нужный default). Если
хочешь отключить link preview — передавай
`link_preview_options=LinkPreviewOptions(is_disabled=True)`.

## Автоматизация BotFather

При первом старте юзербота inline-менеджер создаёт и настраивает себе
Telegram-бота через BotFather:

1. Шлёт `/token`. Если юзер ранее заблокировал BotFather — сначала
   делает `UnblockRequest`.
2. Ищет в ответе существующий `@geektg_<6-chars>_bot`. Если нашёл —
   сохраняет токен в `db["geektg.inline"]["bot_token"]`.
3. Иначе создаёт новый через `/newbot`, генерирует случайный
   `GeekTG_XXXXXX_Bot`-username и заливает аватар юзербота.
4. Зовёт `/setinline` (placeholder "GeekQuery") и
   `/setinlinefeedback` (Enabled).

Caveat'ы:

- BotFather агрессивно rate-limit'ит. Flow вставляет ~2 с sleep'а между
  шагами; падения retry'атся один раз.
- Если заливка аватара упадёт — бот всё равно создастся (просто будет
  с дефолтным аватаром).
- Если polling бота позже вернёт "unauthorized" (например, ты ревокнул
  токен в BotFather), `_dp_revoke_token()` сделает свежий `/token` и
  перепривяжется.

## Breaking changes (v3 → 4.0+)

Если поддерживаешь модуль с aiogram 2.x и переезжаешь на 4.0+:

1. `from aiogram.utils.exceptions import …` →
   `from aiogram.exceptions import …`. `Unauthorized` →
   `TelegramUnauthorizedError`, `RetryAfter` → `TelegramRetryAfter`
   (и `e.timeout` → `e.retry_after`); остальное коллапсируется в
   `TelegramBadRequest` с substring-проверкой по сообщению.
2. Не мутируй event-объекты (`query.something = ...`) — v3-объекты
   frozen. Заворачивай state в свой dict.
3. Type hints: `aiogram.types.CallbackQuery` →
   `friendly_telegram.inline.types.InlineCall`.
4. `InputTextMessageContent` / `InlineQueryResult*` /
   `bot.send_message`: `disable_web_page_preview=True` →
   `link_preview_options=LinkPreviewOptions(is_disabled=True)`.
5. `thumb_*` → `thumbnail_*` во всех `InlineQueryResult*`.
6. `InlineKeyboardMarkup()` + `.row()`/`.add()` → конструктор с
   `inline_keyboard=[[...]]`.
