#!/bin/bash
set -e

# Устанавливаем Python и активируем виртуальное окружение
python3.9 -m venv .venv
source .venv/bin/activate

# Устанавливаем зависимости
pip install -r requirements.txt

# Собираем статику в папку 'staticfiles'
python3 manage.py collectstatic --noinput --clear

echo "--- Static files have been collected successfully. ---"