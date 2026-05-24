#!/usr/bin/env bash

# ==============================================================================
# miband-bot Smart Setup Script for macOS / Linux
# ==============================================================================

# Цвета для вывода в консоль
RED='\033[0;31m'
# Приятный зеленый
GREEN='\033[0;32m'
# Насыщенный желтый
YELLOW='\033[1;33m'
# Глубокий синий
BLUE='\033[0;34m'
# Пурпурный
MAGENTA='\033[0;35m'
# Серый / обычный
NC='\033[0;37m'
BOLD='\033[1m'

clear
echo -e "${BLUE}${BOLD}======================================================================"
echo -e "                 🚀 УМНЫЙ ЗАПУСК И НАСТРОЙКА miband-bot 🚀"
echo -e "======================================================================${NC}"
echo -e "Этот скрипт поможет вам быстро развернуть личного Telegram-бота"
echo -e "для сбора данных Xiaomi Fitness / Mi Band."
echo ""

# ------------------------------------------------------------------------------
# Шаг 1. Выбор метода установки
# ------------------------------------------------------------------------------
echo -e "${BOLD}Как вы хотите запустить бота?${NC}"
echo -e "  ${BOLD}1)${NC} ${GREEN}Напрямую на Python${NC} (Рекомендуется. Потребляет минимум памяти)"
echo -e "  ${BOLD}2)${NC} ${MAGENTA}В Docker контейнерах${NC} (Всё работает в фоне, легко управлять)"
echo ""

while true; do
    read -p "Выберите вариант (1 или 2) [1]: " install_mode
    if [ -z "$install_mode" ]; then
        install_mode="1"
    fi
    if [ "$install_mode" = "1" ] || [ "$install_mode" = "2" ]; then
        break
    else
        echo -e "${RED}Неверный ввод. Пожалуйста, введите 1 или 2.${NC}"
    fi
done
echo ""

# ------------------------------------------------------------------------------
# Шаг 2. Проверка требований выбранного режима
# ------------------------------------------------------------------------------
if [ "$install_mode" = "2" ]; then
    echo -e "${BOLD}[1/3] Проверка окружения Docker...${NC}"
    
    DOCKER_AVAILABLE=true
    DOCKER_RUNNING=true

    if ! command -v docker &> /dev/null; then
        DOCKER_AVAILABLE=false
    fi

    if [ "$DOCKER_AVAILABLE" = true ]; then
        if ! docker info &> /dev/null; then
            DOCKER_RUNNING=false
        fi
    fi

    if [ "$DOCKER_AVAILABLE" = false ]; then
        echo -e "${RED}❌ Docker CLI не найден в вашей системе.${NC}"
        echo -e "Пожалуйста, установите Docker движок перед продолжением:"
        echo -e "  - ${BLUE}Linux:${NC} Установите 'docker' и 'docker-compose-plugin' через менеджер пакетов."
        echo -e "  - ${BLUE}macOS:${NC} Запустите легкий ${BOLD}Colima${NC} ('brew install colima') или Docker Desktop."
        echo -e "Или вернитесь назад и выберите вариант запуска напрямую на Python."
        exit 1
    elif [ "$DOCKER_RUNNING" = false ]; then
        echo -e "${RED}❌ Служба Docker установлена, но сейчас не запущена.${NC}"
        echo -e "Пожалуйста, запустите Docker-демон (например, 'colima start' на Mac"
        echo -e "или 'sudo systemctl start docker' на Linux) и перезапустите скрипт."
        exit 1
    else
        echo -e "${GREEN}✓ Движок Docker активен и готов к работе!${NC}"
        if docker compose version &> /dev/null; then
            COMPOSE_CMD="docker compose"
        elif command -v docker-compose &> /dev/null; then
            COMPOSE_CMD="docker-compose"
        else
            echo -e "${YELLOW}⚠️  Команда 'docker compose' не найдена. Убедитесь, что плагин Compose установлен.${NC}"
        fi
    fi

else
    echo -e "${BOLD}[1/3] Проверка окружения Python...${NC}"
    
    PYTHON_CMD=""
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        # Проверяем версию python
        py_ver=$(python -c 'import sys; print(sys.version_info[0])' 2>/dev/null)
        if [ "$py_ver" = "3" ]; then
            PYTHON_CMD="python"
        fi
    fi

    if [ -z "$PYTHON_CMD" ]; then
        echo -e "${RED}❌ Python 3 не найден в вашей системе.${NC}"
        echo -e "Пожалуйста, установите Python версии 3.10 или выше."
        exit 1
    else
        py_full_ver=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
        echo -e "${GREEN}✓ Найден Python $py_full_ver!${NC}"
    fi
fi
echo ""

# ------------------------------------------------------------------------------
# Шаг 3. Настройка secrets.env
# ------------------------------------------------------------------------------
echo -e "${BOLD}[2/3] Конфигурация параметров бота (secrets.env)...${NC}"

ENV_FILE="secrets.env"
SETUP_CONFIG=true

if [ -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}Файл конфигурации secrets.env уже существует.${NC}"
    read -p "Хотите перезаписать его и настроить параметры заново? [y/N]: " overwrite_env
    if [ -z "$overwrite_env" ]; then
        overwrite_env="n"
    fi
    if [[ ! $overwrite_env =~ ^[Yy]$ ]]; then
        echo -e "${GREEN}✓ Сохраняем существующий secrets.env.${NC}"
        SETUP_CONFIG=false
    fi
fi

if [ "$SETUP_CONFIG" = true ]; then
    echo -e "Сейчас мы настроим основные параметры безопасности."
    echo ""
    
    # Ввод токена бота с подробной инструкцией
    while true; do
        echo -e "🔑 ${BOLD}Шаг 1. Получение Telegram Bot Token${NC}"
        echo -e "Для работы бота необходим токен. Его можно получить бесплатно за 1 минуту:"
        echo -e "  1. Откройте Telegram и перейдите к официальному боту ${BLUE}@BotFather${NC}."
        echo -e "  2. Отправьте ему команду ${BOLD}/newbot${NC}."
        echo -e "  3. Введите название для бота (например, ${YELLOW}Мой Mi Band Бот${NC})."
        echo -e "  4. Введите уникальное имя пользователя (username) на английском,"
        echo -e "     заканчивающееся на ${BOLD}bot${NC} (например, ${YELLOW}my_miband_sync_bot${NC})."
        echo -e "  5. Скопируйте полученный токен (выглядит как ${BLUE}123456789:ABC-DEF...${NC})."
        echo ""
        read -p "Вставьте ваш Telegram Bot Token: " bot_token
        
        if [ -n "$bot_token" ] && [[ "$bot_token" == *":"* ]]; then
            break
        else
            echo -e "${RED}Ошибка: Токен должен быть непустым и содержать символ ':'${NC}\n"
        fi
    done
    echo ""

    echo -e "🔒 ${BOLD}Шаг 2. Автоматическая привязка владельца (Whitelist ID)${NC}"
    echo -e "Вам ${BOLD}НЕ НУЖНО${NC} вручную искать и вводить ваш Telegram User ID!"
    echo -e "Сразу после запуска бота откройте его в Telegram и отправьте команду ${BOLD}/start${NC}."
    echo -e "Бот автоматически распознает ваш ID, запишет его в белый список"
    echo -e "и заблокирует доступ для всех остальных пользователей."
    echo ""

    # Создание secrets.env
    cat << EOF > "$ENV_FILE"
# ==============================================================================
# Конфигурация secrets.env для miband-bot
# ==============================================================================

# Токен вашего Telegram-бота (полученный от @BotFather)
TELEGRAM_BOT_TOKEN=$bot_token

# Единственный разрешенный Telegram User ID (для безопасности данных)
# Оставьте пустым - бот автоматически привяжется к первому, кто напишет /start!
TELEGRAM_ALLOWED_USER_ID=

# Интервал фоновой синхронизации данных из облака Xiaomi Fitness (в секундах)
SYNC_INTERVAL=900

# Глубина запроса при автоматической синхронизации (в днях)
QUERY_DURATION=2

# Загружать детальные ночные данные о сне (FDS)
ENABLE_FDS_SLEEP_DETAILS=true
EOF

    chmod 600 "$ENV_FILE" 2>/dev/null
    echo -e "${GREEN}✓ Файл secrets.env успешно создан!${NC}"
fi
echo ""

# ------------------------------------------------------------------------------
# Шаг 4. Установка зависимостей и запуск
# ------------------------------------------------------------------------------
echo -e "${BOLD}[3/3] Подготовка среды выполнения...${NC}"

if [ "$install_mode" = "2" ]; then
    # Режим Docker
    read -p "Хотите запустить miband-bot в Docker прямо сейчас? [Y/n]: " launch_now
    if [ -z "$launch_now" ]; then
        launch_now="y"
    fi
    if [[ $launch_now =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}Сборка и старт контейнеров в фоне...${NC}"
        if $COMPOSE_CMD up -d --build; then
            echo ""
            echo -e "${GREEN}${BOLD}======================================================================"
            echo -e "        🎉 miband-bot УСПЕШНО НАСТРОЕН И ЗАПУЩЕН В DOCKER! 🎉"
            echo -e "======================================================================${NC}"
            echo -e "Следующие шаги:"
            echo -e "1. Откройте вашего бота в Telegram и отправьте ${BOLD}/start${NC}."
            echo -e "2. Войдите в аккаунт Xiaomi по ссылке или QR-коду."
            echo ""
            echo -e "Команда для просмотра логов:"
            echo -e "  ${BLUE}$COMPOSE_CMD logs -f fitness-bot${NC}"
            echo -e "Команда для остановки бота:"
            echo -e "  ${BLUE}$COMPOSE_CMD down${NC}"
            echo "======================================================================"
        else
            echo -e "${RED}Ошибка при запуске Docker Compose.${NC}"
        fi
    else
        echo -e "${YELLOW}Бот настроен, но не запущен.${NC}"
        echo -e "Запустите вручную командой: ${BLUE}$COMPOSE_CMD up -d --build${NC}"
    fi

else
    # Режим чистого Python
    echo -e "Создаем виртуальное окружение .venv..."
    
    if [ ! -d ".venv" ]; then
        if ! $PYTHON_CMD -m venv .venv; then
            echo -e "${RED}❌ Не удалось создать виртуальное окружение .venv.${NC}"
            echo -e "В вашей системе (вероятно, Debian/Ubuntu) отсутствует пакет для виртуальных сред."
            echo -e "Пожалуйста, установите его с помощью команды:"
            echo -e "  ${BOLD}sudo apt update && sudo apt install -y python3-venv${NC}"
            exit 1
        fi
    fi
    
    source .venv/bin/activate
    echo -e "${BLUE}Установка библиотек из requirements.txt и mi-fitness-python...${NC}"
    if pip install -r requirements.txt -e mi-fitness-python; then
        echo -e "${GREEN}✓ Все зависимости успешно установлены!${NC}"
    else
        echo -e "${RED}❌ Не удалось установить зависимости. Проверьте подключение к сети.${NC}"
        exit 1
    fi
    
    # Создаем удобный скрипт для локального запуска
    LAUNCHER_FILE="run_local.sh"
    cat << 'EOF' > "$LAUNCHER_FILE"
#!/usr/bin/env bash
# ==============================================================================
# Скрипт локального запуска miband-bot (без Docker)
# ==============================================================================
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Ошибка: Папка .venv не найдена. Запустите setup.sh заново."
    exit 1
fi

# Загружаем переменные из secrets.env в окружение текущего процесса
if [ -f secrets.env ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        # Очищаем пробелы и переносы
        line=$(echo "$line" | xargs 2>/dev/null || echo "$line")
        # Игнорируем комментарии и пустые строки
        if [[ ! "$line" =~ ^# ]] && [[ ! -z "$line" ]]; then
            export "$line"
        fi
    done < secrets.env
fi

# Настраиваем локальные пути к папке data (чтобы не писать в глобальные пути /opt)
export DATA_DIR="./data"
export DB_PATH="./data/miband_${TELEGRAM_ALLOWED_USER_ID}.db"
export STATUS_PATH="./data/status_${TELEGRAM_ALLOWED_USER_ID}.json"
export BOT_STATE_DB_PATH="./data/fitness_bot_state.db"

source .venv/bin/activate
echo "=== Запуск miband-bot локально на Python ==="
echo "Нажмите Ctrl+C для завершения работы обоих процессов."
echo ""

# При завершении скрипта (Ctrl+C) убиваем все запущенные нами фоновые задачи
trap "kill 0" EXIT

# Запускаем фоновый синхронизатор и сам Telegram бот параллельно
python -u miband_sync.py &
python -u fitness_bot.py &

# Ожидаем завершения
wait
EOF
    chmod +x "$LAUNCHER_FILE"
    echo -e "${GREEN}✓ Создан удобный скрипт запуска: ${BOLD}./run_local.sh${NC}"
    echo ""
    
    read -p "Хотите запустить бота локально прямо сейчас? [Y/n]: " launch_now
    if [ -z "$launch_now" ]; then
        launch_now="y"
    fi
    if [[ $launch_now =~ ^[Yy]$ ]]; then
        ./run_local.sh
    else
        echo -e "${YELLOW}Бот готов к запуску.${NC}"
        echo -e "Запускайте его в любое время с помощью скрипта:"
        echo -e "  ${BLUE}./run_local.sh${NC}"
    fi
fi

echo ""
