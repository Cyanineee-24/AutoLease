from django.urls import path
from . import views

app_name = 'fleet'

urlpatterns = [
    path('<int:pk>/', views.vehicle_detail, name='vehicle_detail'),
    path('<int:pk>/favorite/', views.favorite_toggle, name='favorite_toggle'),
]
