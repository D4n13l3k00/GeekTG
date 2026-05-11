# Документация для разработчиков GeekTG

Документация для тех, кто пишет модули или ковыряется во внутренностях
самого юзербота.

## Разработчикам модулей

- **[modules.md](modules.md)** — основной гайд: жизненный цикл, команды,
  watcher'ы, строки, конфиг, дистрибуция, лучшие практики. *Начни отсюда.*
- [inline.md](inline.md) — менеджер inline-бота: формы, галереи,
  `*_inline_handler`, `*_callback_handler`, обёртка `InlineCall`,
  возможность пробросить нативный aiogram-3.
- [security.md](security.md) — 13-битная битмаска прав, декораторы,
  bounding mask, runtime-переопределения, decision flow.
- [database.md](database.md) — JSON KV-хранилище и хранение бинарных
  ассетов.
- [utils.md](utils.md) — одностраничный cheatsheet
  `friendly_telegram.utils`.

## Пользовательская документация

Пользовательская документация лежит здесь обычным Markdown — PR'ы
приветствуются.

Отрендеренный Material-сайт публикуется из этого дерева на каждый push
в `master` по адресу <https://d4n13l3k00.github.io/GeekTG/>.

## Тур по кодовой базе

Файлы максимального воздействия, если хочется поменять сам бот:

| Файл | Что |
| ---- | ---- |
| [`friendly_telegram/main.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/main.py) | Загрузка, обработка сигналов, shutdown. |
| [`friendly_telegram/loader.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/loader.py) | Базовый класс `Module`, регистрация, lifecycle. |
| [`friendly_telegram/dispatcher.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/dispatcher.py) | Парсинг команд, обработка префиксов, security-гейты. |
| [`friendly_telegram/security.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/security.py) | Предикаты прав за `@loader.owner` и компанией. |
| [`friendly_telegram/inline/`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/inline/) | Менеджер inline-бота: lifecycle/диспатч (`manager.py`), обёртка `InlineCall` и хелперы (`types.py`). |
| [`friendly_telegram/database/`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/database/) | Локальное JSON KV-хранилище + ассеты. |
| [`friendly_telegram/web/`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/web/) | First-run web-визард и пост-логин дашборд. |
| [`friendly_telegram/modules/`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/modules/) | Встроенные модули. Лучшие живые примеры. |
| [`friendly_telegram/utils.py`](https://github.com/D4n13l3k00/GeekTG/blob/dev/friendly_telegram/utils.py) | Хелперы, используемые везде. |

## Сборка и dev workflow

```sh
uv sync                        # развернуть .venv из pyproject.toml
uv run gtg                     # старт из исходников
uv build                       # собрать wheel + sdist в dist/
uv pip install dist/*.whl      # поставить собранный wheel
```

Тесты живут в [`tests/`](https://github.com/D4n13l3k00/GeekTG/tree/dev/tests/) (pytest + pytest-asyncio). Запуск
— `uv run pytest`. Линтеры/форматтеры подключаются через pre-commit:

```sh
uv run pre-commit install         # одноразовая настройка
uv run pre-commit run --all-files
```

isort (`--profile black`), black и ruff гоняются на каждом коммите.
