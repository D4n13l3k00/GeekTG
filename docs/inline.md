# GeekTG.inline — справочник

Подробная документация по `self.inline` — менеджеру inline-бота: формы, галереи,
inline-команды, обработка нажатий. Краткая выжимка живёт в
[modules.md → Inline manager](modules.md#inline-manager-forms-galleries-callbacks);
эта страница — расширенный референс с примерами под актуальную версию проекта
(GeekTG 4.0+, aiogram 3.x).

> **Что изменилось в 4.0.** Проект перешёл на `aiogram>=3.13`. В коллбэки форм
> теперь приходит наша обёртка `InlineCall` (а не сырой `CallbackQuery` —
> aiogram 3 сделал свои события `frozen` pydantic-моделями, мы не можем
> навешивать на них хелперы). Все примеры ниже — под v3.

## Скопы

Модули, использующие любые возможности этого режима, должны содержать скопу
(комментарий в начале файла):

```python
# scope: inline
```

Если ты **не обрабатываешь** возможность использования модуля на классическом
FTG (`if hasattr(self, 'inline')`), укажи также:

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
    message: Union[Message, int],
    reply_markup: List[List[dict]] = None,
    force_me: bool = True,
    always_allow: List[int] = None,
    ttl: Union[int, bool] = False,
    photo: str = None,
) -> Union[str, bool]:
```

Возвращает строку с `form_uid` либо `False` при ошибке (исключение **не
поднимается** — лог пишется, callback тихо не сработает).

### Пример

```python
await self.inline.form(
    text="📊 Poll GeekTG vs. FTG\n🕶 GeekTG: No votes\n😔 FTG: No votes",
    message=message,
    reply_markup=[
        [{"text": "GeekTG", "callback": self.vote, "args": [False]}],
        [{"text": "FTG",    "callback": self.vote, "args": [True]}],
    ],
    force_me=False,           # пускать всех (по умолчанию — только владельца)
    always_allow=[659800858], # whitelisted user IDs
    ttl=30,                   # секунды до автоудаления формы (default 24 ч)
)
```

### Типы кнопок

**С коллбэком-функцией:**

```python
{
    "text": "Button with function",
    "callback": self.callback_handler,
    "args": (arg1,),
    "kwargs": {"name": "value"},
}
```

**С кастомным payload (bring-your-own-handler через `*_callback_handler`):**

```python
{
    "text": "Button with custom payload",
    "data": "ub/123/456",   # произвольная строка
}
```

**URL:**

```python
{
    "text": "Open in browser",
    "url": "https://example.com",
}
```

**С запросом ввода у пользователя:**

```python
{
    "text": "✍️ Enter value",
    "input": "✍️ Enter new configuration value for this option",
    "handler": self.input_handler,
    "args": (arg1,),
    "kwargs": {"name": "value"},
}
```

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

`caption` — строка, лямбда или async-функция, возвращающая текст подписи.
`next_handler` — async-функция, возвращающая URL следующего фото.

## Обработка нажатий: вариант 1 (без памяти, через `data`)

Если кнопка должна "жить вечно" (например, persistent unmute/unban), используй
`data` вместо `callback`. Тогда коллбэк не привязан к конкретной форме —
обрабатывай вручную через `*_callback_handler`:

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

`call` здесь — `InlineCall`-обёртка над `CallbackQuery`. Для variant 1 на ней
доступны только нативные aiogram-методы (`call.answer`, `call.from_user`,
`call.data`, `call.bot`, `call.message`) — `call.edit/delete/unload/form` не
работают, потому что коллбэк не привязан к зарегистрированной форме.

## Обработка нажатий: вариант 2 (через `callback`)

Когда в кнопку передаётся `callback`, обработчик получает `InlineCall` со
**стейтом формы** в довесок к нативным полям:

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

`call.edit(reply_markup=[[...]])` принимает наш list-of-dict формат — сам
сгенерит `InlineKeyboardMarkup`, обновит `_forms[form_uid]["buttons"]`, и
вызовет `bot.edit_message_text(inline_message_id=...)`. Сетевые ошибки
(`MessageNotModified`, `RetryAfter`, `MessageIdInvalid`) хелпер обрабатывает
сам.

## InlineCall: что это и что доступно

Wrapper, который приходит в коллбэки форм. Хранит ссылку на underlying
`CallbackQuery` / `ChosenInlineResult` и делегирует через `__getattr__` всё,
чего на нём нет напрямую.

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

`self.inline.bot` — полноценный `aiogram.Bot`. Через него доступны все методы
Bot API. `self.inline._dp` — `Dispatcher` (префикс `_` = внутреннее, но
технически можно регистрировать свои хендлеры).

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

`query` — `GeekInlineQuery`, тонкая обёртка над `aiogram.types.InlineQuery` с
дополнительным полем `query.args` (то, что после имени команды). Все остальные
поля (`query.from_user`, `query.id`, `query.answer`) — нативные.

> **Изменения по сравнению с aiogram 2.x в этих примерах:**
>
> - `InputTextMessageContent("text", "HTML", disable_web_page_preview=True)` →
>   `InputTextMessageContent(message_text=..., link_preview_options=LinkPreviewOptions(is_disabled=True))`.
>   `parse_mode` глобально установлен в `HTML` через
>   `DefaultBotProperties` — указывать его в каждом результате не нужно.
> - `thumb_url`/`thumb_width`/`thumb_height` →
>   `thumbnail_url`/`thumbnail_width`/`thumbnail_height`.
> - `InlineKeyboardMarkup()` + `.add()`/`.row()` →
>   `InlineKeyboardMarkup(inline_keyboard=[[…]])` (markup стал immutable).

`rand(20)` импортируется из `friendly_telegram.inline` и нужен для уникального
`id` каждого ответа.

## aiogram_watcher

Модули могут получать **все** сообщения, прилетевшие inline-боту в private,
через метод `aiogram_watcher`:

```python
async def aiogram_watcher(self, message):
    if message.text == "ping":
        await message.answer("pong")
```

`message` — нативный `aiogram.types.Message`. Метод `message.answer(text)` —
тоже нативный (в v2 мы инжектили свой; в v3 это убрано, потому что
`DefaultBotProperties(parse_mode=HTML)` уже даёт нужный default). Если хочешь
отключить link preview — передавай `link_preview_options=LinkPreviewOptions(is_disabled=True)`.

## Breaking changes от v3 для сторонних модулей

Если поддерживаешь модуль с aiogram 2.x и переезжаешь на 4.0+:

1. `from aiogram.utils.exceptions import …` → `from aiogram.exceptions import …`.
   `Unauthorized` → `TelegramUnauthorizedError`, `RetryAfter` →
   `TelegramRetryAfter` (и `e.timeout` → `e.retry_after`), всё остальное —
   через `TelegramBadRequest` с substring-проверкой.
2. Если в коллбэке делал `query.something = ...` (мутировал событие) — это
   падает, потому что v3-объекты frozen. Используй wrapper или храни состояние
   в своём dict.
3. Type hints: `aiogram.types.CallbackQuery` → `friendly_telegram.inline.types.InlineCall`.
4. `InputTextMessageContent` / `InlineQueryResult*` / `bot.send_message`:
   `disable_web_page_preview=True` → `link_preview_options=LinkPreviewOptions(is_disabled=True)`.
5. `thumb_*` → `thumbnail_*` во всех `InlineQueryResult*`.
6. `InlineKeyboardMarkup()` + `.row()`/`.add()` → конструктор с
   `inline_keyboard=[[...]]`.
