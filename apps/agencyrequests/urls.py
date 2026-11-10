from django.urls import path

from . import views

app_name = 'agencyrequests'

urlpatterns = [
    path('', views.inbox, name='inbox'),
    path('<int:pk>/decide/', views.decide, name='decide'),
]
