# miband-bot

Single-user Xiaomi Fitness sync service and Telegram bot.

The bot stores Xiaomi Fitness health data in SQLite and exposes a Telegram menu for recent steps, sleep, heart rate, SpO2, trends, manual sync and CSV export.

## First Run

1. Create `secrets.env` from the variables below.
2. Start Docker Compose.
3. Open the bot in Telegram and send `/start`.
4. The bot will show a Xiaomi login button. Confirm the login, then the bot saves `data/token_<telegram_user_id>.json`, runs the first sync and opens the main menu.

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

Both services share `./data`. Sync runs are guarded by a file lock in that directory, so manual sync from Telegram and the daemon do not write SQLite/token files at the same time.

## Local Checks

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

Entrypoints kept for Docker compatibility:

```sh
python -u miband_sync.py
python -u fitness_bot.py
```

Secrets live in `secrets.env` and `data/token_<telegram_user_id>.json`; do not commit them. Token files are written atomically with mode `0600`.

## License

This project is licensed under GNU GPL v3.0. The vendored `mi-fitness-python` SDK is kept under its own GPL v3.0 license in `mi-fitness-python/LICENSE`.
