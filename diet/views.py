from django.shortcuts import render

from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from .gemini import get_verdict

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
    return render(request, 'diet/settings.html', {
        "user_diet_info": user_diet_info,
        "user_api_key": user_api_key
    })

def login_view(request):
    if request.method == "POST":

        username = request.POST["username"]
        password = request.POST["password"]
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
            print('User is not authenticated.')

    return HttpResponseRedirect(reverse("home"))