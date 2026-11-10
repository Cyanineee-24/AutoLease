from django.urls import path

from . import views

app_name = 'mybookings'

urlpatterns = [
    path('', views.my_bookings, name='list'),
    path('<int:pk>/cancel/', views.cancel_booking, name='cancel'),
    path('<int:pk>/review/', views.review_booking, name='review'),
]
