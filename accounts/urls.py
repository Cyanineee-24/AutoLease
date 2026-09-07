from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register, name='register'),
    path(
        'login/',
        views.UserLoginView.as_view(
            next_page='home',
            redirect_authenticated_user=True,
        ),
        name='login',
    ),
    path(
        'logout/',
        auth_views.LogoutView.as_view(next_page='home'),
        name='logout',
    ),
    path('dashboard/', views.renter_dashboard, name='renter_dashboard'),
]
