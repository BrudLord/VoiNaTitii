from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path
from game import views

urlpatterns = [path('', views.home), path('login/', views.sign_in), path('register/', views.register),
               path('logout/', auth.LogoutView.as_view()), path('api/state/', views.state),
               path('api/thrown-preview/', views.thrown_preview), path('api/action/', views.action), path('api/photo/<int:pk>/', views.photo),
               path('portrait/<int:pk>/', views.portrait), path('admin/', admin.site.urls)]
