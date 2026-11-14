from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import RegistrationForm


def _safe_next(request):
    """Return the requested `next` path, or '' if it points off-site."""
    next_url = request.POST.get('next') or request.GET.get('next') or ''
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return ''


def register(request):
    if request.user.is_authenticated:
        return redirect('home:landing')

    next_url = _safe_next(request)

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            request.session['prefill_email'] = form.cleaned_data.get('email')
            messages.success(request, 'Account created successfully! Click Log in to continue.')
            if next_url:
                return redirect(f"{reverse('login:login')}?{urlencode({'next': next_url})}")
            return redirect('login:login')
    else:
        form = RegistrationForm()

    return render(request, 'register/register.html', {'form': form, 'next': next_url})
