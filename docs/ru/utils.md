# `utils` cheatsheet

`from friendly_telegram import utils` — мелкие хелперы, используемые
во фреймворке и core-модулях. Трогай, когда модулю нужно парсить
аргументы, отвечать, экранировать HTML, резолвить пути или шеллить.
Исходник: [`friendly_telegram/utils.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/utils.py).

`Message` ниже — это `telethon.tl.custom.Message` (НЕ
`telethon.tl.types.Message` — кастомный сабкласс отдаёт `.client`,
`.edit`, `.delete`, `.respond`, `.get_reply_message`, `.is_reply`,
`.raw_text`).

Документ разбит по категориям. Сигнатуры, форма возврата и крайние
случаи расписаны подробно — copy-paste, а не приблизительно.

---

## Telegram I/O

### `answer(message, response, **kwargs) -> List[Message]` *(async)*

```python
async def answer(message, response, **kwargs) -> List[Message]
```

`message: Union[Message, List[Message]]` — Telethon
`telethon.tl.custom.Message` или list, в котором голова — сообщение для
edit/reply, а хвост — сообщения, которые надо удалить перед отправкой
(удобно для flow "работаю… → готово").
`response` может быть `str`, Telethon `Message`, raw `bytes` или
file-like.

Поведение:

- Если `message.out` (мы его отправили) — **редактирует**; иначе
  реплаит с `reply_to = message.reply_to_msg_id`.
- HTML/markdown парсится через `message.client.parse_mode`, если не
  передан `parse_mode=`; `link_preview` дефолтит в `False`.
- Если рендер ≥ 4096 символов (или `asfile=True`), фолбэк на
  `send_file` с `command_result.txt` и удаление оригинального
  outgoing-сообщения.
- Прокидываемые kwargs: `parse_mode`, `link_preview`, `asfile`,
  `filename`, `reply_to`, плюс всё, что принимает `client.send_file`.

Всегда смотри `result[0]` для последующих правок — оригинальное
сообщение могло пропасть.

### `get_user(message) -> User | None` *(async)*

Возвращает Telethon-`User` отправителя с восстановлением после
cache-miss: переитерируется по диалогам (DM) или участникам группы, если
entity не закэширован. Возвращает `None` (и пишет `critical`-лог), если
`peer_id` некорректен или поиск не удался. Обрабатывает
`BotMethodInvalidError` при работе ботом.

### `get_chat_id(message) -> int`

Числовой chat ID без `-100`-префикса каналов (через
`telethon.utils.resolve_id`). Полезен для сериализации в компактные
строки.

### `get_entity_id(entity) -> int`

Обёртка над `telethon.utils.get_peer_id()` для любых entity-like
объектов.

---

## Парсинг аргументов

### `get_args(message) -> List[str]`

`shlex.split()` на всё после первого whitespace-токена `message.message`
(или самой строки).

- Пустое / нет аргументов → `[]`.
- Кривой quoting → `[tail]` (single-element list с raw-хвостом — чтобы
  `len()`-проверки не падали).
- Пустые токены отбрасываются.

### `get_args_raw(message) -> str`

Всё после первого whitespace одной строкой. Возвращает `""`, если
аргументов нет (никогда `False`/`None` — безопасно для `.strip()` /
`.split()` без guard'а).

### `get_args_split_by(message, sep) -> List[str]`

Сплитит `get_args_raw()` по `sep`, стрипает каждую секцию, дропает
пустые после стрипа. Всегда возвращает list.

### `get_target(message, arg_no=0) -> Optional[int]` *(async)*

Резолвит user-ID из сообщения в приоритете:

1. Первая `MessageEntityMentionName` в тексте сообщения.
2. `arg_no`-е слово `get_args(message)` (резолвится через `get_entity`).
3. Отправитель replied-to сообщения.
4. Peer user ID, если сообщение в DM.

`None`, если ничего не резолвится или кандидат не `User` (отбрасывает
чаты/каналы).

---

## Пути и data-директории

### `get_base_dir() -> str`

Абсолютный путь к установленной директории пакета
`friendly_telegram/` (на большинстве инсталляций read-only). Считается
из `__file__`, без syscall'ов.

### `get_dir(mod) -> str`

Абсолютная директория произвольного модуля (path-string или `__file__`).

### `get_data_dir() -> str` *(кэшируется, `lru_cache(maxsize=1)`)*

Writable data-директория, резолв в порядке:

1. `$GTG_DATA_DIR` (или легаси `$FTG_DATA_DIR`).
2. `$XDG_DATA_HOME/friendly-telegram`.
3. `~/.local/share/friendly-telegram`.

Создаётся на первом вызове. Сессии, конфиги, загруженные модули и
ассеты — всё лежит здесь.

---

## Runtime / платформа

### `get_platform_name() -> str`

Юзер-френдли тег платформы (`"📻 VDS"`, `"📱 Termux"`, `"🐳 Docker"`,
`"✌️ lavHost <id>"`). Порядок резолва:

1. Override `$GTG_PLATFORM` / `$FTG_PLATFORM`.
2. `$LAVHOST`.
3. Termux (`$PREFIX` содержит `com.termux`).
4. Docker (существует `/.dockerenv`).
5. Fallback `"📻 VDS"`.

Не кэшируется — env-override после import'а работает.

### `install_requirements(requirements, *, user_install=False, record=True) -> int` *(async)*

Best-effort runtime pip install:

1. `uv pip install --python <exe> <pkgs...>`, если `uv` в PATH.
2. `python -m pip install <pkgs...>`.
3. `python -m ensurepip --upgrade` и retry pip.

Возвращает код возврата subprocess'а (0 = успех). При успехе и
`record=True` дописывает пин'утые `pkg==version` строки в
`<data_dir>/auto_requirements.txt`, чтобы пересборка Docker'а могла их
повторить.

### `print_web_urls(port) -> None`

Печатает доступные веб-UI URL'ы (localhost + LAN IP + опционально
публичный IP) в каноническом bracket-формате IPv6. Используется
first-run-визардом.

---

## Форматирование и экранирование

### `escape_html(text) -> str`

`&` → `&amp;`, `<` → `&lt;`, `>` → `&gt;`. Принудительно кастит в `str`.

### `escape_quotes(text) -> str`

`escape_html()` + `"` → `&quot;`.

### `relocate_entities(entities, offset, text=None) -> list[Entity]`

Сдвигает offset'ы всех Telethon `MessageEntity` на `offset`, клипая по
длине `text`. Удаляет entity'и, которые становятся нулевой длины.
Мутирует входной list и возвращает его. С `text=None` clipping не
применяется.

---

## Прочее

### `rand(length) -> str`

Случайная ASCII letters+digits-строка нужной длины. Inline-менеджер
использует её для уникальных result-ID.

### `get_version_raw() -> str`

`"4.1.4"`-стиль версия из кортежа `__version__` пакета.

### `get_git_info() -> [str, str]`

`[short_sha_or_empty, github_url_or_empty]`. Lazy-import GitPython;
fallback к `["", ""]` на wheel/Docker-сборках без `.git`.

### `run_sync(func, *args, **kwargs) -> asyncio.Future`

Запускает блокирующую функцию в дефолтном executor'е. Всегда
await'ься.

```python
url = "https://example.com/big.jpg"
data = await utils.run_sync(requests.get, url)
```

### `run_async(loop, coro) -> Any`

Запускает async-корутину *синхронно* из non-async-контекста (например,
внутри callback'а, зарегистрированного через sync-API). Использует
`asyncio.run_coroutine_threadsafe` и блокирует до результата.

### `censor(obj, to_censor=None, replace_with="redacted_{count}_chars") -> obj`

Замазывает чувствительные атрибуты (`["phone"]` по дефолту) на объекте
и его вложенных `__dict__` — нужно, чтобы `/tracebacks` и web-визард не
сливали `client.phone` и т.п.

### `merge(a, b) -> dict`

Рекурсивный in-place мердж `a` в `b`. Вложенные dict'ы мерджатся
рекурсивно; параллельные list'ы делают union; скалярные значения `a`
перекрывают `b`.
