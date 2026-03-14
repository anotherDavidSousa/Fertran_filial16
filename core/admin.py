from django.contrib import admin
from django.db.models import Q, Case, When, Value, IntegerField, F, CharField
from .models import (
    Proprietario,
    Gestor,
    Cavalo,
    Carreta,
    Motorista,
    LogCarreta,
    HistoricoGestor,
    CavaloDocumento,
    CarretaDocumento,
    ProprietarioDocumento,
    MotoristaDocumento,
)


class ProprietarioDocumentoInline(admin.TabularInline):
    model = ProprietarioDocumento
    extra = 1


@admin.register(Proprietario)
class ProprietarioAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nome_razao_social', 'tipo', 'status', 'whatsapp')
    search_fields = ('nome_razao_social', 'codigo')
    inlines = [ProprietarioDocumentoInline]


@admin.register(Gestor)
class GestorAdmin(admin.ModelAdmin):
    list_display = ('nome', 'meta_faturamento')


class CavaloDocumentoInline(admin.TabularInline):
    model = CavaloDocumento
    extra = 1


def _cavalos_queryset_ordenado(queryset, filtrar_apenas_com_carreta=False):
    """Ordenação: Classificação → Situação → Fluxo → Tipo → Motorista (A-Z). Opcional: filtrar só com carreta/bi-truck."""
    qs = queryset
    if filtrar_apenas_com_carreta:
        qs = qs.filter(Q(carreta__isnull=False) | Q(tipo='bi_truck')).exclude(situacao='desagregado')
    return qs.annotate(
        ordem_classificacao=Case(
            When(classificacao='agregado', then=Value(0)),
            When(classificacao='frota', then=Value(1)),
            When(classificacao='terceiro', then=Value(2)),
            default=Value(0),
            output_field=IntegerField(),
        ),
        ordem_situacao=Case(
            When(situacao='ativo', then=Value(0)),
            When(situacao='parado', then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        ),
        ordem_fluxo=Case(
            When(fluxo='escoria', then=Value(0)),
            When(fluxo='minerio', then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        ),
        ordem_tipo=Case(
            When(tipo='toco', then=Value(0)),
            When(tipo='trucado', then=Value(1)),
            When(tipo='bi_truck', then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        ),
        motorista_nome_ordem=Case(
            When(motorista__isnull=False, then=F('motorista__nome')),
            default=Value(''),
            output_field=CharField(),
        ),
    ).order_by('ordem_classificacao', 'ordem_situacao', 'ordem_fluxo', 'ordem_tipo', 'motorista_nome_ordem')


@admin.register(Cavalo)
class CavaloAdmin(admin.ModelAdmin):
    list_display = ('placa', 'tipo', 'classificacao', 'situacao', 'proprietario', 'gestor', 'carreta', 'emissao_laudo')
    list_filter = ('tipo', 'classificacao', 'situacao', 'fluxo')
    search_fields = ('placa',)
    inlines = [CavaloDocumentoInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('motorista', 'carreta', 'gestor')
        # Admin: mostrar todos (desagregados, sem carreta, todos os status)
        return _cavalos_queryset_ordenado(qs, filtrar_apenas_com_carreta=False)


class CarretaDocumentoInline(admin.TabularInline):
    model = CarretaDocumento
    extra = 1


@admin.register(Carreta)
class CarretaAdmin(admin.ModelAdmin):
    list_display = ('placa', 'marca', 'modelo', 'classificacao', 'situacao', 'emissao_laudo')
    list_filter = ('classificacao', 'situacao')
    search_fields = ('placa',)


class MotoristaDocumentoInline(admin.TabularInline):
    model = MotoristaDocumento
    extra = 1


@admin.register(Motorista)
class MotoristaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cpf', 'whatsapp', 'cavalo')
    search_fields = ('nome', 'cpf')
    inlines = [MotoristaDocumentoInline]

    def get_inline_instances(self, request, obj=None):
        """Mostra o inline de documentos só na edição; ao adicionar evita 500 por formulário vazio."""
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)


@admin.register(LogCarreta)
class LogCarretaAdmin(admin.ModelAdmin):
    list_display = ('data_hora', 'tipo', 'placa_cavalo', 'carreta_anterior', 'carreta_nova')
    list_filter = ('tipo',)
    date_hierarchy = 'data_hora'


@admin.register(HistoricoGestor)
class HistoricoGestorAdmin(admin.ModelAdmin):
    list_display = ('gestor', 'cavalo', 'data_inicio', 'data_fim')
