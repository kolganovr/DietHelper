from django.shortcuts import render

from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.db import IntegrityError
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .gemini import get_verdict

from .models import User

def home(request):
    verdict = request.session.pop('verdict', None)
    explanation = request.session.pop('explanation', None)
    product = request.session.pop('product', None)

    return render(request, 'diet/home.html', {
        "verdict": verdict,
        "explanation": explanation,
        "product": product
    })

def settings(request):
    if request.method == "POST":
        diet_description = request.POST.get('diet_description', '')
        user_api_key = request.POST.get('diet_api_key', '')

        if request.user.is_authenticated:
            user = request.user
            user.dietInfo = diet_description
            user.set_api_key(user_api_key)
            user.save()

        return HttpResponseRedirect(reverse("home"))
    
    if request.user.is_authenticated:
        user_diet_info = request.user.dietInfo
        user_api_key = request.user.get_api_key()
    else:
        user_diet_info = ""
        user_api_key = ""
    return render(request, 'diet/settings.html', {
        "user_diet_info": user_diet_info,
        "user_api_key": user_api_key
    })

def login_view(request):
    if request.method == "POST":

        username = canonical_username(request.POST["username"].lower().strip())
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return HttpResponseRedirect(reverse("home"))
        else:
            return render(request, "diet/profile.html", {
                "message": "Неправильное имя пользователя или пароль"
            })
    else:
        return render(request, "diet/profile.html")

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
    if request.method == "POST":
        username = request.POST["username"].lower().strip()
        password = request.POST["password"]
        confirmation = request.POST.get("confirmation", "")

        error = None
        if not username:
            error = "Введите логин"
        elif password != confirmation:
            error = "Пароли не совпадают"
        elif User.objects.filter(username__iexact=username).exists():
            error = "Пользователь с таким именем уже существует"
        else:
            try:
                validate_password(password, User(username=username))
            except ValidationError as e:
                error = " ".join(e.messages)

        if error:
            return render(request, "diet/profile.html", {"message": error})

        try:
            user = User.objects.create_user(username=username, password=password)
        except IntegrityError:
            return render(request, "diet/profile.html", {
                "message": "Пользователь с таким именем уже существует"
            })
        login(request, user)
        return HttpResponseRedirect(reverse("home"))
    else:
        return render(request, "diet/profile.html")

def check(request):
    if request.method == 'POST':
        product = request.POST.get('product')
        if not request.user.is_authenticated:
            request.session['verdict'] = "Вы не зашли в аккаунт"
            request.session['explanation'] = "Пожалуйста, войдите или зарегестируйтесь"
            request.session['product'] = ""
            return HttpResponseRedirect(reverse("home"))
       
        diet_description = request.user.dietInfo
        api_key = request.user.get_api_key()
        
        if not api_key:
            request.session['verdict'] = "Не указан API ключ"
            request.session['explanation'] = "Пожалуйста, укажите ваш API ключ в настройках"
            request.session['product'] = ""
            return HttpResponseRedirect(reverse("home"))
        if not diet_description:
            request.session['verdict'] = "Не указаны параметры диеты"
            request.session['explanation'] = "Пожалуйста, укажите параметры вашей диеты в настройках"
            request.session['product'] = ""
            return HttpResponseRedirect(reverse("home"))
        
        try:
            verdict, explanation = get_verdict(product, diet_description, api_key)
            request.session['verdict'] = verdict
            request.session['explanation'] = explanation
            request.session['product'] = product
        except Exception as e:
            request.session['verdict'] = "Ошибка при получении данных"
            request.session['explanation'] = str(e)
            request.session['product'] = ""

    return HttpResponseRedirect(reverse("home"))

def profile(request):
    return render(request, 'diet/profile.html')