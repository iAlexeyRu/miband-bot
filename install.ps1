# Отключаем показ прогресс-баров (скрывает спам при скачивании)
$ProgressPreference = 'SilentlyContinue'

# Кодировка UTF-8 для корректного вывода русских символов
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=== Установка miband-bot ===" -ForegroundColor Blue

function Test-ConfiguredInstall {
    param([string]$ProjectPath)

    $secretsPath = Join-Path $ProjectPath "secrets.env"
    if (-not (Test-Path -LiteralPath $secretsPath)) {
        return $false
    }

    try {
        return [bool](Select-String -LiteralPath $secretsPath -Pattern '^TELEGRAM_BOT_TOKEN=.+$' -Quiet)
    } catch {
        return $true
    }
}

# Проверяем, запущен ли скрипт в защищенной системной папке (например, System32 или C:\Windows)
if ($PWD.Path -like "*\system32*" -or $PWD.Path -eq $env:SystemRoot) {
    Write-Host "Предупреждение: Вы находитесь в защищенной системной папке ($($PWD.Path))." -ForegroundColor Yellow
    Write-Host "Чтобы избежать ошибок доступа, переключаемся в вашу домашнюю папку..." -ForegroundColor Yellow
    Set-Location -Path $env:USERPROFILE
    Write-Host "Новый путь установки: $($PWD.Path)\miband-bot`n" -ForegroundColor Gray
}

$INSTALL_DIR = "miband-bot"
$projectPath = Join-Path $PWD.Path $INSTALL_DIR
$autoStart = $false

# 1. Проверяем существование директории
if (Test-Path -Path $INSTALL_DIR) {
    if (Test-ConfiguredInstall -ProjectPath $projectPath) {
        Write-Host "Найдена настроенная установка. Обновляю файлы и запускаю бота..." -ForegroundColor Green
        $autoStart = $true
    } else {
        Write-Host "Папка '$INSTALL_DIR' уже существует в этой директории." -ForegroundColor Yellow
        $overwrite = Read-Host "Хотите перезаписать файлы проекта внутри нее? [Y/n]"
        if ($overwrite -eq "") { $overwrite = "y" }
        if ($overwrite -notmatch "^[Yy]$") {
            Write-Host "Установка отменена." -ForegroundColor Red
            Exit
        }
    }
} else {
    New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null
}

# Переходим в папку проекта
Set-Location -Path $INSTALL_DIR

# 2. Скачиваем ZIP-архив с GitHub
$zipUrl = "https://github.com/iAlexeyRu/miband-bot/archive/refs/heads/main.zip"
$tempZip = Join-Path $env:TEMP "miband-bot-temp.zip"
$unpackDir = "temp-unpack"

Write-Host "Загрузка последней версии проекта с GitHub..." -ForegroundColor Gray
if (Test-Path -LiteralPath $tempZip) {
    Remove-Item -LiteralPath $tempZip -Force
}
Invoke-WebRequest -Uri $zipUrl -OutFile $tempZip

# 3. Распаковываем во временную папку
Write-Host "Распаковка файлов проекта..." -ForegroundColor Gray
if (Test-Path -LiteralPath $unpackDir) {
    Remove-Item -LiteralPath $unpackDir -Recurse -Force
}
Expand-Archive -Path $tempZip -DestinationPath $unpackDir -Force
Remove-Item $tempZip

# 4. Копируем все файлы (включая скрытые) в корень папки установки
Get-ChildItem -Path "$unpackDir\miband-bot-main" -Force | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination "." -Recurse -Force
}
Remove-Item -Path $unpackDir -Recurse -Force

# 5. Запускаем интерактивный setup.bat
if ($autoStart) {
    Write-Host "`n✓ Проект обновлён. Запускаю бота..." -ForegroundColor Green
    $setupArgs = "/c setup.bat --start"
} else {
    Write-Host "`n✓ Проект успешно загружен! Запускаем интерактивную настройку..." -ForegroundColor Green
    $setupArgs = "/c setup.bat"
}
# Используем $PWD.Path вместо "." для передачи абсолютного корректного пути рабочей папки
Start-Process -FilePath "cmd.exe" -ArgumentList $setupArgs -WorkingDirectory $PWD.Path -NoNewWindow -Wait
