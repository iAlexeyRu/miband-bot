@echo off
chcp 65001 >nul
setlocal EnableExtensions

set "AUTO_START=0"
if /i "%~1"=="--start" set "AUTO_START=1"
if /i "%MIBAND_BOT_AUTO_START%"=="1" set "AUTO_START=1"
cls

echo.
echo   miband-bot
echo.

:CHOOSE_MODE
if "%AUTO_START%"=="1" if exist secrets.env goto MODE_PYTHON
set "install_mode=1"
set /p "install_mode=  [1] Python (recommended)  [2] Docker  Choice [1]: "
if "%install_mode%"=="1" goto MODE_PYTHON
if "%install_mode%"=="2" goto MODE_DOCKER
goto CHOOSE_MODE

:MODE_DOCKER
where docker >nul 2>nul
if errorlevel 1 goto DOCKER_MISSING
docker info >nul 2>nul
if errorlevel 1 goto DOCKER_NOT_RUNNING
echo   OK Docker is ready
set "DOCKER_ACTIVE=1"
goto SETUP_ENV

:DOCKER_MISSING
echo   ERROR Docker was not found. Install Docker Desktop.
pause
exit /b 1

:DOCKER_NOT_RUNNING
echo   ERROR Docker is not running. Start Docker Desktop and try again.
pause
exit /b 1

:MODE_PYTHON
call :FIND_PYTHON
if defined PYTHON_CMD goto PYTHON_OK

echo   ERROR Python 3.11+ was not found: https://www.python.org/downloads/
echo.
set "install_python=y"
set /p "install_python=  Install Python 3.11 automatically? [Y/n]: "
if /i not "%install_python%"=="y" goto PYTHON_INSTALL_DECLINED

echo   Downloading Python 3.11.9...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile 'python_installer.exe'"
if errorlevel 1 goto PYTHON_DOWNLOAD_FAILED

echo   Installing Python...
python_installer.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
if errorlevel 1 goto PYTHON_INSTALL_FAILED
del python_installer.exe >nul 2>nul
set "PATH=%LocalAppData%\Programs\Python\Python311;%LocalAppData%\Programs\Python\Python311\Scripts;%PATH%"
set "PYTHON_CMD=python"
%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto PYTHON_INSTALL_FAILED
goto PYTHON_OK

:PYTHON_INSTALL_DECLINED
echo   Install Python manually and run setup.bat again.
pause
exit /b 1

:PYTHON_DOWNLOAD_FAILED
echo   ERROR Could not download Python installer.
pause
exit /b 1

:PYTHON_INSTALL_FAILED
echo   ERROR Could not install Python.
pause
exit /b 1

:PYTHON_OK
echo   OK Python is ready: %PYTHON_CMD%
set "DOCKER_ACTIVE=0"
goto SETUP_ENV

:FIND_PYTHON
set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    py -3.13 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3.13" & exit /b 0
    py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3.12" & exit /b 0
    py -3.11 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3.11" & exit /b 0
)
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python" & exit /b 0
)
where python3 >nul 2>nul
if not errorlevel 1 (
    python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python3" & exit /b 0
)
exit /b 0

:SETUP_ENV
echo.
if not exist secrets.env goto INPUT_ENV_VALUES
if "%AUTO_START%"=="1" goto LAUNCH_PHASE
set "overwrite_env=n"
set /p "overwrite_env=  Config already exists. Reconfigure? [y/N]: "
if /i not "%overwrite_env%"=="y" goto LAUNCH_PHASE

:INPUT_ENV_VALUES
echo.
echo   Telegram bot token from @BotFather:

:INPUT_TOKEN
set "bot_token="
set /p "bot_token=  Token: "
if "%bot_token%"=="" goto TOKEN_EMPTY
echo %bot_token% | find ":" >nul 2>nul
if errorlevel 1 goto TOKEN_INVALID
goto TOKEN_OK

:TOKEN_EMPTY
echo   Token cannot be empty.
goto INPUT_TOKEN

:TOKEN_INVALID
echo   Invalid token format. It must contain a colon.
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
echo   OK Config saved

:LAUNCH_PHASE
echo.
if not "%DOCKER_ACTIVE%"=="1" goto PYTHON_LAUNCH

:DOCKER_LAUNCH
set "launch_now=y"
set /p "launch_now=  Start in Docker now? [Y/n]: "
if /i not "%launch_now%"=="y" goto DOCKER_MANUAL
docker compose up -d --build
if errorlevel 1 goto DOCKER_LAUNCH_FAILED
echo.
echo   OK Bot started in Docker. Send /start in Telegram.
echo   Logs: docker compose logs -f fitness-bot
goto END_LAUNCH

:DOCKER_MANUAL
echo   Manual start: docker compose up -d --build
goto END_LAUNCH

:DOCKER_LAUNCH_FAILED
echo   ERROR Docker startup failed.
goto END_LAUNCH

:PYTHON_LAUNCH
echo   Preparing Python environment...
if not exist .venv (
    %PYTHON_CMD% -m venv .venv >nul 2>nul
    if errorlevel 1 goto VENV_FAILED
)
call .venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel > pip_install.log 2>&1
if errorlevel 1 goto PIP_INSTALL_FAILED
python -m pip install -r requirements.txt -e mi-fitness-python >> pip_install.log 2>&1
if errorlevel 1 goto PIP_INSTALL_FAILED
del pip_install.log >nul 2>nul
echo   OK Dependencies installed
call :WRITE_RUN_LOCAL
if errorlevel 1 goto RUN_LOCAL_FAILED

if "%AUTO_START%"=="1" goto RUN_LOCAL_NOW

echo.
set "launch_now=y"
set /p "launch_now=  Start bot now? [Y/n]: "
if /i "%launch_now%"=="y" call run_local.bat
goto END_LAUNCH

:VENV_FAILED
echo   ERROR Could not create .venv.
pause
exit /b 1

:PIP_INSTALL_FAILED
echo   ERROR Dependency installation failed:
type pip_install.log
del pip_install.log >nul 2>nul
pause
exit /b 1

:RUN_LOCAL_FAILED
echo   ERROR Could not create run_local.bat.
pause
exit /b 1

:WRITE_RUN_LOCAL
>run_local.bat echo @echo off
>>run_local.bat echo chcp 65001 ^>nul
>>run_local.bat echo cd /d "%%~dp0"
>>run_local.bat echo if not exist .venv ^(
>>run_local.bat echo     echo   ERROR .venv was not found. Run setup.bat again.
>>run_local.bat echo     pause
>>run_local.bat echo     exit /b 1
>>run_local.bat echo ^)
>>run_local.bat echo if not exist run.py ^(
>>run_local.bat echo     echo   ERROR run.py was not found. Update project and run setup.bat again.
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
>>run_local.bat echo echo   OK Bot started. Keep this window open.
>>run_local.bat echo echo   Logs: data\bot.log / data\sync.log
>>run_local.bat echo echo.
>>run_local.bat echo python -u run.py
>>run_local.bat echo echo.
>>run_local.bat echo echo   Bot stopped. You can close this window.
>>run_local.bat echo echo.
>>run_local.bat echo pause
exit /b 0

:RUN_LOCAL_NOW
call run_local.bat

:END_LAUNCH
echo.
pause
endlocal
