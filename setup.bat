@echo off
chcp 65001 > nul
set AUTO_START=0
if /i "%~1"=="--start" set AUTO_START=1
if /i "%MIBAND_BOT_AUTO_START%"=="1" set AUTO_START=1
cls

echo.
echo   miband-bot
echo.

:CHOOSE_MODE
if "%AUTO_START%"=="1" if exist secrets.env goto MODE_PYTHON
set install_mode=1
set /p install_mode="  [1] Python (рек.)  [2] Docker  Выбор [1]: "
if "%install_mode%"=="1" goto MODE_PYTHON
if "%install_mode%"=="2" goto MODE_DOCKER
goto CHOOSE_MODE

:MODE_DOCKER
where docker >nul 2>nul
if errorlevel 1 ( echo   ! Docker не найден. Установите Docker Desktop. & pause & exit /b 1 )
docker info >nul 2>nul
if errorlevel 1 ( echo   ! Docker не запущен. Запустите Docker Desktop. & pause & exit /b 1 )
echo   OK Docker готов
set DOCKER_ACTIVE=1
goto SETUP_ENV

:MODE_PYTHON
python --version >nul 2>nul
if not errorlevel 1 goto PYTHON_OK

echo   ! Python не найден: https://www.python.org/downloads/
echo.
set install_python=y
set /p install_python="  Установить Python 3.11 автоматически? [Y/n]: "
if /i not "%install_python%"=="y" ( echo   Установите Python вручную и повторите. & pause & exit /b 1 )

echo   Скачивание Python 3.11.9...
powershell -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile 'python_installer.exe'"
echo   Установка...
python_installer.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
del python_installer.exe
set "PATH=%LocalAppData%\Programs\Python\Python311;%LocalAppData%\Programs\Python\Python311\Scripts;%PATH%"
python --version >nul 2>nul
if errorlevel 1 ( echo   ! Не удалось установить Python. & pause & exit /b 1 )

:PYTHON_OK
echo   OK Python готов
set DOCKER_ACTIVE=0
goto SETUP_ENV

:SETUP_ENV
echo.
if not exist secrets.env goto INPUT_ENV_VALUES
if "%AUTO_START%"=="1" goto LAUNCH_PHASE
set overwrite_env=n
set /p overwrite_env="  Конфигурация уже есть. Перенастроить? [y/N]: "
if /i not "%overwrite_env%"=="y" goto LAUNCH_PHASE

:INPUT_ENV_VALUES
echo.
echo   Токен бота от @BotFather в Telegram:

:INPUT_TOKEN
set bot_token=
set /p bot_token="  Токен: "
if "%bot_token%"=="" goto TOKEN_EMPTY
echo %bot_token% | find ":" >nul 2>nul
if errorlevel 1 goto TOKEN_INVALID
goto TOKEN_OK

:TOKEN_EMPTY
echo   Токен не может быть пустым.
goto INPUT_TOKEN

:TOKEN_INVALID
echo   Неверный формат - токен должен содержать двоеточие.
goto INPUT_TOKEN

:TOKEN_OK
(
echo # miband-bot config
echo TELEGRAM_BOT_TOKEN=%bot_token%
echo TELEGRAM_ALLOWED_USER_ID=
echo SYNC_INTERVAL=900
echo QUERY_DURATION=2
echo ENABLE_FDS_SLEEP_DETAILS=true
) > secrets.env
echo   OK Конфигурация сохранена

:LAUNCH_PHASE
echo.
if not "%DOCKER_ACTIVE%"=="1" goto PYTHON_LAUNCH

:DOCKER_LAUNCH
set launch_now=y
set /p launch_now="  Запустить в Docker сейчас? [Y/n]: "
if /i not "%launch_now%"=="y" ( echo   Запуск вручную: docker compose up -d --build & goto END_LAUNCH )
docker compose up -d --build
if not errorlevel 1 (
    echo.
    echo   OK Бот запущен в Docker. Отправьте /start в Telegram.
    echo   Логи: docker compose logs -f fitness-bot
) else (
    echo   ! Ошибка запуска Docker.
)
goto END_LAUNCH

:PYTHON_LAUNCH
echo   Подготовка...
if not exist .venv ( python -m venv .venv >nul 2>nul )
call .venv\Scripts\activate
pip install -r requirements.txt -e mi-fitness-python > pip_install.log 2>&1
if not errorlevel 1 (
    del pip_install.log >nul 2>nul
    echo   OK Готово
) else (
    echo   ! Ошибка установки зависимостей:
    type pip_install.log
    del pip_install.log >nul 2>nul
    pause & exit /b 1
)

>run_local.bat echo @echo off
>>run_local.bat echo chcp 65001 ^> nul
>>run_local.bat echo cd /d "%%~dp0"
>>run_local.bat echo if not exist .venv ^(
>>run_local.bat echo     echo   ! .venv не найдено. Запустите setup.bat заново.
>>run_local.bat echo     pause
>>run_local.bat echo     exit /b 1
>>run_local.bat echo ^)
>>run_local.bat echo if not exist run.py ^(
>>run_local.bat echo     echo   ! run.py не найден. Обновите проект и запустите setup.bat заново.
>>run_local.bat echo     pause
>>run_local.bat echo     exit /b 1
>>run_local.bat echo ^)
>>run_local.bat echo call .venv\Scripts\activate
>>run_local.bat echo set PYTHONUTF8=1
>>run_local.bat echo set PYTHONIOENCODING=utf-8
>>run_local.bat echo md data 2^>nul
>>run_local.bat echo cls
>>run_local.bat echo echo.
>>run_local.bat echo echo   miband-bot
>>run_local.bat echo echo.
>>run_local.bat echo echo   OK Бот запущен. Не закрывайте это окно.
>>run_local.bat echo echo   Логи: data\bot.log  /  data\sync.log
>>run_local.bat echo echo.
>>run_local.bat echo python -u run.py
>>run_local.bat echo echo.
>>run_local.bat echo echo   Бот остановлен. Можно закрыть окно.
>>run_local.bat echo echo.
>>run_local.bat echo pause

if "%AUTO_START%"=="1" goto RUN_LOCAL_NOW

echo.
set launch_now=y
set /p launch_now="  Запустить бота сейчас? [Y/n]: "
if /i "%launch_now%"=="y" ( call run_local.bat )
goto END_LAUNCH

:RUN_LOCAL_NOW
call run_local.bat

:END_LAUNCH
echo.
pause
