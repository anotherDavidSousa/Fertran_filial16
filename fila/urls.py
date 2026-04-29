from django.urls import path
from . import views
from . import n8n_api

urlpatterns = [
    path('', views.home_view, name='home'),
    path('esqueci-senha/', views.esqueci_senha_view, name='esqueci_senha'),
    path('solicitar-acesso/', views.solicitar_acesso_view, name='solicitar_acesso'),
    path('lista-carregamentos/', views.lista_carregamentos_view, name='lista_carregamentos'),
    path('ost/<int:pk>/download-pdf/', views.ost_download_pdf, name='ost_download_pdf'),
    path('cte/<int:pk>/download-pdf/', views.cte_download_pdf, name='cte_download_pdf'),
    path('processador/', views.processador_view, name='processador'),
    # API n8n
    path('api/n8n/ost/', n8n_api.api_n8n_ost_sync, name='api_n8n_ost_sync'),
    path('api/n8n/cte/', n8n_api.api_n8n_cte_sync, name='api_n8n_cte_sync'),
]
