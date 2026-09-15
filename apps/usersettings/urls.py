from django.contrib.auth.views import PasswordChangeDoneView, PasswordChangeView
from django.urls import path, reverse_lazy

from . import views

app_name = 'usersettings'

urlpatterns = [
    path('', views.settings_view, name='settings'),
    path(
        'password/',
        PasswordChangeView.as_view(
            template_name='usersettings/password_change.html',
            success_url=reverse_lazy('usersettings:password_change_done'),
        ),
        name='password_change',
    ),
    path(
        'password/done/',
        PasswordChangeDoneView.as_view(
            template_name='usersettings/password_change_done.html',
        ),
        name='password_change_done',
    ),
]
