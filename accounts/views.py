from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import RegistrationForm


def register(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            if user.is_renter:
                return redirect('accounts:renter_dashboard')
            return redirect('home')
    else:
        form = RegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})


@login_required
def renter_dashboard(request):
    if not request.user.is_renter:
        return redirect('home')
    return render(request, 'accounts/dashboard.html')
