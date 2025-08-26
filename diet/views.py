from django.shortcuts import render

from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from .gemini import get_verdict

from .models import User

def home(request):
    verdict = request.session.pop('verdict', None)
    explanation = request.session.pop('explanation', None)
    return render(request, 'diet/home.html', {
        "verdict": verdict,
        "explanation": explanation
    })

def settings(request):
    if request.method == "POST":
        diet_description = request.POST.get("diet_description", "")
        user_api_key = request.POST.get("api_key", "")
        print(f'Diet description updated: {diet_description}')
        print(f'User API key updated: {user_api_key}')

        if request.user.is_authenticated:
            user = request.user
            user.dietInfo = diet_description
            user.apiKey = user_api_key
            user.save()

        return HttpResponseRedirect(reverse("home"))
    
    if request.user.is_authenticated:
        user_diet_info = request.user.dietInfo
        user_api_key = request.user.apiKey
    else:
        user_diet_info = ""
        user_api_key = ""
    return render(request, 'diet/settings.html', {
        "user_diet_info": user_diet_info,
        "user_api_key": user_api_key
    })

def login_view(request):
    if request.method == "POST":

        username = request.POST["username"].lower().strip()
        password = request.POST["password"].lower().strip()
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return HttpResponseRedirect(reverse("home"))
        else:
            return render(request, "diet/login.html", {
                "message": "Invalid username and/or password."
            })
    else:
        return render(request, "diet/login.html")

def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("home"))

def register(request):
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        user = User.objects.create_user(username=username, password=password)
        user.save()
        login(request, user)
        return HttpResponseRedirect(reverse("home"))
    else:
        return render(request, "diet/register.html")

def check(request):
    if request.method == 'POST':
        product = request.POST.get('product')
        if request.user.is_authenticated:
            diet_description = request.user.dietInfo
            api_key = request.user.apiKey

            print(f'Product: {product}, Diet Description: {diet_description}, API Key: {api_key}')

            verdict, explanation = get_verdict(product, diet_description, api_key)
            request.session['verdict'] = verdict
            request.session['explanation'] = explanation
        else:
            request.session['verdict'] = "User is not authenticated."
            request.session['explanation'] = "Please log in to access this feature."

    return HttpResponseRedirect(reverse("home"))