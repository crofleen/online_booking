@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Онлайн-бронирование услуг — демонстрационная сборка

set "PY=python"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
python -c "import django, rest_framework" >nul 2>&1
if not errorlevel 1 goto deps_ready

if not exist ".venv\Scripts\python.exe" (
    echo [1/5] Создание виртуального окружения...
    python -m venv .venv
)
echo [2/5] Установка зависимостей...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
set "PY=.venv\Scripts\python.exe"
goto migrate

:deps_ready
echo [1/5] Зависимости найдены в системном Python

:migrate
echo [3/5] Подготовка базы данных...
"%PY%" manage.py migrate --noinput

echo [4/5] Демонстрационные данные...
"%PY%" manage.py seed_demo

echo [5/5] Запуск сервера на http://127.0.0.1:8000
echo Для остановки нажмите Ctrl+C
start "" http://127.0.0.1:8000/
"%PY%" manage.py runserver 127.0.0.1:8000
