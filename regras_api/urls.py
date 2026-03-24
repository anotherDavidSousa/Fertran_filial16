from django.urls import path

from . import views


urlpatterns = [
    path(
        'api/programacoes/<str:cnpj_emit>/<str:cnpj_dest>/<str:pagador>/',
        views.programacao_lookup,
        name='api_programacao_lookup',
    ),
]
