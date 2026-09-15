from django.urls import path

from . import views

app_name = 'userprofile'

urlpatterns = [
    path('', views.profile, name='profile'),
]
