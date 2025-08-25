#!/bin/bash
set -e

# Устанавливаем Pip
yum install -y python3-pip

# Устанавливаем зависимости
python3 -m pip install -r requirements.txt

# Применяем миграции
python3 manage.py migrate

# Создаем суперпользователя (новая команда!)
python3 manage.py createsuperuser --noinput || true

# Собираем статику
python3 manage.py collectstatic --noinput --clear