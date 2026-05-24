#!/bin/bash
# Скрипт бесшовной установки miband-bot для macOS / Linux
set -e

# Цвета для вывода в консоль
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BLUE}=== Установка miband-bot ===${NC}"

# 1. Проверяем зависимости (curl или wget, и unzip)
if ! command -v curl &> /dev/null && ! command -v wget &> /dev/null; then
    echo -e "${RED}Ошибка: Для загрузки требуется утилита curl или wget.${NC}"
    exit 1
fi

if ! command -v unzip &> /dev/null; then
    echo -e "${RED}Ошибка: Для установки требуется утилита unzip (установите ее через ваш менеджер пакетов).${NC}"
    exit 1
fi

# 2. Создаем или проверяем директорию установки
INSTALL_DIR="miband-bot"
if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}Папка '$INSTALL_DIR' уже существует в этой директории.${NC}"
    read -p "Хотите перезаписать файлы проекта внутри нее? [Y/n]: " overwrite_confirm </dev/tty
    if [ -z "$overwrite_confirm" ]; then
        overwrite_confirm="y"
    fi
    if [[ ! "$overwrite_confirm" =~ ^[Yy]$ ]]; then
        echo -e "${RED}Установка отменена.${NC}"
        exit 1
    fi
else
    mkdir -p "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# 3. Скачиваем ZIP-архив с GitHub
echo "Загрузка последней версии проекта с GitHub..."
ZIP_URL="https://github.com/iAlexeyRu/miband-bot/archive/refs/heads/main.zip"
TEMP_ZIP="miband-bot-temp.zip"

if command -v curl &> /dev/null; then
    curl -sSL -o "$TEMP_ZIP" "$ZIP_URL"
else
    wget -q -O "$TEMP_ZIP" "$ZIP_URL"
fi

# 4. Распаковываем и очищаем временные файлы
echo "Распаковка файлов проекта..."
unzip -q -o "$TEMP_ZIP"
rm "$TEMP_ZIP"

# 5. Копируем файлы из вложенной папки и удаляем ее
cp -r miband-bot-main/. .
rm -rf miband-bot-main

# 6. Запускаем интерактивный setup.sh
chmod +x setup.sh
echo -e "${GREEN}✓ Проект успешно загружен! Запускаем интерактивную настройку...${NC}"
echo ""

# Перенаправляем stdin на /dev/tty, чтобы интерактивные read-промпты работали корректно при запуске через пайп
./setup.sh </dev/tty
