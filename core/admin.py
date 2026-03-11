from django.contrib import admin
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


@admin.register(Cavalo)
class CavaloAdmin(admin.ModelAdmin):
    list_display = ('placa', 'tipo', 'classificacao', 'situacao', 'proprietario', 'gestor', 'carreta', 'emissao_laudo')
    list_filter = ('tipo', 'classificacao', 'situacao', 'fluxo')
    search_fields = ('placa',)
    inlines = [CavaloDocumentoInline]


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


@admin.register(LogCarreta)
class LogCarretaAdmin(admin.ModelAdmin):
    list_display = ('data_hora', 'tipo', 'placa_cavalo', 'carreta_anterior', 'carreta_nova')
    list_filter = ('tipo',)
    date_hierarchy = 'data_hora'


@admin.register(HistoricoGestor)
class HistoricoGestorAdmin(admin.ModelAdmin):
    list_display = ('gestor', 'cavalo', 'data_inicio', 'data_fim')
