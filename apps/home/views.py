from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

def landing(request):
    if request.user.is_authenticated:
        return redirect('home:dashboard')
    return render(request, 'home/landing.html')


@login_required
def dashboard(request):
    return render(request, 'home/dashboard.html')
