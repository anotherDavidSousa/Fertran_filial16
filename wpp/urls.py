from django.urls import path

from . import views

app_name = 'wpp'

urlpatterns = [
    # Pages
    path('', views.inbox, name='inbox'),
    path('chat/<str:jid>/', views.chat, name='chat'),
    path('pendencias/', views.pendencias, name='pendencias'),
    path('config/', views.config, name='config'),
    # AJAX / polling
    path('api/chat/<str:jid>/mensagens/', views.mensagens_json, name='mensagens_json'),
    path('api/chat/<str:jid>/enviar/', views.enviar_mensagem, name='enviar_mensagem'),
    path('api/pendencias/criar/', views.criar_pendencia, name='criar_pendencia'),
    path('api/pendencias/<int:pk>/resolver/', views.resolver_pendencia, name='resolver_pendencia'),
    path('api/grupos/sync/', views.sync_grupos, name='sync_grupos'),
    # Webhook (no session auth — validated via token header)
    path('api/webhook/', views.webhook, name='webhook'),
]
