from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import RegistrationForm


def register(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            request.session['prefill_email'] = form.cleaned_data.get('email')
            request.session['prefill_password'] = form.cleaned_data.get('password1')
            messages.success(request, 'Account created successfully! Click Log in to continue.')
            return redirect('accounts:login')
    else:
        form = RegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})


class UserLoginView(auth_views.LoginView):
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        return reverse('accounts:renter_dashboard')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['prefill_email'] = self.request.session.pop('prefill_email', '')
        context['prefill_password'] = self.request.session.pop('prefill_password', '')
        return context


@login_required
def renter_dashboard(request):
    return render(request, 'accounts/dashboard.html')
