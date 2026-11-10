from django.urls import path

from . import views

app_name = 'userprofile'

urlpatterns = [
    path('', views.profile, name='profile'),
    path('edit/', views.profile_edit, name='profile_edit'),
    path('license/', views.license_edit, name='license'),
]
