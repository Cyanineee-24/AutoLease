from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = 'login'

urlpatterns = [
    path(
        'login/',
        views.UserLoginView.as_view(
            next_page='accounts:renter_dashboard',
            redirect_authenticated_user=True,
        ),
        name='login',
    ),
]