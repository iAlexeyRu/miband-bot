# miband-bot

[Русский](README.md) | English

A personal Telegram bot for Xiaomi Fitness / Mi Band data.

It fetches steps, sleep, heart rate and SpO2 from Xiaomi Fitness, stores the history in a local SQLite database, and shows a practical Telegram menu. The goal is simple: your band data stays on your own server, while Telegram becomes a convenient place to check today's health snapshot, run a manual sync or export CSV files.

The project is designed for one owner. It is not a public multi-user bot and not a medical service.

## What It Does

- Shows recent steps, sleep, heart rate and SpO2 in Telegram.
- Runs manual sync from a Telegram button.
- Syncs data automatically on a schedule.
- Stores history in SQLite under `data/`.
- Exports accumulated tables as a ZIP with CSV files.
- Runs with Docker Compose.
- Writes the Xiaomi token atomically with mode `0600`.

## Who It Is For

This project is useful if you:

- use Xiaomi Fitness / Mi Band;
- want to see your own data in Telegram;
- are comfortable running a small self-hosted service;
- understand that unofficial APIs can break when Xiaomi changes something.

It is not a good fit if you need a multi-user SaaS, medical-grade accuracy, guaranteed compatibility with every band, or an official Xiaomi API.

## Reverse Engineering Notice

`miband-bot` is an unofficial project. It is not affiliated with Xiaomi, Zepp, Huami, Telegram or their partners.

Xiaomi Fitness access is based on reverse engineering of unofficial APIs. This means:

- Xiaomi can change the API without notice;
- login or sync can temporarily stop working;
- use the project only with your own accounts and your own data;
- follow applicable laws and service terms in your jurisdiction;
- wearable data is not a medical diagnosis.

## How It Works

```text
Mi Band -> Xiaomi Fitness cloud -> miband-bot -> SQLite -> Telegram menu / CSV export
```

Docker Compose starts two processes:

- `tracker` - periodically syncs data from Xiaomi Fitness;
- `fitness-bot` - responds in Telegram, shows the menu, starts manual sync and exports data.

Both processes share `./data`. Writes are protected by a file lock, so background sync and manual sync do not write SQLite/token files at the same time.

## Requirements

- A server or home machine with Docker and Docker Compose.
- A Telegram bot token from [@BotFather](https://t.me/BotFather).
- Your Telegram user id.
- A Xiaomi account with Xiaomi Fitness data.

## Quick Start

1. Copy the secrets template:

```sh
cp secrets.env.example secrets.env
```

2. Fill at least these variables:

```env
TELEGRAM_BOT_TOKEN=123456:replace-me
TELEGRAM_ALLOWED_USER_ID=123456789
```

3. Start the service:

```sh
docker compose up -d --build
docker compose logs -f fitness-bot
```

4. Open your Telegram bot and send `/start`.

5. The bot will show a Xiaomi login button. Confirm login through the link/QR flow. After that the bot saves `data/token_<telegram_user_id>.json`, runs the first sync and opens the main menu.

## Configuration

Main variables live in `secrets.env`:

```env
TELEGRAM_BOT_TOKEN=123456:replace-me
TELEGRAM_ALLOWED_USER_ID=123456789
SYNC_INTERVAL=900
QUERY_DURATION=2
ENABLE_FDS_SLEEP_DETAILS=true
```

- `TELEGRAM_BOT_TOKEN` - your Telegram bot token.
- `TELEGRAM_ALLOWED_USER_ID` - the single Telegram user id allowed to access the bot.
- `SYNC_INTERVAL` - background sync interval in seconds. `900` = 15 minutes.
- `QUERY_DURATION` - how many recent days to query on each sync.
- `ENABLE_FDS_SLEEP_DETAILS` - whether to try fetching detailed FDS sleep data.

Database and status paths are already set in `compose.yaml`. If you run without Docker, see `secrets.env.example`.

## Where Data Lives

Runtime files are created under `./data`:

- `token_<telegram_user_id>.json` - Xiaomi auth token, secret file;
- `miband_<telegram_user_id>.db` - SQLite database with health data;
- `status_<telegram_user_id>.json` - latest sync status;
- `fitness_bot_state.db` - Telegram menu state;
- `sync_<telegram_user_id>.lock` - sync lock file.

Do not commit `secrets.env`, `data/`, `*.db`, `token*.json` or `status*.json`. These files are already listed in `.gitignore`.

## Bot Commands

- `/start` - open the menu or start Xiaomi login.
- `/sync` - run manual sync.
- `/status` - show local database status.

Most actions are done with buttons in the Telegram menu.

## CSV Export

The menu includes data export. The bot builds a ZIP with CSV tables and sends it through Telegram.

Remember: the ZIP contains health data and travels through Telegram infrastructure. Do not send it to shared chats or store it where other people can access it.

## Local Development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt -e mi-fitness-python
.venv/bin/python -m py_compile fitness_bot.py miband_sync.py $(find miband_tracker -name '*.py' | sort)
.venv/bin/python -m pytest
.venv/bin/python -m pytest mi-fitness-python/tests/unit
.venv/bin/ruff check .
.venv/bin/python -m pip check
```

Entrypoints are kept for Docker and local compatibility:

```sh
python -u miband_sync.py
python -u fitness_bot.py
```

If installed as a Python package, console scripts are available:

```sh
miband-sync
miband-fitness-bot
```

## Troubleshooting

**The bot does not respond.**
Check `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_ID` and logs:

```sh
docker compose logs -f fitness-bot
```

**Sync says token is missing.**
Open the bot in Telegram, send `/start` and complete the Xiaomi login flow.

**The token expired.**
Run Xiaomi login again from the menu. You can remove the old token from `data/`.

**Some data is missing or there is no SpO2/sleep detail.**
Check that Xiaomi Fitness itself shows that data. Some data depends on the band model, sharing settings and unofficial API availability.

**Everything broke after a Xiaomi update.**
That is an expected risk for a reverse-engineering project. Check issues/README and logs, then update the code or temporarily disable the affected feature.

## License And Vendored SDK

This project is licensed under GNU GPL v3.0 or later. The full license text is in [LICENSE](LICENSE).

The `mi-fitness-python` SDK is kept in this repository as a vendored source copy and remains under its own GNU GPL v3.0 license: [mi-fitness-python/LICENSE](mi-fitness-python/LICENSE). Origin and update policy are documented in [VENDORED.md](VENDORED.md).
