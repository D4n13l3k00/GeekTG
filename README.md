<div align="center">

# GeekTG · Рефорк Friendly Telegram (от GeekTG)

[🇬🇧 English version](README.en.md)

[![Python](https://img.shields.io/badge/python-3.11%20%E2%80%93%203.14-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Version](https://img.shields.io/badge/version-4.4.4-informational)](https://github.com/D4n13l3k00/GeekTG/releases)
[![License](https://img.shields.io/badge/license-AGPL--3.0--or--later-green)](LICENSE)
[![Telethon](https://img.shields.io/badge/telethon-1.40%2B-blue?logo=telegram&logoColor=white)](https://github.com/LonamiWebs/Telethon)
[![uv](https://img.shields.io/badge/uv-ready-blueviolet?logo=astral)](https://github.com/astral-sh/uv)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000)](https://github.com/psf/black)

</div>

> ⚠️ Юзерботы нарушают ToS Telegram. Запускай на номере, который не жалко
> потерять. Не используй дефолтные API-ключи в проде — получи свои на
> [my.telegram.org/apps](https://my.telegram.org/apps).

Telegram-**юзербот** с inline-ботом, маленьким веб-интерфейсом
для первичной настройки и системой сторонних модулей.

Изначально основан на
[friendly-telegram/friendly-telegram](https://github.com/friendly-telegram/friendly-telegram),
форкнут командой GeekTG ([GeekTG/Friednly-Telegram](https://github.com/GeekTG/Friednly-Telegram)), потом был заброшег из-за потери интереса команды. За основну взял последний и обновил под новые зависимости и реалии.

---

## 🔀 Что изменилось в этом форке

API модулей немного изменился (старые поддерживаются), можно ознакомиться в [документации](/docs/).
Так же документация доступна в [GitHub Pages](https://d4n13l3k00.github.io/GeekTG)

**Что поменялось?** Да многое: обновлен веб, добавлена поддержка анимированных смайлов,
добавлена типизация для Pylance. А самое главное что бота можно установить через uv как пакет и
будет полная поддержка тайпингов для создания своих модулей!

---

## 📦 Установка

### Вариант A — `uv` (рекомендуется)

```bash
uv tool install git+https://github.com/D4n13l3k00/GeekTG # --python 3.13 к примеру для установки конкретной версии
gtg
```

`uv` — однофайловый Python-тулчейн, инсталлер на
[astral.sh/uv](https://astral.sh/uv). Фиксирует точную версию Python, собирает
wheel и изолирует зависимости. Обновление — `uv tool upgrade gtg`.

### Вариант B — Из исходников

```bash
git clone https://github.com/D4n13l3k00/GeekTG
cd GeekTG
uv sync
uv run gtg
```

### Вариант C — Docker / Compose

```bash
docker compose up -d --build
docker compose logs -f gtg
```

[`docker-compose.yml`](docker-compose.yml) монтирует именованный том на data-директорию, чтобы сессии переживали `docker compose down`.

---

## 🚀 Первый запуск

Выводит баннер с data-директорией и открывает веб-мастер на свободном порту:

```yaml
🌐 Web UI is ready. Open one of:
  • http://localhost:8888       (только эта машина)
  • http://192.168.1.42:8888    (локальная сеть)
  • http://203.0.113.7:8888     (публично — проверь, что порт открыт)
```

Мастер проведёт через:

1. **API-ключи** — получить на [my.telegram.org/apps](https://my.telegram.org/apps).
2. **Номер телефона** — международный формат, например `+79991234567`.
3. **Код подтверждения** — приходит в другой залогиненный сеанс Telegram (чат «Telegram»), иначе по SMS.
4. **Пароль 2FA**, если включён.

После этого дашборд показывает профиль и кнопку открыть *Избранное* — там вводить команды вроде `.help`, `.info`, `.loadmod`.

---

## ⚙️ CLI-флаги

| Флаг | Что делает |
| ---- | ---------- |
| `gtg --print-data-dir` | Напечатать data-директорию и выйти |
| `gtg --data-root /path` | Переопределить data-директорию |
| `gtg --platform "My VPS"` | Переопределить имя платформы в `.info` (или `$GTG_PLATFORM`) |
| `gtg --port 8888` | Зафиксировать порт веб-UI (по умолчанию — случайный) |
| `gtg --no-web` | Без веб-UI |
| `gtg --no-inline` | Отключить inline-бота |
| `gtg --root` / `-R` | Разрешить запуск от `root` (только для контейнеров) |
| `gtg --setup` | Войти в конфигуратор с уже существующей сессией |

Полный список — `gtg --help`.

---

## 📁 Где что лежит

Data-root по умолчанию — `~/.local/share/friendly-telegram` (`$XDG_DATA_HOME/friendly-telegram`). Переопределить через `$GTG_DATA_DIR` или `--data-root`.

```shell
~/.local/share/friendly-telegram/
├── config.json                      # глобальный + per-user конфиг
├── api_token.txt                    # api_id / api_hash
├── config-<user_id>.json            # БД модулей на аккаунт
├── friendly-telegram-+7…1234.session
├── loaded_modules/                  # сторонние .py, загруженные через .loadmod
└── assets/<user_id>/                # бинарные блобы из store_asset()
```

Бэкап и восстановление доступны прямо в веб-UI. Либо вручную: `tar czf gtg.tgz ~/.local/share/friendly-telegram/` — распаковать на новом хосте и запустить `gtg`.

---

## 🧩 Написание модулей

См. [документацию](https://d4n13l3k00.github.io/GeekTG/modules/).

---

## 🗺️ Статус и roadmap

Это maintenance/modernization-форк. Цели по порядку:

1. ✅ Поднять установку и запуск на Python 3.10 – 3.14.
2. ✅ Выпилить внешние зависимости, которых больше нет (Heroku, Okteto, Telethon-Mod).
3. ✅ Локальное хранилище, дружелюбный первый запуск.
4. ✅ Лучший DX для авторов модулей — type hints по всему core, ruff/black/isort через pre-commit, `inline.py` разбит на `inline/`.
5. 🟡 Настоящий self-update для wheel-инсталлов (сейчас заглушка, отсылающая к `uv tool upgrade`).
6. ✅ Документация — двуязычные доки под [`docs/`](docs/), сайт на MkDocs Material, деплой на [d4n13l3k00.github.io/GeekTG](https://d4n13l3k00.github.io/GeekTG/) на push в `master`.

Issues и PR приветствуются. Если после обновления сломался сторонний модуль — открой issue с трейсбэком.

---

## 📄 Лицензия

GNU AGPL v3 — см. [`LICENSE`](LICENSE).
Изначально Copyright © 2018-2022 The Friendly-Telegram Authors, форкнут командой GeekTG, рефреш — текущим мейнтейнером.
