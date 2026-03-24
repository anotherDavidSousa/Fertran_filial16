from django.contrib import admin

from .models import Programacao


@admin.register(Programacao)
class ProgramacaoAdmin(admin.ModelAdmin):
    list_display = (
        'codigo',
        'cnpj_emit',
        'cnpj_dest',
        'pagador',
        'tipo_faturamento',
        'campo_peso',
        'campo_valor',
        'atualizado_em',
    )
    list_filter = ('tipo_faturamento', 'pagador')
    search_fields = ('codigo', 'cnpj_emit', 'cnpj_dest', 'fornecedor_vale_pedagio')
