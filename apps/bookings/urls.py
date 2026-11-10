from django.urls import path

from . import views

app_name = 'bookings'

urlpatterns = [
    path('request/<int:vehicle_pk>/', views.booking_request, name='request'),
]
