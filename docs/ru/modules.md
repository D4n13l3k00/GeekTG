# Пишем модули

Модули — единица расширения GeekTG. Каждый модуль — это один Python-файл,
определяющий один класс с командами юзербота, watcher'ами сообщений,
inline-обработчиками и персистентным состоянием. Loader подбирает их при
старте или по требованию через `.loadmod`.

Этот документ описывает канонический layout модуля, жизненный цикл и
мелкие foot-gun'ы, не очевидные из кода. Темы со своими страницами
(inline-формы, security, база, utils) линкуются по тексту.

> Используй `from telethon.tl.custom import Message` для сигнатур
> хендлеров. У `tl.types.Message` нет `.edit`, `.delete`, `.respond`,
> `.get_reply_message`, `.is_reply`, `.raw_text` — на которые
> опирается каждый хендлер в кодовой базе.

---

## Оглавление

1. [Модуль за пять минут](#модуль-за-пять-минут)
2. [Анатомия модуля](#анатомия-модуля)
3. [Хуки жизненного цикла](#хуки-жизненного-цикла)
4. [`self.ctx` — единый DI-бандл](#selfctx--единый-di-бандл)
5. [Команды](#команды)
6. [Watcher'ы (пассивные обработчики)](#watcherы-пассивные-обработчики)
7. [Inline manager](#inline-manager) — см. также **[inline.md](inline.md)**
8. [Строки и переводы](#строки-и-переводы)
9. [Конфиг (`ModuleConfig`)](#конфиг-moduleconfig)
10. [База данных и ассеты](#база-данных-и-ассеты) — см. **[database.md](database.md)**
11. [Utils cheatsheet](#utils-cheatsheet) — см. **[utils.md](utils.md)**
12. [Security](#security) — см. **[security.md](security.md)**
13. [Заголовки модуля и метадирективы](#заголовки-модуля-и-метадирективы)
14. [Дистрибуция и загрузка](#дистрибуция-и-загрузка)
15. [Best practices и подводные камни](#best-practices-и-подводные-камни)

---

## Модуль за пять минут

Сохрани как `~/.local/share/friendly-telegram/loaded_modules/HelloMod.py`
(или подгрузи по URL через `.loadmod`):

```python
# meta developer: @your_handle
# requires: pillow

from telethon.tl.custom import Message
from friendly_telegram import loader, utils


@loader.tds
class HelloMod(loader.Module):
    """Здоровается с отправителем."""

    strings = {
        "name": "Hello",
        "hi": "👋 <b>Привет, {name}!</b>",
    }

    @loader.unrestricted
    async def hicmd(self, message: Message):
        """Поздороваться."""
        sender = await message.get_sender()
        await utils.answer(
            message,
            self.tr("hi", message).format(name=sender.first_name),
        )
```

Сделай `.loadmod` на файл (или перезапусти бот). Затем:

```text
> .hi
👋 Привет, John!
```

Это всё, что нужно: подкласс `loader.Module` с именем, заканчивающимся
на `Mod`, декоратор `@loader.tds`, один метод с именем, заканчивающимся
на `cmd`.

---

## Анатомия модуля

```text
┌────────────────────────────────┐
│  метадирективы                 │  # meta developer:, # requires:, # scope:
├────────────────────────────────┤
│  imports                       │  telethon, friendly_telegram, твои deps
├────────────────────────────────┤
│  helpers / pure functions      │  выноси за класс, когда self не нужен
├────────────────────────────────┤
│  @loader.tds                   │
│  class FooMod(loader.Module):  │
│      strings  = {...}          │  пользовательский текст (переводимый)
│      config   = ModuleConfig() │  настройки в рантайме (опционально)
│      __init__                  │  только конфиг
│      client_ready              │  async-инициализация (опционально)
│      on_unload                 │  async-tear-down, ≤ 5 с бюджет
│      *cmd, watcher,            │
│      *_inline_handler,         │
│      *_callback_handler        │
└────────────────────────────────┘
```

Имя класса **должно заканчиваться на `Mod`** — так loader его находит.
В одном файле — ровно один класс `Mod`.

---

## Хуки жизненного цикла

Loader зовёт их по порядку. Ни один не обязателен, но большинство
нетривиальных модулей реализуют как минимум `client_ready`.

| Хук | Сигнатура | Когда |
| ---- | --------- | ---- |
| `__init__` | `(self) -> None` | При импорте файла. **Sync** — никаких I/O. Единственное нормальное применение — `self.config = loader.ModuleConfig(...)`. |
| `config_complete` | `(self) -> None` | После того, как `self.config` смерджен с persisted-значениями из БД. Sync. Используй для валидации инвариантов конфига. |
| `client_ready` | `async (self, client, db)` | После того, как все клиенты подключены и inline-менеджер инициализирован. Опционально — современный код читает `self.ctx` напрямую. Override'ить только если нужны background-таски или async one-time setup. |
| `on_unload` | `async (self) -> None` | На `.unloadmod`, перезагрузке или shutdown'е. Жёсткий 5-секундный таймаут — отменяй свои задачи здесь, не делай `await client.send_message(...)` для cleanup'а. |

Background-таски: храни сильную ссылку. GC фреймворка иначе соберёт
fire-and-forget `asyncio.ensure_future(...)`.

```python
async def client_ready(self, client, db):
    self._task = asyncio.create_task(self._loop())  # держим ссылку!

async def on_unload(self):
    self._task.cancel()
```

---

## `self.ctx` — единый DI-бандл

Фреймворк наполняет `self.ctx` (frozen-dataclass `ModuleContext`)
**до того, как запускается `client_ready`**, поэтому он доступен везде,
где может выполниться метод модуля: в командах, watcher'ах,
inline-обработчиках, callback-обработчиках, callback'ах форм,
background-задачах.

```python
@dataclass(frozen=True)
class ModuleContext:
    client:     TelegramClient        # основной клиент юзербота
    db:         Database              # KV-хранилище + ассеты
    inline:     InlineManager         # тот же объект, что self.inline
    modules:    Modules               # loader (другие модули, watcher'ы…)
    allclients: Sequence[TelegramClient]
    log:        Callable[..., Any]    # log-хелпер фреймворка
    origin:     str                   # "<file>" или источник загрузки
```

Предпочитай `self.ctx.X` копированию ссылок в `self._client = client`
внутри `client_ready` — этот boilerplate легаси. Frozen-dataclass также
означает, что плохо ведущий себя модуль не сможет подменить loader'у
взгляд на мир.

```python
@loader.tds
class FooMod(loader.Module):
    """Демо использования self.ctx."""

    @loader.owner
    async def hellocmd(self, message: Message):
        # В командах можно использовать message.client или self.ctx.client —
        # это один и тот же объект. self.ctx нужен там, где нет message.
        me = await self.ctx.client.get_me()
        self.ctx.db.set(__name__, "last_run_by", me.id)
        await utils.answer(message, f"Привет, {me.first_name}!")

    async def on_btn(self, call):
        # У callback'ов inline-форм нет Telethon Message — self.ctx это
        # как добраться до клиента и БД отсюда.
        await self.ctx.client.send_message("me", "Кнопка нажата!")
```

### Когда всё ещё имеет смысл переопределять `client_ready`

- Старт background-задач (`asyncio.create_task(...)`) — нужно где-то
  делать spawn, и `client_ready` для этого канонический. Держи task на
  `self`.
- Async one-time setup, зависящий от подключённого клиента (например,
  `self._me = await client.get_me()`, если нужно сразу).
- Легаси-модули, которые ещё делают `self._db = db; self._client =
  client` — продолжают работать, но их стоит мигрировать на `self.ctx`.

Override'ить его *только* чтобы "сохранить ссылки" больше не нужно.

---

## Команды

Любой **корутинный** метод, имя которого заканчивается на `cmd`,
становится командой. Имя без суффикса — сама команда: `mycoolcmd` →
`.mycool`.

```python
async def echocmd(self, message: Message):
    """Эхо аргументов."""
    await utils.answer(message, utils.get_args_raw(message) or "(пусто)")
```

Конвенции, на которые опирается `.help` и фреймворк:

- **Docstring** — текст помощи. Держи его в одну строку.
- Конвенция `<args>`-плейсхолдера помогает пользователям:
  `"""<text> — Эхо."""`.
- Префиксуй метод [security-декоратором](security.md#декораторы), если
  только команда не безопасна *для всех в любых чатах* (тогда
  `@loader.unrestricted`).
- Всегда отвечай через `utils.answer(message, …)` — он редактирует, если
  отправитель — мы, и реплаит иначе; возвращает list сообщений.

### Парсинг аргументов

```python
utils.get_args_raw(message)              # "foo bar baz"
utils.get_args(message)                  # ["foo", "bar", "baz"] (shell-like)
utils.get_args_split_by(message, "|")    # split по своему сепаратору
utils.get_target(message, arg_no=0)      # резолвит юзера — по реплаю,
                                         # @username, ID или арг-у
```

`utils.get_args` делает shell-style split (`shlex`) — оборачивай
multi-word аргументы в кавычки.

---

## Watcher'ы (пассивные обработчики)

Метод буквально с именем `watcher` зовётся для **каждого входящего
сообщения, которое не от юзербота**, включая сервисные (joins, edits…).
Используй редко — каждое сообщение в каждом чате через него прогоняется.

```python
async def watcher(self, message: Message):
    if isinstance(message, types.MessageService):
        return
    if "🔔" in (message.raw_text or ""):
        await message.react("🤖")
```

Кидай исключения свободно — они логируются и не валят dispatcher.

### `aiogram_watcher` (DM в inline-бот)

Отдельный хук, срабатывающий для **сообщений в личку inline-бота**
(не юзербота). Используй для FSM-flow'ов или промптов после inline-формы.

```python
async def aiogram_watcher(self, message):
    # message — нативный aiogram.types.Message
    if message.text == "ping":
        await message.answer("pong")
```

`parse_mode` бота по дефолту HTML (выставлен глобально через
`DefaultBotProperties`), так что `message.answer("<b>hi</b>")` работает
без лишних аргументов.

### Отключение watcher'ов на инстансе

Пользователь может выключить любой watcher через `.watcherbl
<ИмяМодуля>`; список лежит в `db["friendly_telegram.main"]
["disabled_watchers"]`. Dispatcher сверяется с ним на каждом дисптаче,
так что переключение мгновенное.

---

## Inline manager

Inline manager (`self.inline`, доступен после `client_ready`) даёт твоему
модулю рисовать Telegram inline-клавиатуры через автоматически
зарегистрированный `@BotFather`-бот — формы, галереи,
`*_inline_handler` и `*_callback_handler` методы.

```python
@loader.owner
async def menucmd(self, message: Message):
    await self.inline.form(
        text="Выбери:",
        message=message,
        reply_markup=[
            [{"text": "🟢 Да", "callback": self._yes}],
            [{"text": "🔴 Нет", "callback": self._no}],
        ],
        ttl=300,
        force_me=True,
    )

async def _yes(self, call):     # call: friendly_telegram.inline.types.InlineCall
    await call.answer("Ты сказал да!")
    await call.edit("✅ Подтверждено.")
```

Callback'и форм получают обёртку `InlineCall` (не сырой aiogram
`CallbackQuery` — события aiogram-3 — frozen pydantic-модели). На ней:

- `call.delete()` / `call.unload()` / `call.edit(...)` / `call.form` —
  наши form-stateful хелперы.
- Нативные aiogram-атрибуты (`call.answer`, `call.from_user`,
  `call.data`, `call.message`, `call.bot`, …) делегируются.

Используй `self.inline.bot` (обычный `aiogram.Bot`), когда надо звать
Bot API напрямую.

Полный референс — типы кнопок, gallery / `_inline_handler` /
`_callback_handler` примеры, v2-→-v3 миграция — в **[inline.md](inline.md)**.

---

## Строки и переводы

Атрибут класса `strings` на момент определения — обычный `dict`. После
того как отработает `@loader.tds` (в `send_config_one`), фреймворк
подменяет его на объект `Strings`, который:

- даёт attribute-доступ (`self.strings["hi"]`) **и** call-доступ
  (`self.strings("hi", message)`),
- мерджит переводы из langpack'ов, зарегистрированных через `.langpack`,
- автоматически наполняет `_cmd_doc_<name>` и `_cls_doc` docstring'ами
  команд/класса, чтобы они тоже были переводимы.

Так как тип меняется по ходу, type-checker'ы не следят за
`self.strings(...)`. Используй в коде модуля
**`self.tr(key, message=None)`** — это настоящий метод, оборачивающий
`self.strings(key, message)`:

```python
strings = {
    "name": "MyMod",                    # обязательно, показывается в .help
    "ok":   "✅ <b>Готово.</b>",
    "fail": "🚫 <b>Не удалось: {}</b>",
}

await utils.answer(message, self.tr("ok", message))
await utils.answer(
    message,
    self.tr("fail", message).format(reason),
)
```

Всегда передавай `message` вторым аргументом, чтобы применялись
per-chat language-настройки.

### Style guide

В проекте единый стиль для всех пользовательских строк:

- **Шаблон**: `<emoji> <b>текст</b>` — emoji *снаружи* bold-а.
- **Семантика**:
  - `✅` успех, `🚫` отказ/ошибка, `⚠️` предупреждение, `❓` промпт
  - `🔄` в процессе / restart, `📥` download, `📤` upload, `🔍` search
  - `ℹ️` info, `🤖` статус бота, `🗑` удаление

Чек-лист стиля:

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

## Конфиг (`ModuleConfig`)

Для runtime-настроек (URL'ы, пороги, фича-флаги) используй
`loader.ModuleConfig`:

```python
def __init__(self):
    self.config = loader.ModuleConfig(
        "GREETING", "Hello",       lambda m: self.tr("greeting_doc", m),
        "MAX_TRIES", 3,            "Сколько раз ретраить при ошибке",
    )

async def client_ready(self, client, db):
    msg = self.config["GREETING"]            # текущее значение
    default = self.config.getdef("GREETING") # исходный дефолт
    doc = self.config.getdoc("GREETING")     # описание для .config
```

Записи передаются позиционными тройками `(KEY, default, doc)` —
`ModuleConfig.__init__` режет их по `i % 3`. `doc` может быть строкой
или `callable(message)`, возвращающим строку (для переводимых описаний).

Пользователь правит через `.config <ИмяМодуля> <KEY> <value>`. Значения
персистятся в БД под `__module__`-namespace'ом модуля.

---

## База данных и ассеты

JSON KV-хранилище + хранение бинарных блобов. Используй
`db.get(__name__, key, default)` / `db.set(__name__, key, value)` для
private-стейта модуля, `db.store_asset()` / `db.fetch_asset()` для
медиа.

```python
@loader.owner
async def bumpcmd(self, message: Message):
    db = self.ctx.db
    db.set(__name__, "counter", db.get(__name__, "counter", 0) + 1)
```

Полный референс: **[database.md](database.md)**.

---

## Utils cheatsheet

`from friendly_telegram import utils` экспортирует `answer`, `get_args`,
`escape_html`, `get_chat_id`, `run_sync`, `merge`, `rand`,
`get_data_dir`, `install_requirements`, `get_platform_name` и ещё пару.
Полная таблица с описаниями: **[utils.md](utils.md)**.

---

## Security

Права — это **13-битная битмаска**, лежащая на функции команды как
`func.security`, AND'ящаяся с глобальным `bounding_mask` и возможно
переопределённая в рантайме через `.security <command>`. Дефолт для
команды без декораторов — `OWNER | SUDO`. Декораторы выставляют биты:

```python
@loader.owner          # только OWNER
@loader.sudo           # OWNER | SUDO
@loader.unrestricted   # все
@loader.group_admin_ban_users
@loader.pm
async def kickcmd(self, message): ...
```

Декораторы стэкаются (биты OR'ятся). `@loader.ratelimit` ортогонален —
он не гейтит доступ, только троттлит.

Полный референс (все 13 флагов, декораторы, decision flow, bounding
mask, user-группы): **[security.md](security.md)**.

---

## Заголовки модуля и метадирективы

Loader сканирует **первые комментарии** файла модуля на директивы:

```python
# meta developer: @your_handle
# meta desc: Однострочное описание модуля для browser'ов модулей.
# meta pic: https://example.com/preview.png

# requires: pillow numpy ffmpeg-python

# scope: ffmpeg
# scope: geektg_min 4.0.0
```

| Директива | Эффект |
| --------- | ------ |
| `# meta developer:` | Хэндл автора, показывается `.help` и browser-модулями. |
| `# meta desc:` / `# meta pic:` | Опциональная мета для browser'ов. |
| `# requires: <pkg> <pkg>...` | Loader auto-устанавливает через `uv pip` (или fallback на `pip`) при ImportError. |
| `# scope: ffmpeg` | Loader откажется загружать модуль, если в PATH нет `ffmpeg`. |
| `# scope: geektg_min X.Y.Z` | Не загружает на старых версиях GeekTG. |

Директивы должны быть в шапке файла (до первого `import`).

---

## Дистрибуция и загрузка

Пользователь ставит твой модуль одним из трёх способов:

1. **`.loadmod` reply / file**: реплай на `.py`-файл с `.loadmod`, или
   отправка файла с `.loadmod` в caption. Loader сохраняет под
   `loaded_modules/<ClassName>.py`.
2. **`.loadmod <url>`**: raw URL на `.py` (GitHub raw, gist, …).
3. **`.dlmod <name>`**: поиск и установка из репозитория модулей
   (см. `.cfg loader REPO_CONFIG_URL`).

Модули персистятся между рестартами, потому что `.py`-исходник лежит на
диске. Чтобы удалить: `.unloadmod <ClassName>` (удаляет и файл).

### Внутренний flow регистрации

Когда loader подбирает файл (на boot или `.loadmod`):

1. **Import.** `.py` импортируется через `importlib`, регистрируется в
   `sys.modules` под синтетическим именем
   (`friendly_telegram.modules.<name>` для встроенных,
   `loaded_modules.<ClassName>` для пользовательских).
2. **Поиск класса.** Loader ищет класс с именем на `Mod`, наследник
   `loader.Module`. Должен быть ровно один — лишние игнорируются.
3. **Замена существующего.** Если модуль с тем же именем класса уже
   загружен, у старого инстанса вызывается `on_unload()` (5 с таймаут),
   его команды/watcher'ы снимаются с глобального dispatcher'а.
4. **`config_complete`.** `mod.config` гидратируется из БД / env /
   дефолтов, зовётся `config_complete()`. `@loader.tds` инжектит сюда
   переведённые docstring'и.
5. **`ctx` set.** `mod.ctx = ModuleContext(...)` — единый DI-бандл.
6. **`client_ready`.** `client_ready` всех модулей запускаются
   параллельно (`asyncio.gather`). После их завершения параллельно же
   запускается `_client_ready2` — внутренний хук только для core-модулей.
7. **Discovery хендлеров.** `*cmd`, `*_inline_handler`,
   `*_callback_handler`, `watcher`, `aiogram_watcher` интроспектятся и
   регистрируются в dispatcher'е / inline-менеджере.

`.unloadmod` обращает шаги 7 → 3: дерегистрирует хендлеры, зовёт
`on_unload`, выкидывает из `sys.modules`, удаляет исходный файл.

---

## Best practices и подводные камни

- **Держи сильные ссылки на background-таски.**
  `asyncio.ensure_future(...)` без сохранения возврата *будет* съеден GC
  в Python 3.11+. Сохраняй task в `self`.
- **Не блокируй loop.** Оборачивай блокирующие SDK-вызовы в `await
  utils.run_sync(func, *args)`.
- **Не импортируй пакет как `friendly-telegram`** (с дефисом). Используй
  `friendly_telegram` или relative-imports (`from .. import utils`).
  Дефисное имя зашиммено для backward-compat, но новый код должен быть
  чистым.
- **Стиль `message`-аргумента**: каждая команда и watcher получают
  Telethon `Message`. После `await utils.answer(...)` *оригинальное*
  сообщение пропало, если бот его отредактировал; для follow-up'ов
  используй возвращаемое значение.
- **Ratelimit'ь свою background-работу.** Telegram'ские flood-пороги
  удивительно тесные. `await asyncio.sleep(...)` между bulk-операциями.
- **Тестируй на одноразовом аккаунте.** Юзерботы — нарушение Telegram'ских
  ToS.
- **Restart vs reload.** `.loadmod` с тем же именем класса
  перегружает на месте — вызывается `on_unload`, создаётся свежий
  инстанс. Часть state'а (открытые сокеты, aiogram-хендлеры) переживает
  только полный `.restart`.
- **Логирование.** `import logging; logger = logging.getLogger(__name__)`.
  Видимый дефолтный уровень — `INFO` — используй `logger.debug` для
  шумных трейсов.

---

## Куда смотреть в кодовой базе

- [`friendly_telegram/loader.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/loader.py) —
  базовый класс `Module`, декоратор `tds`, логика регистрации.
- [`friendly_telegram/dispatcher.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/dispatcher.py) —
  парсинг команд, security-проверки.
- [`friendly_telegram/security.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/security.py) —
  предикаты прав за `@loader.owner` и компанией.
- [`friendly_telegram/inline/`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/inline/) — пакет
  inline-менеджера: `manager.py` (lifecycle/диспатч), `types.py`
  (обёртка `InlineCall`, хелперы).
- [`friendly_telegram/modules/`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/modules/) —
  встроенные модули. Лучшие живые примеры.

В сомнениях — копируй маленький core-модуль (`bot_token.py`,
`nocollisions.py`) и модифицируй.
