# Contributing

Thanks for improving `miband-bot`. This project is intentionally small: keep changes practical, testable and clear for self-hosted users.

## Local Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt -e mi-fitness-python
```

Run checks before opening a pull request:

```sh
.venv/bin/python -m py_compile fitness_bot.py miband_sync.py $(find miband_tracker -name '*.py' | sort)
.venv/bin/python -m pytest
.venv/bin/python -m pytest mi-fitness-python/tests/unit
.venv/bin/ruff check .
.venv/bin/python -m pip check
docker compose build
```

## Secrets

Never commit real files from:

- `secrets.env`;
- `data/`;
- `token*.json`;
- `status*.json`;
- SQLite databases or CSV exports.

Use `secrets.env.example` in documentation and tests.

## Code Style

- Prefer the existing Python style and small focused modules.
- Keep user-facing Telegram text clear and concise.
- Add tests for behavior changes.
- Keep Russian UI text valid; Ruff `RUF001/RUF002/RUF003` are ignored because Cyrillic strings are intentional.
- Do not mass-format vendored `mi-fitness-python` unless the change is specifically about updating that vendor copy.

## Reverse Engineering Etiquette

This project talks to unofficial Xiaomi Fitness APIs. Contributions must stay focused on legitimate personal use:

- do not add features for accessing other people's data without permission;
- do not publish real credentials, account ids, request signatures or private exports;
- document fragile API assumptions when adding reverse-engineered behavior;
- make optional/best-effort features fail gracefully when Xiaomi changes an endpoint.

## Vendored SDK

`mi-fitness-python` is kept in this repository as a vendored source copy. See `VENDORED.md` before changing it. When updating the vendor copy, document the upstream source, version or commit, and any local patches.
