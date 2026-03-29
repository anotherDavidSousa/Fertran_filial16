from django.urls import path

from . import views

app_name = 'wpp'

urlpatterns = [
    # Pages
    path('', views.inbox, name='inbox'),
    path('chat/<str:jid>/', views.inbox, name='chat'),
    path('pendencias/', views.pendencias, name='pendencias'),
    path('config/', views.config, name='config'),
    # AJAX — chat partial (HTML, loaded into right panel)
    path('api/chat/<str:jid>/partial/', views.chat_partial, name='chat_partial'),
    # AJAX — data endpoints
    path('api/grupos/', views.grupos_json, name='grupos_json'),
    path('api/chat/<str:jid>/mensagens/', views.mensagens_json, name='mensagens_json'),
    path('api/chat/<str:jid>/enviar/', views.enviar_mensagem, name='enviar_mensagem'),
    path('api/pendencias/criar/', views.criar_pendencia, name='criar_pendencia'),
    path('api/pendencias/<int:pk>/resolver/', views.resolver_pendencia, name='resolver_pendencia'),
    path('api/grupos/sync/', views.sync_grupos, name='sync_grupos'),
    path('api/chat/<str:jid>/foto/', views.sync_foto, name='sync_foto'),
    # Media proxy (authenticated redirect to MinIO)
    path('api/media/<path:key>', views.media_proxy, name='media_proxy'),
    # Webhook (no session auth)
    path('api/webhook/', views.webhook, name='webhook'),
]
