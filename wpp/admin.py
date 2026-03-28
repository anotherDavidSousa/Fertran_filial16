from django.contrib import admin

from .models import Contato, GrupoConfig, Mensagem, PerfilUsuario, Pendencia, WppInstance


@admin.register(WppInstance)
class WppInstanceAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativo', 'criado_em')
    list_filter = ('ativo',)


@admin.register(Contato)
class ContatoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'telefone', 'jid', 'atualizado_em')
    search_fields = ('nome', 'telefone', 'jid')


@admin.register(GrupoConfig)
class GrupoConfigAdmin(admin.ModelAdmin):
    list_display = ('nome', 'placa_cavalo', 'instance', 'ativo', 'sincronizado_em')
    list_filter = ('ativo', 'instance')
    search_fields = ('nome', 'placa_cavalo', 'jid')
    readonly_fields = ('jid',)


@admin.register(Mensagem)
class MensagemAdmin(admin.ModelAdmin):
    list_display = ('sender_nome', 'jid_chat', 'tipo', '_texto_curto', 'timestamp')
    list_filter = ('tipo', 'from_me')
    search_fields = ('sender_nome', 'texto', 'jid_chat')
    readonly_fields = ('msg_id', 'timestamp', 'criado_em')

    @admin.display(description='Texto')
    def _texto_curto(self, obj):
        return obj.texto[:80] or f'[{obj.tipo}]'


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ('user', 'assinatura')
    search_fields = ('user__username', 'assinatura')


@admin.register(Pendencia)
class PendenciaAdmin(admin.ModelAdmin):
    list_display = ('grupo', 'status', 'criado_por', 'criado_em', 'resolvido_por', 'resolvido_em')
    list_filter = ('status', 'grupo')
    search_fields = ('texto', 'grupo__nome')
    readonly_fields = ('criado_em', 'resolvido_em')
