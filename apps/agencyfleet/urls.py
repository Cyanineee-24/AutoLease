from django.urls import path

from . import views

app_name = 'agencyfleet'

urlpatterns = [
    path('', views.listings, name='list'),
    path('new/', views.create, name='create'),
    path('<int:pk>/edit/', views.edit, name='edit'),
    path('<int:pk>/status/', views.change_status, name='status'),
    path('<int:pk>/delete/', views.delete, name='delete'),
    path('<int:pk>/photos/', views.photos, name='photos'),
    path('<int:pk>/photos/<int:image_pk>/primary/', views.photo_primary, name='photo_primary'),
    path('<int:pk>/photos/<int:image_pk>/delete/', views.photo_delete, name='photo_delete'),
]
