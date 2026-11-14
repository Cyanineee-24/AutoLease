from django.urls import path

from . import views

app_name = 'agencyfleet'

urlpatterns = [
    path('', views.listings, name='list'),
]
