# База данных и хранение ассетов

Мини-асинхронное key-value-хранилище на JSON-файле под
`<data_dir>/config-<user_id>.json` плюс хранение бинарных блобов рядом
для медиа, которое не лезет в JSON. Где резолвится `<data_dir>` —
описано в **[utils.md → `get_data_dir`](utils.md#get_data_dir---str-кэшируется-lru_cachemaxsize1)**.

Класс `Database` наследуется от `dict` и партиционирует хранилище по
**owner**-namespace'у — конвенция: используй `__name__`, чтобы
удаление модуля было чистым delete'ом.

---

## Архитектура

Два слоя:

- **Frontend** ([`database/frontend.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/database/frontend.py))
  — публичный класс `Database` с debounced-записями и API ассетов.
- **Backend** ([`database/backend.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/database/backend.py))
  — JSON read/write на диск + персистентность ассет-блобов.
  Исторический cloud-backend убран; теперь всё локально.

Файлы на диске:

```text
<data_dir>/
├── config-<user_id>.json         # KV-хранилище (per-account)
└── assets/<user_id>/
    ├── 1.bin, 2.bin, …           # бинарные блобы
    └── .next_id                  # auto-increment-счётчик
```

---

## KV-хранилище

```python
@loader.owner
async def bumpcmd(self, message: Message):
    db = self.ctx.db
    n = db.get(__name__, "counter", 0)
    db.set(__name__, "counter", n + 1)
    await utils.answer(message, f"counter теперь {n + 1}")
```

Конвенции:

- **Первый аргумент** (`owner`): используй `__name__` для private-данных.
- **Значения** должны быть JSON-сериализуемыми.
- Cross-module-чтения разрешены — делай редко и документируй контракт
  с обеих сторон.

### Чтение

| Вызов | Возвращает |
| ---- | ------- |
| `db.get(owner, key, default=None)` | Значение или `default`, если нет. |
| `db[owner]` | Вложенный dict owner'а (рейзит `KeyError`, если нет). |
| `db.keys()` | Все namespace'ы. |

### Запись и flush-семантика

`db.set(owner, key, value)` строго говоря **не async** — возвращает
`NotifyingFuture`, который можно либо fire-and-forget'ить, либо
await'ить:

```python
self.ctx.db.set(__name__, "k", v)            # fire-and-forget (типичный случай)
await self.ctx.db.set(__name__, "k", v)      # ждёт записи на диск
```

Внутри записи коалесцируются через 10-секундный debounce: первый
несохранённый `set` шедулит flush, последующие `set`'ы в окне
piggybackают на тот же future. Await future'а отменяет задержку и
flushит сразу.

`await db.save()` форсирует немедленный flush невзирая на pending-debounce
— полезно в shutdown-путях.

Поэтому `db.set` в тесном loop'е безопасен — это один disk-write раз в
~10 с, не один на вызов.

---

## Хранение ассетов

Для бинарных блобов, которым не место в JSON (картинки, voice-заметки,
архивы). Storage локальный, cloud-backend убран.

```python
asset_id = await db.store_asset(b"...")            # bytes/bytearray
asset_id = await db.store_asset("/tmp/cat.jpg")    # путь
asset_id = await db.store_asset(message)           # Telethon Message (скачает media)
asset_id = await db.store_asset("plain text")      # str → utf-8 bytes
db.set(__name__, "cat_id", asset_id)

raw: bytes | None = await db.fetch_asset(db.get(__name__, "cat_id"))
```

`store_asset` возвращает auto-incrementing `int`. `fetch_asset`
возвращает raw-bytes или `None`, если ассет пропал. Оба под защитой
внутреннего `asyncio.Lock`, чтобы конкурентные `store_asset` не
коллайдились по ID.

> **Note по миграции.** В старых FTG `fetch_asset` возвращал Telethon
> `Message`. Локальный storage возвращает raw-bytes. Чтобы переслать —
> `await client.send_file(chat, file=raw)`.

---

## Зарезервированные DB-ключи

Namespace'ы / ключи, которые читают/пишут core-модули. Не затирай их из
third-party.

| Owner (`__name__`) | Key | Назначение |
| ------------------ | --- | ------- |
| `friendly_telegram.main` | `command_prefix` | Триггер-символ команды (дефолт `.`). |
| `friendly_telegram.main` | `blacklist_chats`, `blacklist_users` | Дропать сообщения до dispatch'а. |
| `friendly_telegram.main` | `disabled_watchers` | Модули с muted `watcher`. |
| `friendly_telegram.main` | `language`, `langpacks` | i18n / langpack-настройки. |
| `friendly_telegram.security` | `owner`, `sudo`, `support` | Permission-группы. |
| `friendly_telegram.security` | `masks` | Per-command permission-override. |
| `friendly_telegram.security` | `bounding_mask`, `default`, `any_admin` | Global security-config. |
| `friendly_telegram.security` | `blacklist_users` | Hard-deny-список. |
| `friendly_telegram.modules.help` | `hide` | Модули, скрытые из `.help`. |
| `geektg.inline` | `bot_token` | Token inline-бота. |
| `friendly_telegram.modules.corectrl` | `aliases` | Юзерские aliases команд. |
| `friendly_telegram.modules.loader` | `chosen_preset` | Repo-preset (`"none"` по дефолту — без remote-fetch). |

Списки перечитываются из БД на каждом lookup'е, так что изменения
вступают мгновенно без рестарта.

---

## Крайние случаи

- **Concurrency.** Frontend предполагает один asyncio-loop — он не
  thread-safe. Если надо трогать из другого треда — используй
  `asyncio.run_coroutine_threadsafe`.
- **Corruption.** Битый `config-<user_id>.json` молча трактуется как
  `{}` при загрузке (бэкап *не* делается автоматически — бэкапь сам,
  если экспериментируешь).
- **No-op mode.** Тесты конструируют frontend с `noop=True` /
  `backend=None`; API работает, но ничего не персистится.
