#!/bin/bash
set -e

# --- ШАГ 1: Сборка фронтенда (JavaScript) ---
echo "Installing npm dependencies..."
npm install

echo "Building JavaScript bundle..."
npm run build # Эта команда создаст diet/static/diet/bundle.js

# --- ШАГ 2: Установка Python и зависимостей ---
echo "Installing Python dependencies..."
python3.9 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# --- ШАГ 3: Миграции базы ---
# Без DATABASE_URL Django молча возьмёт SQLite и миграции пройдут мимо боевой базы
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL is not set at build time" >&2
    exit 1
fi
echo "Applying migrations..."
python3 manage.py migrate --noinput

# --- ШАГ 4: Сборка статики Django ---
# Эта команда теперь найдет и твой styles.css, и bundle.js, и всё остальное
echo "Collecting static files..."
python3 manage.py collectstatic --noinput --clear

echo "--- Build finished successfully! ---"