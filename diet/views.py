from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .gemini import GeminiError, get_verdict
from .models import Check, User

MAX_PRODUCT_LENGTH = 200
HISTORY_LIMIT = 20
EXAMPLES = ["Овсянка на молоке", "Шаурма с курицей", "Латте на овсяном", "Гречка с грибами"]


def setup_steps(user):
    """Что нужно сделать, чтобы проверять продукты. Порядок = порядок онбординга."""
    authed = user.is_authenticated
    return [
        {"label": "Войти или зарегистрироваться", "done": authed,
         "url": reverse("profile"), "action": "Войти"},
        {"label": "Добавить API-ключ Gemini", "done": authed and bool(user.get_api_key()),
         "url": reverse("settings"), "action": "Добавить"},
        {"label": "Описать свою диету", "done": authed and bool(user.dietInfo.strip()),
         "url": reverse("settings"), "action": "Описать"},
    ]


def home(request):
    result = request.session.pop('result', None)
    draft = request.session.pop('product_draft', '')
    steps = setup_steps(request.user)

    check = None
    history = []
    if request.user.is_authenticated:
        if result and result.get("kind") == "verdict":
            check = Check.objects.filter(user=request.user, pk=result.get("check_id")).first()
            result = None
        history = request.user.checks.all()[:HISTORY_LIMIT]
        if check:
            history = [c for c in history if c.pk != check.pk]

    return render(request, 'diet/home.html', {
        "result": result,
        "check": check,
        "draft": draft,
        "steps": steps,
        "ready": all(step["done"] for step in steps),
        "history": history,
        "examples": EXAMPLES,
        "max_product_length": MAX_PRODUCT_LENGTH,
    })


def _check_failed(request, product, title, message, url=None, action=None):
    request.session['result'] = {
        "kind": "error", "title": title, "message": message, "url": url, "action": action,
    }
    request.session['product_draft'] = product
    return HttpResponseRedirect(reverse("home"))


def check(request):
    if request.method != 'POST':
        return HttpResponseRedirect(reverse("home"))

    product = (request.POST.get('product') or '').strip()[:MAX_PRODUCT_LENGTH]
    settings_url = reverse("settings")

    if not product:
        return _check_failed(request, product, "Введите продукт",
                             "Напишите название блюда или его состав.")
    if not request.user.is_authenticated:
        return _check_failed(request, product, "Нужен вход",
                             "Войдите или зарегистрируйтесь, чтобы проверять продукты.",
                             reverse("profile"), "Войти")

    api_key = request.user.get_api_key()
    if not api_key:
        return _check_failed(request, product, "Не указан API-ключ",
                             "Добавьте ключ Gemini в настройках, без него проверка не работает.",
                             settings_url, "Открыть настройки")
    if not request.user.dietInfo.strip():
        return _check_failed(request, product, "Не описана диета",
                             "Опишите в настройках, что вам можно и нельзя.",
                             settings_url, "Открыть настройки")

    try:
        data = get_verdict(product, request.user.dietInfo, api_key)
    except GeminiError as e:
        if e.kind == "key":
            return _check_failed(request, product, e.title, e.message, settings_url, "Открыть настройки")
        return _check_failed(request, product, e.title, e.message)

    item = Check.objects.create(user=request.user, product=product, **data)
    request.session['result'] = {"kind": "verdict", "check_id": item.pk}
    return HttpResponseRedirect(reverse("home"))


@require_POST
def clear_history(request):
    if request.user.is_authenticated:
        request.user.checks.all().delete()
        messages.success(request, "История очищена")
    return HttpResponseRedirect(reverse("home"))


def settings(request):
    if not request.user.is_authenticated:
        messages.info(request, "Войдите, чтобы настроить диету и ключ")
        return HttpResponseRedirect(reverse("profile"))

    user = request.user
    if request.method == "POST":
        was_ready = all(step["done"] for step in setup_steps(user))

        user.dietInfo = request.POST.get('diet_description', '').strip()
        new_key = request.POST.get('diet_api_key', '').strip()
        if request.POST.get('remove_key'):
            user.set_api_key('')
        elif new_key:
            # Пустое поле = оставить сохранённый ключ: ключ в форму не отдаём
            user.set_api_key(new_key)
        user.save()

        if not was_ready and all(step["done"] for step in setup_steps(user)):
            messages.success(request, "Всё готово, можно проверять продукты")
            return HttpResponseRedirect(reverse("home"))
        messages.success(request, "Настройки сохранены")
        return HttpResponseRedirect(reverse("settings"))

    api_key = user.get_api_key()
    return render(request, 'diet/settings.html', {
        "user_diet_info": user.dietInfo,
        "key_hint": api_key[-4:] if api_key else "",
    })


def _auth_failed(request, tab, username, errors):
    request.session['auth_form'] = {"tab": tab, "username": username, "errors": errors}
    return HttpResponseRedirect(reverse("profile"))


def login_view(request):
    if request.method != "POST":
        return HttpResponseRedirect(reverse("profile"))

    raw_username = request.POST.get("username", "").strip()
    username = canonical_username(raw_username.lower())
    password = request.POST.get("password", "")
    user = authenticate(request, username=username, password=password)

    if user is None:
        return _auth_failed(request, "login", raw_username,
                            {"password": "Неправильный логин или пароль"})
    login(request, user)
    return HttpResponseRedirect(reverse("home"))


@require_POST
def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("home"))


def canonical_username(username):
    # Старые аккаунты регистрировались без lower(), ищем их без учёта регистра
    if User.objects.filter(username=username).exists():
        return username
    matches = list(User.objects.filter(username__iexact=username).values_list("username", flat=True)[:2])
    return matches[0] if len(matches) == 1 else username


def register(request):
    if request.method != "POST":
        return HttpResponseRedirect(reverse("profile"))

    username = request.POST.get("username", "").lower().strip()
    password = request.POST.get("password", "")
    confirmation = request.POST.get("confirmation", "")

    errors = {}
    if not username:
        errors["username"] = "Введите логин"
    elif User.objects.filter(username__iexact=username).exists():
        errors["username"] = "Пользователь с таким именем уже существует"
    if password != confirmation:
        errors["confirmation"] = "Пароли не совпадают"
    else:
        try:
            validate_password(password, User(username=username))
        except ValidationError as e:
            errors["password"] = " ".join(e.messages)

    if not errors:
        try:
            user = User.objects.create_user(username=username, password=password)
        except IntegrityError:
            errors["username"] = "Пользователь с таким именем уже существует"
    if errors:
        return _auth_failed(request, "register", username, errors)

    login(request, user)
    messages.success(request, "Аккаунт создан. Осталось добавить ключ Gemini и описать диету")
    return HttpResponseRedirect(reverse("settings"))


def profile(request):
    form = request.session.pop('auth_form', None) or {}
    context = {
        "tab": form.get("tab", "login"),
        "form_username": form.get("username", ""),
        "errors": form.get("errors", {}),
    }
    if request.user.is_authenticated:
        context["steps"] = setup_steps(request.user)
        context["check_count"] = request.user.checks.count()
    return render(request, 'diet/profile.html', context)
