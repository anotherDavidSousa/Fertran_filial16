from django.contrib import admin
from .models import ApiKey, Carregamento, OST, CTe


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ('user', 'descricao', 'ativo', 'criado_em', 'ultimo_uso')
    readonly_fields = ('token', 'criado_em', 'ultimo_uso')
    list_filter = ('ativo',)
    search_fields = ('descricao', 'user__username')


@admin.register(Carregamento)
class CarregamentoAdmin(admin.ModelAdmin):
    list_display = (
        'nota_fiscal', 'chave_acesso', 'fluxo', 'emit_nome',
        'peso_display', 'datahora_emissao', 'arquivado', 'criado_em'
    )
    list_filter = ('fluxo', 'arquivado')
    search_fields = ('chave_acesso', 'nota_fiscal', 'emit_nome', 'dest_nome', 'xProd_produto')
    readonly_fields = ('criado_em', 'atualizado_em')
    date_hierarchy = 'datahora_emissao'

    def peso_display(self, obj):
        """Exibe o Peso (qCom) na lista do admin."""
        if obj.qCom_peso is None:
            return '—'
        return obj.qCom_peso
    peso_display.short_description = 'Peso'
    peso_display.admin_order_field = 'qCom_peso'


@admin.register(OST)
class OSTAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'filial', 'serie', 'documento', 'data_hora_manifesto_display',
        'remetente', 'destinatario', 'nota_fiscal', 'chave_acesso', 'tem_carregamento', 'tem_pdf', 'criado_em',
    )
    list_filter = ('data_manifesto', 'criado_em')
    search_fields = (
        'filial', 'serie', 'documento', 'remetente', 'destinatario',
        'chave_acesso', 'motorista',
    )
    readonly_fields = ('criado_em', 'pdf_storage_key')
    date_hierarchy = 'criado_em'
    list_per_page = 50

    def get_search_results(self, request, queryset, search_term):
        """Inclui busca por número da nota fiscal (campo JSON lista)."""
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        term = (search_term or '').strip()
        if term:
            from django.db.models import Q
            q_nf = Q(nota_fiscal__contains=[term])
            try:
                q_nf |= Q(nota_fiscal__contains=[int(term)])
            except ValueError:
                pass
            qs_nf = self.model.objects.filter(q_nf)
            queryset = (queryset | qs_nf).distinct()
            use_distinct = True
        return queryset, use_distinct

    def data_hora_manifesto_display(self, obj):
        if obj.data_manifesto:
            s = obj.data_manifesto.strftime('%d/%m/%Y')
            if obj.hora_manifesto:
                s += ' ' + obj.hora_manifesto.strftime('%H:%M')
            return s
        return '—'
    data_hora_manifesto_display.short_description = 'Data/hora manifesto'

    def tem_carregamento(self, obj):
        return obj.carregamentos.exists()
    tem_carregamento.boolean = True
    tem_carregamento.short_description = 'Vinculado'

    def tem_pdf(self, obj):
        return bool(obj.pdf_storage_key)
    tem_pdf.boolean = True
    tem_pdf.short_description = 'PDF'


@admin.register(CTe)
class CTeAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'filial', 'serie', 'numero_cte', 'data_hora_emissao_display',
        'remetente', 'destinatario', 'valor_total', 'placa_cavalo', 'motorista', 'nota_fiscal', 'tem_pdf', 'criado_em',
    )
    list_filter = ('data_emissao', 'criado_em')
    search_fields = (
        'filial', 'serie', 'numero_cte', 'remetente', 'destinatario', 'motorista',
        'nota_fiscal', 'chave_nfe', 'placa_cavalo', 'placa_carreta',
    )
    readonly_fields = ('criado_em', 'pdf_storage_key')
    date_hierarchy = 'data_emissao'
    list_per_page = 50

    def data_hora_emissao_display(self, obj):
        if obj.data_emissao:
            s = obj.data_emissao.strftime('%d/%m/%Y')
            if obj.hora_emissao:
                s += ' ' + obj.hora_emissao.strftime('%H:%M')
            return s
        return '—'
    data_hora_emissao_display.short_description = 'Data/hora emissão'

    def tem_pdf(self, obj):
        return bool(obj.pdf_storage_key)
    tem_pdf.boolean = True
    tem_pdf.short_description = 'PDF'
