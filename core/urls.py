from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.index, name='index'),
    path('proprietarios/', views.proprietario_list, name='proprietario_list'),
    path('proprietarios/novo/', views.proprietario_create, name='proprietario_create'),
    path('proprietarios/<int:pk>/', views.proprietario_detail, name='proprietario_detail'),
    path('proprietarios/<int:pk>/editar/', views.proprietario_edit, name='proprietario_edit'),
    path('cavalos/', views.cavalo_list, name='cavalo_list'),
    path('cavalos/novo/', views.cavalo_create, name='cavalo_create'),
    path('cavalos/<int:pk>/', views.cavalo_detail, name='cavalo_detail'),
    path('cavalos/<int:pk>/editar/', views.cavalo_edit, name='cavalo_edit'),
    path('carretas/', views.carreta_list, name='carreta_list'),
    path('carretas/nova/', views.carreta_create, name='carreta_create'),
    path('carretas/<int:pk>/', views.carreta_detail, name='carreta_detail'),
    path('carretas/<int:pk>/editar/', views.carreta_edit, name='carreta_edit'),
    path('motoristas/', views.motorista_list, name='motorista_list'),
    path('motoristas/novo/', views.motorista_create, name='motorista_create'),
    path('motoristas/<int:pk>/', views.motorista_detail, name='motorista_detail'),
    path('motoristas/<int:pk>/editar/', views.motorista_edit, name='motorista_edit'),
    path('logs/', views.log_list, name='log_list'),
    path('ajax/carretas/classificacoes/', views.ajax_carretas_classificacoes, name='ajax_carretas_classificacoes'),
    path('api/login/', views.api_login, name='api_login'),
    path('api/token/refresh/', views.api_refresh_token, name='api_token_refresh'),
    path('api/me/', views.api_me, name='api_me'),
]
