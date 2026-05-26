# miband-bot

[Русский](README.md) | English

A personal self-hosted Telegram bot for your Xiaomi Fitness / Mi Band data.

Fetches steps, sleep, heart rate, SpO2, stress, daily activity, weight,
and workouts from the Xiaomi Fitness cloud, stores them in a local SQLite database,
and provides access to them directly from Telegram —
without third-party services and without sharing your data with anyone.

> **This project is designed for a single owner.**
> This is not a public bot or a medical service.

## Features

- View recent steps, sleep, heart rate, SpO2, stress, weight, and workouts in Telegram.
- Manual and scheduled automatic synchronization.
- Auto-refresh of the pinned main menu message after background synchronization.
- History storage in SQLite (`data/`).
- Export of all tables to a ZIP archive with CSV files directly into the chat.
- Deployment via Docker Compose.
- Atomic writing of the Xiaomi token with `0600` permissions.
- Smart auto-binding to the first user (whitelist).

## How it works

```text
Mi Band → Xiaomi Fitness cloud → miband-bot → SQLite → Telegram / CSV
```

Docker Compose runs two processes:

- `tracker` — periodically synchronizes data from Xiaomi Fitness;
- `fitness-bot` — serves the Telegram menu, handles manual sync, and performs exports.

Both processes work with the same `./data` folder. Concurrent write access
is prevented by a file-based lock.

## Requirements

- Docker and Docker Compose (or installed Python 3.11+).
- Telegram bot token from [@BotFather](https://t.me/BotFather).
- A Xiaomi account with Xiaomi Fitness data.

## Quick Start

### Method 1: Seamless One-Click Installation (Recommended)

If you don't have the project files on your machine yet, you can automatically download and set everything up using a single command in your terminal:

- **macOS / Linux:**
  ```sh
  curl -fsSL https://raw.githubusercontent.com/iAlexeyRu/miband-bot/main/install.sh | bash
  ```
- **Windows (PowerShell):**
  ```powershell
  powershell -c "irm https://raw.githubusercontent.com/iAlexeyRu/miband-bot/main/install.ps1 | iex"
  ```

The installer will automatically create a `miband-bot` directory, download and extract the project files, verify dependencies, and launch the interactive setup!
Running the same PowerShell command again on an already configured install will update the files and start the bot without asking for the Telegram token again.

---

### Method 2: Launch from Downloaded Directory

If you have already cloned the repository via `git clone` or downloaded the ZIP archive manually:

- **macOS / Linux:**
  ```sh
  ./setup.sh
  ```
- **Windows:**
  Double-click the `setup.bat` file or run it in the console:
  ```cmd
  setup.bat
  ```

The script will automatically check your environment, guide you step-by-step to get your Telegram bot token, create the `secrets.env` configuration, set up the Python virtual environment (if you choose to run without Docker), and let you launch the bot with a single key press!
After setup, you can start the bot again with `run_local.sh` on macOS/Linux or `run_local.bat` on Windows from the `miband-bot` folder.

---

### Method 3: Fully Manual Setup:

1. Copy the configuration template:
   ```sh
   cp secrets.env.example secrets.env
   ```
2. Specify your `TELEGRAM_BOT_TOKEN` in the `secrets.env` file. **Leave the `TELEGRAM_ALLOWED_USER_ID` variable blank** — the bot will automatically bind to you upon the first start.
3. Start the Docker containers:
   ```sh
   docker compose up -d --build
   ```
4. Open your created bot in Telegram and send the `/start` command — the bot will recognize your account, bind it as the sole owner, and begin synchronization!

## Settings

All variables are in `secrets.env`:

| Variable | Default | Description |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token |
| `TELEGRAM_ALLOWED_USER_ID` | — | Allowed user ID (leave empty for auto-binding) |
| `SYNC_INTERVAL` | `900` | Background sync interval, in seconds |
| `QUERY_DURATION` | `2` | Fetch depth during sync, in days |
| `ENABLE_FDS_SLEEP_DETAILS` | `true` | Download detailed FDS night sleep data |

Paths to the database and status files are defined in `compose.yaml`. For running without Docker, refer to `secrets.env.example`.

## Data Files

Runtime files are created in `./data`:

| File | Content |
| --- | --- |
| `token_<id>.json` | Xiaomi auth token (**secret**) |
| `miband_<id>.db` | SQLite database with health data |
| `status_<id>.json` | Last sync status |
| `allowed_user.id` | ID of the bound owner |
| `fitness_bot_state.db` | Telegram menu internal state |
| `sync_<id>.lock` | Sync lock file |

`secrets.env`, `data/`, `*.db`, `token*.json`, and `status*.json`
are added to `.gitignore` — do not commit them.

## Commands

| Command | Action |
| --- | --- |
| `/start` | Open menu or start Xiaomi login flow |
| `/sync` | Start manual synchronization |
| `/status` | Show local database status |

## Local Development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt -e mi-fitness-python
.venv/bin/python -m py_compile fitness_bot.py miband_sync.py \
    $(find miband_tracker -name '*.py' | sort)
.venv/bin/python -m pytest
.venv/bin/python -m pytest mi-fitness-python/tests/unit
.venv/bin/ruff check .
.venv/bin/python -m pip check
```

Entry points:

```sh
python -u miband_sync.py      # or: miband-sync
python -u fitness_bot.py      # or: miband-fitness-bot
```

## Troubleshooting

**The bot does not respond** — check `TELEGRAM_BOT_TOKEN`, check the logs, and make sure you were the first to send `/start` to the bot to bind it. If you need to reset the bound owner, simply delete the file `data/allowed_user.id` and send `/start` again.

```sh
docker compose logs -f fitness-bot
```

**Token not found** — send `/start` and complete the Xiaomi login flow.

**Token expired** — start a re-login from the menu; the old file
can be deleted from `data/`.

**No SpO2 or sleep details** — make sure this data is visible
in the Xiaomi Fitness app itself. Availability depends on the band model
and data sharing settings.

**Everything broke after a Xiaomi update** — this is an expected risk
when working with unofficial APIs. Check issues and logs, then
update the code or temporarily disable the problematic module.

## Important: Reverse Engineering and Limitations

`miband-bot` is an unofficial project, not affiliated with Xiaomi, Zepp,
Huami, or Telegram.

Data access is implemented via reverse engineering of closed APIs,
therefore:

- Xiaomi may change the API without warning;
- authorization or synchronization may temporarily stop working;
- use this project only with your own accounts and data;
- comply with applicable laws and services' terms of use;
- wristband data is not a medical opinion.

## License

The project is distributed under the [GNU GPL v3.0 or later](LICENSE).

SDK `mi-fitness-python` is included as a vendored source copy under
[GNU GPL v3.0](mi-fitness-python/LICENSE). Details are in [VENDORED.md](VENDORED.md).
