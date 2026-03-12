from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('esqueci-senha/', views.esqueci_senha_view, name='esqueci_senha'),
    path('solicitar-acesso/', views.solicitar_acesso_view, name='solicitar_acesso'),
    path('fila/', views.fila_view, name='fila'),
    path('fila/<slug:fluxo_slug>/', views.fila_view, name='fila_fluxo'),
    path('fluxos/', views.fila_view, name='fluxos'),
    path('arquivados/', views.arquivados_view, name='arquivados'),
    path('manifestados/', views.arquivados_view, name='manifestados'),
    path('lista-carregamentos/', views.lista_carregamentos_view, name='lista_carregamentos'),
    path('ost/<int:pk>/download-pdf/', views.ost_download_pdf, name='ost_download_pdf'),
    path('cte/<int:pk>/download-pdf/', views.cte_download_pdf, name='cte_download_pdf'),
    path('item/<int:pk>/', views.item_detail, name='item_detalhe'),
    path('item/<int:pk>/manifestar/', views.item_manifestar_view, name='manifestar'),
    path('item/<int:pk>/download-xml/', views.item_download_xml, name='download_xml'),
    path('item/<int:pk>/download-ost-pdf/', views.item_download_ost_pdf, name='download_ost_pdf'),
    path('processador/', views.processador_view, name='processador'),
]
