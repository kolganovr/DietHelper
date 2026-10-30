"""Локальный сервер для скриншотов README (только runserver, sqlite, без прода).

Создаёт тестовый аккаунт demo с безглютеновой диетой, кладёт в историю несколько проверок
и подменяет get_verdict ответами из кэша eval (gemini-3.1-flash-lite, промпт v1), так что
в Gemini не ходит и настоящий ключ не нужен. Сначала прогнать eval по кейсам gf*.

    python -X utf8 eval/screens_server.py      # затем http://127.0.0.1:8001, вход demo / DEMO_PASSWORD
"""
import glob
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.chdir(REPO)
os.environ.update(DJANGO_SETTINGS_MODULE="DietHelper.settings", DEBUG="True", SECRET_KEY="local-screens")
os.environ.pop("FERNET_KEY", None)
os.environ.pop("DATABASE_URL", None)

import django  # noqa: E402

django.setup()
from django.core.management import call_command  # noqa: E402

from diet import views  # noqa: E402
from diet.models import Check, User  # noqa: E402

USERNAME = "demo"
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo-local-only-42")  # локальный тестовый аккаунт
DIET = "Целиакия, строгая безглютеновая диета"
HISTORY = ["Пиво", "Рис с курицей", "Соевый соус", "Гречневая каша на воде"]

cache = {}
for path in glob.glob(str(REPO / "eval" / ".cache" / "gemini-3.1-flash-lite" / "*" / "gf*_0.json")):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("answer"):
        cache[data["product"].lower()] = data["answer"]


def cached_verdict(product, diet, api_key, **kwargs):
    return cache[product.strip().lower()]


if __name__ == "__main__":
    call_command("migrate", verbosity=0)
    views.get_verdict = cached_verdict

    user, _ = User.objects.get_or_create(username=USERNAME)
    user.set_password(DEMO_PASSWORD)
    user.dietInfo = DIET
    user.set_api_key("local-demo-key-not-real")
    user.save()
    user.checks.all().delete()
    for product in HISTORY:
        Check.objects.create(user=user, product=product, **cache[product.lower()])

    call_command("runserver", "127.0.0.1:8001", "--noreload")
