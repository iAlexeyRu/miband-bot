@echo off
:: ==============================================================================
:: miband-bot Smart Setup Script for Windows (100% Flat robust version)
:: ==============================================================================
chcp 65001 > nul
cls

echo ======================================================================
echo                  🚀 УМНЫЙ ЗАПУСК И НАСТРОЙКА miband-bot 🚀
echo ======================================================================
echo Этот скрипт поможет вам быстро развернуть личного Telegram-бота
echo для сбора данных Xiaomi Fitness / Mi Band.
echo.

:: ------------------------------------------------------------------------------
:: Шаг 1. Выбор метода установки
:: ------------------------------------------------------------------------------
echo Как вы хотите запустить бота?
echo   1] Напрямую на Python (Рекомендуется. Потребляет минимум памяти)
echo   2] В Docker контейнерах (Всё работает в фоне)
echo.

:CHOOSE_MODE
set install_mode=1
set /p install_mode="Выберите вариант (1 или 2) [1]: "
if "%install_mode%"=="1" goto MODE_PYTHON
if "%install_mode%"=="2" goto MODE_DOCKER
echo Неверный ввод. Пожалуйста, введите 1 или 2.
echo.
goto CHOOSE_MODE

:: ------------------------------------------------------------------------------
:: Шаг 2. Проверка требований
:: ------------------------------------------------------------------------------
:MODE_DOCKER
echo.
echo [1/3] Проверка окружения Docker...
where docker >nul 2>nul
if errorlevel 1 (
    echo ❌ Docker CLI не найден. Пожалуйста, установите Docker Desktop или настройте WSL 2.
    pause
    exit /b 1
)
docker info >nul 2>nul
if errorlevel 1 (
    echo ❌ Демон Docker не запущен. Пожалуйста, запустите Docker и перезапустите скрипт.
    pause
    exit /b 1
)
echo ✓ Движок Docker активен и готов к работе!
set DOCKER_ACTIVE=1
goto SETUP_ENV

:MODE_PYTHON
echo.
echo [1/3] Проверка окружения Python...
python --version >nul 2>nul
if not errorlevel 1 goto PYTHON_OK

echo ❌ Python не найден или не настроен в вашей системе.
echo Вы можете скачать его вручную по ссылке: https://www.python.org/downloads/
echo.
set install_python=y
set /p install_python="Хотите, чтобы я автоматически скачал и установил Python 3.11? [Y/n]: "
if /i not "%install_python%"=="y" (
    echo Установка отменена. Пожалуйста, установите Python вручную.
    pause
    exit /b 1
)

echo.
echo Скачивание установщика Python 3.11.9...
powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile 'python_installer.exe'"
echo Установка Python (это займет около минуты, пожалуйста, подождите)...
python_installer.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
del python_installer.exe

:: Добавляем установленный Python в PATH текущей сессии
set "PATH=%LocalAppData%\Programs\Python\Python311;%LocalAppData%\Programs\Python\Python311\Scripts;%PATH%"

python --version >nul 2>nul
if errorlevel 1 (
    echo ❌ Не удалось автоматически установить Python или добавить его в PATH.
    echo Пожалуйста, установите Python вручную по ссылке: https://www.python.org/downloads/
    pause
    exit /b 1
)

:PYTHON_OK
echo ✓ Python найден!
set DOCKER_ACTIVE=0
goto SETUP_ENV

:: ------------------------------------------------------------------------------
:: Шаг 3. Настройка secrets.env
:: ------------------------------------------------------------------------------
:SETUP_ENV
echo.
echo [2/3] Конфигурация параметров бота (secrets.env)...

if not exist secrets.env goto INPUT_ENV_VALUES
echo Файл конфигурации secrets.env уже существует.
set overwrite_env=n
set /p overwrite_env="Хотите перезаписать его и настроить заново? [y/N]: "
if /i not "%overwrite_env%"=="y" (
    echo ✓ Сохраняем существующий secrets.env.
    goto LAUNCH_PHASE
)

:INPUT_ENV_VALUES
echo.
echo Сейчас мы настроим основные параметры безопасности.
echo.

:INPUT_TOKEN
echo 🔑 Шаг 1. Получение Telegram Bot Token
echo Для работы бота необходим токен. Его можно получить бесплатно за 1 минуту:
echo   1. Откройте Telegram и перейдите к официальному боту @BotFather.
echo   2. Отправьте ему команду /newbot.
echo   3. Введите название для бота (например, Мой Mi Band Бот).
echo   4. Введите уникальное имя пользователя (username) на английском,
echo      заканчивающееся на bot (например, my_miband_sync_bot).
echo   5. Скопируйте полученный токен (выглядит как 123456789:ABC-DEF...).
echo.
set /p bot_token="Вставьте ваш Telegram Bot Token: "
if "%bot_token%"=="" (
    echo Ошибка: Токен не может быть пустым.
    echo.
    goto INPUT_TOKEN
)
echo %bot_token% | findstr /c:":" >nul
if errorlevel 1 (
    echo Ошибка: Токен должен содержать символ ":"
    echo.
    goto INPUT_TOKEN
)
echo.

echo 🔒 Шаг 2. Автоматическая привязка владельца (Whitelist ID)
echo Вам НЕ НУЖНО вручную искать и вводить ваш Telegram User ID!
echo Сразу после запуска бота откройте его в Telegram и отправьте команду /start.
echo Бот автоматически распознает ваш ID, запишет его в белый список
echo и заблокирует доступ для всех остальных пользователей.
echo.

:: Создание secrets.env (запись построчно во избежание багов парсера скобок)
echo # ============================================================================== > secrets.env
echo # Конфигурация secrets.env для miband-bot >> secrets.env
echo # ============================================================================== >> secrets.env
echo. >> secrets.env
echo # Токен вашего Telegram-бота (полученный от @BotFather) >> secrets.env
echo TELEGRAM_BOT_TOKEN=%bot_token% >> secrets.env
echo. >> secrets.env
echo # Единственный разрешенный Telegram User ID (для безопасности данных) >> secrets.env
echo # Оставьте пустым - бот автоматически привяжется к первому, кто напишет /start! >> secrets.env
echo TELEGRAM_ALLOWED_USER_ID= >> secrets.env
echo. >> secrets.env
echo # Интервал фоновой синхронизации данных из облака Xiaomi Fitness (в секундах) >> secrets.env
echo SYNC_INTERVAL=900 >> secrets.env
echo. >> secrets.env
echo # Глубина запроса при автоматической синхронизации (в днях) >> secrets.env
echo QUERY_DURATION=2 >> secrets.env
echo. >> secrets.env
echo # Загружать детальные ночные данные о сне (FDS) >> secrets.env
echo ENABLE_FDS_SLEEP_DETAILS=true >> secrets.env

echo ✓ Файл secrets.env успешно создан!
echo.

:: ------------------------------------------------------------------------------
:: Шаг 4. Установка зависимостей и запуск
:: ------------------------------------------------------------------------------
:LAUNCH_PHASE
echo [3/3] Подготовка среды выполнения...

if not "%DOCKER_ACTIVE%"=="1" goto PYTHON_LAUNCH

:DOCKER_LAUNCH
set launch_now=y
set /p launch_now="Хотите запустить miband-bot в Docker прямо сейчас? [Y/n]: "
if /i not "%launch_now%"=="y" (
    echo.
    echo   Бот настроен, но не запущен.
    echo   Запустите вручную командой: docker compose up -d --build
    goto END_LAUNCH
)
echo Сборка и запуск контейнеров...
docker compose up -d --build
if not errorlevel 1 (
    echo.
    echo ======================================================================
    echo         🎉 miband-bot УСПЕШНО НАСТРОЕН И ЗАПУЩЕН В DOCKER! 🎉
    echo ======================================================================
    echo Теперь откройте бота в Telegram и отправьте команду /start.
    echo.
    echo Логи:   docker compose logs -f fitness-bot
    echo Стоп:   docker compose down
    echo ======================================================================
) else (
    echo Ошибка при сборке или запуске Docker Compose.
)
goto END_LAUNCH

:PYTHON_LAUNCH
echo Создаем виртуальное окружение .venv и устанавливаем зависимости...
if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate
echo Установка библиотек...
pip install -r requirements.txt -e mi-fitness-python

:: Записываем рабочий запуск в run_local.bat построчно (полностью без скобочных блоков)
echo @echo off > run_local.bat
echo chcp 65001 ^> nul >> run_local.bat
echo cd /d "%%~dp0" >> run_local.bat
echo if not exist .venv ^( >> run_local.bat
echo     echo Ошибка: Виртуальное окружение .venv не найдено. Запустите setup.bat сначала. >> run_local.bat
echo     pause >> run_local.bat
echo     exit /b 1 >> run_local.bat
echo ^) >> run_local.bat
echo. >> run_local.bat
echo :: Загрузка переменных из secrets.env >> run_local.bat
echo if exist secrets.env ^( >> run_local.bat
echo     for /f "usebackq delims=" %%%%x in ^("secrets.env"^) do ^( >> run_local.bat
echo         echo %%%%x ^| findstr /r "^#" ^>nul >> run_local.bat
echo         if errorlevel 1 ^( >> run_local.bat
echo             set %%%%x >> run_local.bat
echo         ^) >> run_local.bat
echo     ^) >> run_local.bat
echo ^) >> run_local.bat
echo. >> run_local.bat
echo :: Настройка локальных путей к папке data >> run_local.bat
echo set DATA_DIR=.\data >> run_local.bat
echo set DB_PATH=.\data\miband_%%TELEGRAM_ALLOWED_USER_ID%%.db >> run_local.bat
echo set STATUS_PATH=.\data\status_%%TELEGRAM_ALLOWED_USER_ID%%.json >> run_local.bat
echo set BOT_STATE_DB_PATH=.\data\fitness_bot_state.db >> run_local.bat
echo. >> run_local.bat
echo call .venv\Scripts\activate >> run_local.bat
echo === Запуск miband-bot локально ^(без Docker^) === >> run_local.bat
echo Для завершения работы закройте это окно консоли. >> run_local.bat
echo. >> run_local.bat
echo Запуск синхронизатора и Telegram-бота... >> run_local.bat
echo. >> run_local.bat
echo [Запуск фонового синхронизатора...] >> run_local.bat
echo start /b python -u miband_sync.py >> run_local.bat
echo [Запуск бота...] >> run_local.bat
echo python -u fitness_bot.py >> run_local.bat

echo ✓ Создан удобный скрипт запуска: run_local.bat
echo.
set launch_now=y
set /p launch_now="Хотите запустить бота локально прямо сейчас? [Y/n]: "
if /i "%launch_now%"=="y" (
    call run_local.bat
)

:END_LAUNCH
echo.
pause
