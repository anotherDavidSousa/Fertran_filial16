from django.contrib import admin

from .models import (
    Produto,
    RegraFaturamento,
    RegraPagador,
    RegraPeso,
    RegraTerminal,
    RegraValor,
    Rota,
)


@admin.register(Rota)
class RotaAdmin(admin.ModelAdmin):
    list_display = ('cnpj_emit', 'cnpj_dest', 'mensagem', 'atualizado_em')
    search_fields = ('cnpj_emit', 'cnpj_dest', 'mensagem')


@admin.register(RegraFaturamento)
class RegraFaturamentoAdmin(admin.ModelAdmin):
    list_display = ('cnpj_emit', 'cnpj_dest', 'tipo', 'atualizado_em')
    list_filter = ('tipo',)
    search_fields = ('cnpj_emit', 'cnpj_dest')


@admin.register(RegraPagador)
class RegraPagadorAdmin(admin.ModelAdmin):
    list_display = ('cnpj_emit', 'cnpj_dest', 'pagador', 'atualizado_em')
    search_fields = ('cnpj_emit', 'cnpj_dest')


@admin.register(RegraPeso)
class RegraPesoAdmin(admin.ModelAdmin):
    list_display = ('cnpj_emit', 'cnpj_dest', 'campo_peso', 'atualizado_em')
    search_fields = ('cnpj_emit', 'cnpj_dest', 'campo_peso')


@admin.register(RegraValor)
class RegraValorAdmin(admin.ModelAdmin):
    list_display = ('cnpj_emit', 'cnpj_dest', 'campo_valor', 'atualizado_em')
    search_fields = ('cnpj_emit', 'cnpj_dest', 'campo_valor')


@admin.register(RegraTerminal)
class RegraTerminalAdmin(admin.ModelAdmin):
    list_display = ('cnpj_emit', 'cnpj_dest', 'tipo', 'valor', 'atualizado_em')
    list_filter = ('tipo',)
    search_fields = ('cnpj_emit', 'cnpj_dest', 'valor')


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ('nome_produto', 'codigo', 'atualizado_em')
    search_fields = ('nome_produto', 'codigo')
