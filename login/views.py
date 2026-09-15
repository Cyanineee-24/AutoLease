from django.contrib.auth import views as auth_views
from django.urls import reverse


class UserLoginView(auth_views.LoginView):
    template_name = 'login/login.html'
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        return reverse('home:dashboard')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['prefill_email'] = self.request.session.pop('prefill_email', '')
        context['prefill_password'] = self.request.session.pop('prefill_password', '')
        return context
