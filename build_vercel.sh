#!/bin/bash

# Устанавливаем Python 3.9 (это решит проблему "command not found")
yum install -y python39 python39-pip

# Устанавливаем зависимости, используя конкретную версию pip
python3.9 -m pip install -r requirements.txt

# Применяем миграции
python3.9 manage.py migrate

# Собираем статику
python3.9 manage.py collectstatic --noinput --clear