# miband-bot

Русский | [English](README_EN.md)

Личный Telegram-бот для данных Xiaomi Fitness / Mi Band.

Он сам забирает шаги, сон, пульс и SpO2 из Xiaomi Fitness, складывает их в локальную SQLite-базу и показывает понятное меню в Telegram. Идея простая: данные с браслета остаются у вас на сервере, а Telegram становится удобной кнопкой «посмотреть здоровье за сегодня», «обновить вручную» или «выгрузить CSV».

Проект рассчитан на одного владельца. Это не публичный бот для многих пользователей и не медицинский сервис.

## Что умеет

- Показывает последние шаги, сон, пульс и SpO2 в Telegram.
- Запускает ручную синхронизацию кнопкой в меню.
- Автоматически синхронизирует данные по расписанию.
- Хранит историю в SQLite в папке `data/`.
- Экспортирует накопленные таблицы в ZIP с CSV-файлами.
- Работает через Docker Compose.
- Пишет Xiaomi token атомарно с правами `0600`.

## Кому подходит

Проект подойдет, если вы:

- пользуетесь Xiaomi Fitness / Mi Band;
- хотите видеть свои данные в Telegram;
- готовы запустить маленький self-hosted сервис;
- понимаете, что неофициальные API могут сломаться после изменений Xiaomi.

Проект не подойдет, если нужен многопользовательский SaaS, медицинская точность, гарантия совместимости со всеми браслетами или официальный Xiaomi API.

## Важно про reverse engineering

`miband-bot` - неофициальный проект. Он не связан с Xiaomi, Zepp, Huami, Telegram или их партнерами.

Доступ к данным Xiaomi Fitness сделан через reverse engineering неофициальных API. Это значит:

- Xiaomi может изменить API без предупреждения;
- вход или синхронизация могут временно перестать работать;
- используйте проект только для своих аккаунтов и своих данных;
- соблюдайте применимые законы и условия сервисов в вашей стране;
- данные браслета не являются медицинским заключением.

## Как это работает

```text
Mi Band -> Xiaomi Fitness cloud -> miband-bot -> SQLite -> Telegram menu / CSV export
```

В Docker Compose запускаются два процесса:

- `tracker` - периодически синхронизирует данные из Xiaomi Fitness;
- `fitness-bot` - отвечает в Telegram, показывает меню, запускает ручной sync и экспорт.

Оба процесса используют одну папку `./data`. Запись защищена файловым lock, поэтому фоновая и ручная синхронизация не пишут в SQLite/token одновременно.

## Что понадобится

- Сервер или домашняя машина с Docker и Docker Compose.
- Telegram bot token от [@BotFather](https://t.me/BotFather).
- Ваш Telegram user id.
- Xiaomi аккаунт, в котором видны данные Xiaomi Fitness.

## Быстрый запуск

1. Скопируйте пример секретов:

```sh
cp secrets.env.example secrets.env
```

2. Заполните минимум эти переменные:

```env
TELEGRAM_BOT_TOKEN=123456:replace-me
TELEGRAM_ALLOWED_USER_ID=123456789
```

3. Запустите сервис:

```sh
docker compose up -d --build
docker compose logs -f fitness-bot
```

4. Откройте своего Telegram-бота и отправьте `/start`.

5. Бот покажет кнопку входа в Xiaomi. Подтвердите вход по ссылке/QR. После этого бот сохранит `data/token_<telegram_user_id>.json`, запустит первую синхронизацию и откроет главное меню.

## Настройки

Основные переменные лежат в `secrets.env`:

```env
TELEGRAM_BOT_TOKEN=123456:replace-me
TELEGRAM_ALLOWED_USER_ID=123456789
SYNC_INTERVAL=900
QUERY_DURATION=2
ENABLE_FDS_SLEEP_DETAILS=true
```

- `TELEGRAM_BOT_TOKEN` - token вашего Telegram-бота.
- `TELEGRAM_ALLOWED_USER_ID` - единственный Telegram user id, которому разрешен доступ.
- `SYNC_INTERVAL` - интервал фоновой синхронизации в секундах. `900` = 15 минут.
- `QUERY_DURATION` - сколько последних дней запрашивать при sync.
- `ENABLE_FDS_SLEEP_DETAILS` - пробовать ли загружать детальные ночные данные FDS.

Пути к базе и статусу уже заданы в `compose.yaml`. Если запускаете без Docker, смотрите `secrets.env.example`.

## Где лежат данные

Runtime-файлы создаются в `./data`:

- `token_<telegram_user_id>.json` - Xiaomi auth token, секретный файл;
- `miband_<telegram_user_id>.db` - SQLite-база с health-данными;
- `status_<telegram_user_id>.json` - последний статус синхронизации;
- `fitness_bot_state.db` - служебное состояние Telegram-меню;
- `sync_<telegram_user_id>.lock` - lock-файл синхронизации.

Не коммитьте `secrets.env`, `data/`, `*.db`, `token*.json` и `status*.json`. Эти файлы уже добавлены в `.gitignore`.

## Команды бота

- `/start` - открыть меню или начать вход в Xiaomi.
- `/sync` - запустить ручную синхронизацию.
- `/status` - показать состояние локальной базы.

Основное управление происходит кнопками в Telegram-меню.

## Экспорт CSV

В меню есть экспорт данных. Бот собирает ZIP с CSV-таблицами и отправляет его в Telegram.

Помните: ZIP с health-данными уходит через инфраструктуру Telegram. Не отправляйте экспорт в чужие чаты и не храните его там, где доступ есть у других людей.

## Локальная разработка

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt -e mi-fitness-python
.venv/bin/python -m py_compile fitness_bot.py miband_sync.py $(find miband_tracker -name '*.py' | sort)
.venv/bin/python -m pytest
.venv/bin/python -m pytest mi-fitness-python/tests/unit
.venv/bin/ruff check .
.venv/bin/python -m pip check
```

Entrypoints сохранены для Docker и локального запуска:

```sh
python -u miband_sync.py
python -u fitness_bot.py
```

Если проект установлен как Python package, доступны console scripts:

```sh
miband-sync
miband-fitness-bot
```

## Troubleshooting

**Бот не отвечает.**
Проверьте `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_ID` и логи:

```sh
docker compose logs -f fitness-bot
```

**Синхронизация пишет, что token не найден.**
Откройте бота в Telegram, отправьте `/start` и пройдите Xiaomi login flow.

**Token истек.**
В меню запустите повторный вход в Xiaomi. Старый token можно удалить из `data/`.

**Данных мало или нет SpO2/деталей сна.**
Проверьте, что Xiaomi Fitness реально показывает эти данные. Часть данных зависит от модели браслета, настроек шаринга и доступности неофициального API.

**После обновления Xiaomi все сломалось.**
Это ожидаемый риск reverse-engineering проекта. Проверьте issues/README и логи, затем обновите код или временно отключите проблемную часть.

## Лицензия и vendored SDK

Проект распространяется под GNU GPL v3.0 or later. Полный текст лицензии лежит в [LICENSE](LICENSE).

SDK `mi-fitness-python` хранится в репозитории как vendored source copy и остается под своей GNU GPL v3.0 лицензией: [mi-fitness-python/LICENSE](mi-fitness-python/LICENSE). Подробности о происхождении и политике обновления описаны в [VENDORED.md](VENDORED.md).
