#!/bin/bash

# Выходим из скрипта, если любая команда завершится с ошибкой
set -e

echo "Starting build..."

# 1. Устанавливаем зависимости
echo "Installing requirements..."
pip install -r requirements.txt

# 2. Применяем миграции к базе данных
echo "Applying database migrations..."
python manage.py migrate

# 3. Собираем статические файлы
echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Build finished."