#!/bin/bash

set -e

# Устанавливаем ТОЛЬКО Pip для системного Python3
yum install -y python3-pip

# Теперь все команды будут работать
python3 -m pip install -r requirements.txt
python3 manage.py migrate
python3 manage.py collectstatic --noinput --clear