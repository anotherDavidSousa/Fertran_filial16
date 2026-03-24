from django.urls import path

from . import views


urlpatterns = [
    path('api/rotas/<str:cnpj_emit>/<str:cnpj_dest>/', views.rota_lookup, name='api_rota_lookup'),
    path(
        'api/regras/faturamento/<str:cnpj_emit>/<str:cnpj_dest>/',
        views.faturamento_lookup,
        name='api_faturamento_lookup',
    ),
    path(
        'api/regras/pagador/<str:cnpj_emit>/<str:cnpj_dest>/',
        views.pagador_lookup,
        name='api_pagador_lookup',
    ),
    path(
        'api/regras/peso/<str:cnpj_emit>/<str:cnpj_dest>/',
        views.peso_lookup,
        name='api_peso_lookup',
    ),
    path(
        'api/regras/valor/<str:cnpj_emit>/<str:cnpj_dest>/',
        views.valor_lookup,
        name='api_valor_lookup',
    ),
    path('api/produtos/<str:nome_produto>/', views.produto_lookup, name='api_produto_lookup'),
    path(
        'api/regras/terminal/<str:cnpj_emit>/<str:cnpj_dest>/',
        views.terminal_lookup,
        name='api_terminal_lookup',
    ),
]
