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

# --- ШАГ 3: Сборка статики Django ---
# Эта команда теперь найдет и твой styles.css, и bundle.js, и всё остальное
echo "Collecting static files..."
python3 manage.py collectstatic --noinput --clear

echo "--- Build finished successfully! ---"