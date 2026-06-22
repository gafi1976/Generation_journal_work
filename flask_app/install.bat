@echo off
chcp 65001 > nul
echo ============================================
echo  Установка зависимостей
echo  Генератор журнала Lotus Notes
echo ============================================
echo.

REM Проверяем наличие Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден!
    echo Скачайте Python 3.10+ с https://www.python.org/downloads/
    echo При установке обязательно отметьте "Add Python to PATH"
    pause
    exit /b 1
)

echo [OK] Python найден:
python --version
echo.

REM Обновляем pip
echo [1/2] Обновление pip...
python -m pip install --upgrade pip --quiet

REM Устанавливаем зависимости
echo [2/2] Установка Flask и Waitress...
python -m pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo [ОШИБКА] Не удалось установить зависимости.
    echo Проверьте подключение к интернету.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Установка завершена успешно!
echo  Запустите сервер: run.bat
echo ============================================
pause
