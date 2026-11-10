from django.contrib import messages
from django.shortcuts import redirect, render

from .forms import RegistrationForm


def register(request):
    if request.user.is_authenticated:
        return redirect('home:landing')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            request.session['prefill_email'] = form.cleaned_data.get('email')
            messages.success(request, 'Account created successfully! Click Log in to continue.')
            return redirect('login:login')
    else:
        form = RegistrationForm()

    return render(request, 'register/register.html', {'form': form})
