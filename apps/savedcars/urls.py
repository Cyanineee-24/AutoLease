from django.urls import path

from . import views

app_name = 'savedcars'

urlpatterns = [
    path('', views.saved_list, name='list'),
]
