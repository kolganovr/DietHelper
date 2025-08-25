#!/bin/bash

# Устанавливаем зависимости
pip install -r requirements.txt

# Применяем миграции
python manage.py migrate

# Собираем статику
python manage.py collectstatic --noinput --clear