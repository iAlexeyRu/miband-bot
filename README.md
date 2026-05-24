# miband-bot

Русский | [English](README_EN.md)

Однопользовательский сервис синхронизации Xiaomi Fitness и Telegram-бот.

Бот сохраняет данные здоровья из Xiaomi Fitness в SQLite и показывает в Telegram меню с шагами, сном, пульсом, SpO2, аналитикой, ручной синхронизацией и экспортом CSV.

## Первый запуск

1. Создайте `secrets.env` с переменными ниже.
2. Запустите Docker Compose.
3. Откройте бота в Telegram и отправьте `/start`.
4. Бот покажет кнопку входа в Xiaomi. Подтвердите вход, после этого бот сохранит `data/token_<telegram_user_id>.json`, запустит первую синхронизацию и откроет главное меню.

```env
TELEGRAM_BOT_TOKEN=123456:telegram-token
TELEGRAM_ALLOWED_USER_ID=123456789
SYNC_INTERVAL=900
QUERY_DURATION=2
ENABLE_FDS_SLEEP_DETAILS=true
```

## Docker

```sh
docker compose up -d --build
docker compose logs -f fitness-bot
```

Оба сервиса используют общую папку `./data`. Синхронизация защищена файловым lock в этой папке, поэтому ручной sync из Telegram и daemon не пишут в SQLite/token одновременно.

## Локальные проверки

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt -e mi-fitness-python
.venv/bin/python -m py_compile fitness_bot.py miband_sync.py $(find miband_tracker -name '*.py' | sort)
.venv/bin/python -m pytest
.venv/bin/python -m pytest mi-fitness-python/tests/unit
.venv/bin/ruff check .
.venv/bin/python -m pip check
```

## Runtime

Entrypoints сохранены для совместимости с Docker:

```sh
python -u miband_sync.py
python -u fitness_bot.py
```

Секреты лежат в `secrets.env` и `data/token_<telegram_user_id>.json`; не коммитьте их. Token-файлы записываются атомарно с правами `0600`.

## Лицензия

Проект распространяется под GNU GPL v3.0. Vendored SDK `mi-fitness-python` сохранён со своей GPL v3.0 лицензией в `mi-fitness-python/LICENSE`.
