# GeekTG · Friendly Telegram, освежённый

[🇬🇧 English version](README.md)

Telegram-**юзербот** с inline-ботом-компаньоном, маленьким веб-интерфейсом
для первичной настройки и плагинной системой сторонних модулей.

Изначально основан на
[friendly-telegram/friendly-telegram](https://github.com/friendly-telegram/friendly-telegram),
форкнут командой GeekTG, потом замороженный пару лет. Подобрал кодовую базу,
потому что она всё ещё обходит большинство современных альтернатив в самом
важном — *быть юзерботом*: маленький, хакабельный, без телеметрии, без SaaS —
и вернул её к жизни поверх Python-тулчейна 2026 года.

> ⚠️ Юзерботы нарушают ToS Telegram. Запускай на номере, который не жалко
> потерять. Не используй дефолтные API-ключи в проде — получи свои на
> [my.telegram.org/apps](https://my.telegram.org/apps).

---

## Что изменилось в этом рефреше

Ничего пользовательского не переписывалось — API модулей, inline-менеджер,
декораторы безопасности/ratelimit, диспетчер остались такими же. **Сторонние
модули продолжают работать** благодаря шиму, который выставляет пакет под
историческим именем ``friendly-telegram``.

Что поменялось:

- 🐍 **Python**-упаковка через `pyproject.toml` (hatchling) вместо старого
  bash-инсталлера / `requirements.txt`. Собирается обычный wheel, появляется
  консольный скрипт `gtg`.
- 📦 **Установка через `uv` / `pipx`** — одна команда, без ручных venv-ов и
  системного pip (бутстрапим его лениво для сторонних модулей со своими
  зависимостями).
- 🪪 **Telethon 1.40+** (upstream, не Mod-форк) с актуальным отпечатком
  устройства Pixel/Android — Telegram надёжно доставляет коды входа.
- 🗂 **Только локальное хранилище** — конфиг, сессии, модули и ассеты лежат
  под `~/.local/share/friendly-telegram/` (XDG-совместимо). Облачные каналы
  (`friendly-<uid>-data`, `friendly-<uid>-assets`) выпилены — больше нет
  левых каналов в списке чатов и flood-wait-ов на каждую запись конфига.
- 🌐 **Веб-UI переписан** — чистый двухшаговый мастер по-русски, анимированный
  aurora-фон, тёмные SweetAlert-ы, карточка профиля с замаскированным
  телефоном (`+7********10`) и кнопкой «Открыть Избранное».
- 🛡 **Корректный Ctrl-C / SIGTERM** — больше никаких 20-строчных трейсбэков
  на завершении.
- 🧹 **Удалено**: Heroku/Okteto-деплой, install.sh / install.ps1,
  `meval`-окружение для eval (сам модуль остался), git-self-update (заменили
  заглушкой со ссылкой на `uv tool upgrade`).
- 🩹 **Качество**: разрешили циклический импорт, перешли на `asyncio.run()`
  вместо `get_event_loop()`, починили hot-path в `SuperList`, держим задачи
  `on_unload` сильными ссылками от GC, дефолты структурированного логирования.

Подробнее: [`CHANGELOG`](docs/) (будет позже) — пока авторитетный источник
это `git log`.

---

## Установка

### Вариант A — `uv` (рекомендуется)

```sh
uv tool install git+https://github.com/D4n13l3k00/GeekTG
gtg
```

`uv` — однофайловый Python-тулчейн, инсталлер на
[astral.sh/uv](https://astral.sh/uv). Пинит точную версию Python, собирает
wheel и изолирует зависимости. Обновление — `uv tool upgrade gtg`.

### Вариант B — `pipx`

```sh
pipx install git+https://github.com/D4n13l3k00/GeekTG
gtg
```

### Вариант C — Docker / Compose

```sh
docker compose up -d --build
docker compose logs -f gtg
```

[`docker-compose.yml`](docker-compose.yml) монтирует именованный том на
data-директорию, чтобы сессии переживали `docker compose down`.

### Вариант D — из исходников

```sh
git clone https://github.com/D4n13l3k00/GeekTG
cd Friendly-Telegram
uv sync
uv run gtg
```

---

## Первый запуск

```sh
gtg
```

Печатает баннер с resolved data-директорией и открывает маленький
веб-мастер на свободном локальном порту. URL выводится в stdout:

```text
🌐 Web UI is ready. Open one of:
  • http://localhost:8888       (только эта машина)
  • http://192.168.1.42:8888    (локальная сеть)
  • http://203.0.113.7:8888     (публично — проверь, что порт открыт)
```

Мастер проводит через:

1. **API-ключи** — получить на [my.telegram.org/apps](https://my.telegram.org/apps).
2. **Номер телефона** — международный формат, например `+79991234567`.
3. **Код подтверждения** — Telegram присылает его в *другой
   залогиненный Telegram-сеанс*, если он есть (в чат с «Telegram»), иначе
   по SMS.
4. **Пароль 2FA**, если на аккаунте включено облачное.

После этого дашборд показывает профиль и одну кнопку — открыть
*Избранное* в Telegram, чтобы начать вводить команды вроде `.help`,
`.info`, `.loadmod`.

---

## Полезные CLI-флаги

| Флаг | Что |
| ---- | --- |
| `gtg --print-data-dir` | Напечатать resolved data-директорию и выйти |
| `gtg --data-root /path` | Переопределить data-директорию на этот запуск |
| `gtg --platform "My VPS"` | Переопределить имя платформы в `.info` (или `$GTG_PLATFORM`) |
| `gtg --port 8888` | Зафиксировать порт веб-UI (по умолчанию — случайный свободный) |
| `gtg --no-web` | Без веб-UI, конфигурировать через терминал |
| `gtg --no-inline` | Отключить inline-бота |
| `gtg --root` / `-R` | Разрешить запуск от `root` (не надо, кроме как в контейнере) |
| `gtg --setup` | Зайти в конфигуратор с уже существующей сессией |

Полный список — `gtg --help`.

---

## Где что лежит

Дефолтный data-root — `$XDG_DATA_HOME/friendly-telegram` (обычно
`~/.local/share/friendly-telegram`). Переопределить — через `$GTG_DATA_DIR`
или `--data-root`.

```text
~/.local/share/friendly-telegram/
├── config.json                      # глобальный + per-user конфиг
├── api_token.txt                    # api_id / api_hash
├── config-<user_id>.json            # БД модулей на аккаунт (был облачный канал)
├── friendly-telegram-+7…1234.session
├── loaded_modules/                  # сторонние .py, сохранённые через .loadmod
└── assets/<user_id>/                # бинарные блобы из store_asset()
```

Бэкап = `tar czf gtg.tgz ~/.local/share/friendly-telegram/`. Восстановление —
распаковать на новом хосте, запустить `gtg`. На стороне Telegram мигрировать
нечего.

---

## Inline-бот

`InlineManager` автоматически регистрирует inline-бота через `@BotFather`
на первом запуске — его используют core- и сторонние модули для inline-кнопок,
галерей и форм. Чтобы подставить своего:

```text
.setbottoken 123456789:AA…
.restart
```

Остальные команды: `.bottoken` (показывает текущего бота, токен замаскирован),
`.resetbottoken` (очистить и пересоздать на следующем старте).

---

## Писать модули

Модули — обычные `.py`-файлы; loader подбирает классы с именами,
заканчивающимися на `Mod`, унаследованные от
`friendly_telegram.loader.Module`. Исторический алиас пакета сохранён —
существующие модули с `from .. import loader, utils` продолжают работать.

Минимальный пример:

```python
# requires: pillow
from telethon.tl.custom import Message
from .. import loader, utils

@loader.tds
class HelloMod(loader.Module):
    """Дружелюбное приветствие."""

    strings = {
        "name": "Hello",
        "hi": "👋 <b>Привет, {}!</b>",
    }

    @loader.unrestricted
    async def hicmd(self, message: Message):
        """Сказать привет."""
        await utils.answer(message, self.tr("hi", message).format(
            (await message.client.get_me()).first_name,
        ))
```

Кинуть в `~/.local/share/friendly-telegram/loaded_modules/HelloMod.py`
(или загрузить через `.loadmod` по URL/файлу). Директива
`# requires: pillow` авто-ставит недостающие pip-зависимости в активное
окружение — работает и в `uv tool`-venv-ах без pip.

---

## Статус и roadmap

Это maintenance / modernization-форк. Цели по порядку:

1. ✅ Поднять установку и запуск на Python 3.9 – 3.13.
2. ✅ Выпилить внешние зависимости, которых больше нет (Heroku, Okteto, Telethon-Mod).
3. ✅ Локальное хранилище, дружелюбнее первый запуск.
4. 🟡 Лучший DX для авторов модулей — type hints, ruff/black/isort через
   pre-commit, поменьше монолитов (`inline.py` уже разбит на `inline/`,
   `dispatcher.py` следующий).
5. 🟡 Настоящий self-update для wheel-инсталлов (сейчас заглушка, отсылающая
   к `uv tool upgrade`).
6. 🟡 Обновление документации — upstream `docs.geektg.tk` оффлайн; новые
   доки живут под [`docs/`](docs/).

Issues и PR приветствуются. Если ты поддерживал сторонний FTG-модуль и
после рефреша что-то сломалось — открой issue с трейсбэком; обратная
совместимость — это жёсткая цель, а не мягкая.

---

## Лицензия

GNU AGPL v3 — см. [`LICENSE`](LICENSE).
Изначально Copyright © 2018-2022 The Friendly-Telegram Authors, модифицировано
командой GeekTG, рефреш — текущим мейнтейнером.
