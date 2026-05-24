#!/usr/bin/env bash
# miband-bot setup for macOS / Linux

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

ok()  { echo -e "  ${GREEN}✓${NC} $1"; }
err() { echo -e "  ${RED}❌${NC} $1"; }

clear
echo ""
echo "  miband-bot"
echo ""

# --- Выбор режима ---
while true; do
    read -p "  [1] Python (рек.)  [2] Docker  Выбор [1]: " install_mode
    install_mode="${install_mode:-1}"
    [ "$install_mode" = "1" ] || [ "$install_mode" = "2" ] && break
done
echo ""

# --- Проверка требований ---
if [ "$install_mode" = "2" ]; then
    if ! command -v docker &> /dev/null; then
        err "Docker не найден. Установите Docker Desktop или Colima (brew install colima)."
        exit 1
    fi
    if ! docker info &> /dev/null; then
        err "Docker не запущен. Запустите демон (colima start / Docker Desktop) и повторите."
        exit 1
    fi
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        err "Плагин docker compose не найден."
        exit 1
    fi
    ok "Docker готов"
    DOCKER_MODE=true
else
    PYTHON_CMD=""
    for cmd in python3 python; do
        if command -v "$cmd" &> /dev/null; then
            ver=$("$cmd" -c 'import sys; print(sys.version_info[0])' 2>/dev/null)
            [ "$ver" = "3" ] && PYTHON_CMD="$cmd" && break
        fi
    done
    if [ -z "$PYTHON_CMD" ]; then
        err "Python 3 не найден. Установите: https://www.python.org/downloads/"
        exit 1
    fi
    ok "Python готов ($PYTHON_CMD)"
    DOCKER_MODE=false
fi

# --- Конфигурация ---
echo ""
if [ -f secrets.env ]; then
    read -p "  Конфигурация уже есть. Перенастроить? [y/N]: " overwrite < /dev/tty
    if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
        : # skip to launch
    else
        rm -f secrets.env
    fi
fi

if [ ! -f secrets.env ]; then
    echo ""
    echo "  Токен бота от @BotFather в Telegram:"
    while true; do
        read -p "  > " bot_token < /dev/tty
        [ -z "$bot_token" ] && echo "  Токен не может быть пустым." && continue
        [[ "$bot_token" == *":"* ]] && break
        echo "  Неверный формат (должен содержать ':')."
    done

    {
        echo "# miband-bot"
        echo "TELEGRAM_BOT_TOKEN=$bot_token"
        echo "TELEGRAM_ALLOWED_USER_ID="
        echo "SYNC_INTERVAL=900"
        echo "QUERY_DURATION=2"
        echo "ENABLE_FDS_SLEEP_DETAILS=true"
    } > secrets.env
    ok "Конфигурация сохранена"
fi

# --- Запуск ---
echo ""
if [ "$DOCKER_MODE" = true ]; then
    read -p "  Запустить в Docker сейчас? [Y/n]: " launch_now < /dev/tty
    launch_now="${launch_now:-y}"
    if [[ ! "$launch_now" =~ ^[Yy]$ ]]; then
        echo "  Запуск вручную: $COMPOSE_CMD up -d --build"
        exit 0
    fi
    $COMPOSE_CMD up -d --build
    if [ $? -eq 0 ]; then
        echo ""
        ok "Бот запущен в Docker. Отправьте /start в Telegram."
        echo "  Логи: $COMPOSE_CMD logs -f fitness-bot"
    else
        err "Ошибка запуска Docker."
    fi
    exit 0
fi

# Python режим
echo "  Подготовка..."
if [ ! -d ".venv" ]; then
    if ! $PYTHON_CMD -m venv .venv; then
        err "Не удалось создать .venv. На Debian/Ubuntu: sudo apt install -y python3-venv"
        exit 1
    fi
fi

source .venv/bin/activate
if pip install -r requirements.txt -e mi-fitness-python > pip_install.log 2>&1; then
    rm -f pip_install.log
    ok "Готово"
else
    err "Ошибка установки зависимостей:"
    cat pip_install.log
    rm -f pip_install.log
    exit 1
fi

# Генерируем run_local.sh — логи Python уходят в файлы
cat << 'EOF' > run_local.sh
#!/usr/bin/env bash
# Запуск miband-bot (Python читает secrets.env автоматически)
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "  ❌ .venv не найдена. Запустите setup.sh заново."
    exit 1
fi

if [ ! -f "run.py" ]; then
    echo "  ❌ run.py не найден. Обновите проект и запустите setup.sh заново."
    exit 1
fi

source .venv/bin/activate
mkdir -p data
clear
echo ""
echo "  miband-bot"
echo ""
echo "  ✓ Бот запущен. Не закрывайте это окно."
echo "  Логи: data/bot.log  /  data/sync.log"
echo ""

python -u run.py
echo ""
echo "  Бот остановлен. Можно закрыть окно."
echo ""
EOF
chmod +x run_local.sh
ok "Создан скрипт запуска: ./run_local.sh"
echo ""

read -p "  Запустить бота сейчас? [Y/n]: " launch_now < /dev/tty
launch_now="${launch_now:-y}"
if [[ "$launch_now" =~ ^[Yy]$ ]]; then
    ./run_local.sh
fi
