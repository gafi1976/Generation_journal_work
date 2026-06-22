@echo off
chcp 65001 > nul
echo ============================================
echo  Генератор журнала Lotus Notes
echo  Запуск сервера...
echo ============================================
echo.

REM Переходим в папку скрипта
cd /d "%~dp0"

REM Проверяем Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден!
    echo Сначала запустите install.bat
    pause
    exit /b 1
)

REM Проверяем Waitress
python -c "import waitress" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Зависимости не установлены!
    echo Сначала запустите install.bat
    pause
    exit /b 1
)

echo  Сервер доступен по адресу:
echo  http://localhost:5000
echo.
echo  Коллеги открывают в браузере:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set IP=%%a
    goto :show_ip
)
:show_ip
set IP=%IP: =%
echo  http://%IP%:5000
echo.
echo  Для остановки нажмите Ctrl+C
echo ============================================
echo.

python run.py

pause
