import re

from django.conf import settings
from django.db import models
from django.db.models.functions import Now

PLATE_RE = re.compile(r'\b([A-Z]{3}\d{4}|[A-Z]{3}\d[A-Z]\d{2})\b')


def _extract_plate(text):
    """Returns the first Brazilian plate (old or Mercosul) found in text, or empty string."""
    if not text:
        return ''
    m = PLATE_RE.search(text.upper())
    return m.group(1) if m else ''


class WppInstance(models.Model):
    """UAZAPI WhatsApp instance configuration."""
    nome = models.CharField('Nome', max_length=100)
    token = models.CharField('Token UAZAPI', max_length=200)
    ativo = models.BooleanField('Ativo', default=True)
    criado_em = models.DateTimeField('Criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Instância WPP'
        verbose_name_plural = 'Instâncias WPP'

    def __str__(self):
        return self.nome


class Contato(models.Model):
    """WhatsApp contact (individual, not a group)."""
    jid = models.CharField('JID', max_length=100, unique=True, db_index=True,
                           help_text='Ex.: 5531999999999@s.whatsapp.net')
    nome = models.CharField('Nome', max_length=200, blank=True)
    telefone = models.CharField('Telefone', max_length=30, blank=True)
    atualizado_em = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        verbose_name = 'Contato'
        verbose_name_plural = 'Contatos'
        ordering = ['nome']

    def __str__(self):
        return self.nome or self.jid


class GrupoConfig(models.Model):
    """WhatsApp group — stores JID, display name, optional plate link to Carregamento."""
    instance = models.ForeignKey(
        WppInstance, on_delete=models.CASCADE,
        related_name='grupos', verbose_name='Instância',
    )
    jid = models.CharField('JID', max_length=120, unique=True, db_index=True,
                           help_text='Ex.: 55319...@g.us')
    nome = models.CharField('Nome do grupo', max_length=300, blank=True)
    placa_cavalo = models.CharField(
        'Placa do cavalo', max_length=10, blank=True, db_index=True,
        help_text='Extraída automaticamente do nome do grupo ou preenchida manualmente.',
    )
    ativo = models.BooleanField('Ativo', default=True)
    sincronizado_em = models.DateTimeField('Sincronizado em', null=True, blank=True)

    class Meta:
        verbose_name = 'Grupo'
        verbose_name_plural = 'Grupos'
        ordering = ['nome']

    def save(self, *args, **kwargs):
        if self.nome and not self.placa_cavalo:
            self.placa_cavalo = _extract_plate(self.nome)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome or self.jid

    def carregamento_ativo(self):
        """Returns the active Carregamento linked to this group via placa_cavalo, or None."""
        if not self.placa_cavalo:
            return None
        from fila.models import Carregamento, OST
        ost_ids = OST.objects.filter(
            placa_cavalo__iexact=self.placa_cavalo
        ).values_list('id', flat=True)
        return Carregamento.objects.filter(
            ost_id__in=ost_ids, arquivado=False
        ).first()


class Mensagem(models.Model):
    TYPE_TEXT = 'text'
    TYPE_IMAGE = 'image'
    TYPE_DOCUMENT = 'document'
    TYPE_AUDIO = 'audio'
    TYPE_VIDEO = 'video'
    TYPE_STICKER = 'sticker'
    TYPE_OTHER = 'other'
    TYPE_CHOICES = [
        (TYPE_TEXT, 'Texto'),
        (TYPE_IMAGE, 'Imagem'),
        (TYPE_DOCUMENT, 'Documento'),
        (TYPE_AUDIO, 'Áudio'),
        (TYPE_VIDEO, 'Vídeo'),
        (TYPE_STICKER, 'Sticker'),
        (TYPE_OTHER, 'Outro'),
    ]

    msg_id = models.CharField('ID da mensagem', max_length=100, unique=True, db_index=True)
    grupo = models.ForeignKey(
        GrupoConfig, on_delete=models.CASCADE, null=True, blank=True,
        related_name='mensagens', verbose_name='Grupo',
    )
    contato = models.ForeignKey(
        Contato, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mensagens', verbose_name='Contato',
    )
    jid_chat = models.CharField('JID chat', max_length=120, db_index=True,
                                help_text='JID do grupo ou contato onde a mensagem chegou.')
    sender_jid = models.CharField('JID remetente', max_length=120, blank=True)
    sender_nome = models.CharField('Nome remetente', max_length=200, blank=True)
    from_me = models.BooleanField('Enviada por nós', default=False)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='mensagens_wpp',
        verbose_name='Enviado por (usuário interno)',
    )
    tipo = models.CharField('Tipo', max_length=20, choices=TYPE_CHOICES, default=TYPE_TEXT)
    texto = models.TextField('Texto', blank=True)
    media_minio_key = models.CharField('Chave MinIO da mídia', max_length=500, blank=True)
    timestamp = models.DateTimeField('Timestamp', db_index=True)
    criado_em = models.DateTimeField('Criado em', auto_now_add=True, db_default=Now())

    class Meta:
        verbose_name = 'Mensagem'
        verbose_name_plural = 'Mensagens'
        ordering = ['timestamp']

    def __str__(self):
        preview = self.texto[:60] if self.texto else f'[{self.tipo}]'
        return f'{self.sender_nome or self.sender_jid}: {preview}'


class PerfilUsuario(models.Model):
    """WPP profile for a Django user — signature displayed when sending messages."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='wpp_perfil', verbose_name='Usuário',
    )
    assinatura = models.CharField(
        'Assinatura', max_length=50,
        help_text='Ex.: João — será exibida em negrito no início da mensagem.',
    )

    class Meta:
        verbose_name = 'Perfil WPP'
        verbose_name_plural = 'Perfis WPP'

    def __str__(self):
        return f'{self.user} ({self.assinatura})'


class Pendencia(models.Model):
    STATUS_ABERTA = 'aberta'
    STATUS_RESOLVIDA = 'resolvida'
    STATUS_CHOICES = [
        (STATUS_ABERTA, 'Aberta'),
        (STATUS_RESOLVIDA, 'Resolvida'),
    ]

    grupo = models.ForeignKey(
        GrupoConfig, on_delete=models.CASCADE,
        related_name='pendencias', verbose_name='Grupo',
    )
    texto = models.TextField('Descrição')
    status = models.CharField(
        'Status', max_length=20, choices=STATUS_CHOICES,
        default=STATUS_ABERTA, db_index=True,
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pendencias_criadas', verbose_name='Criado por',
    )
    criado_em = models.DateTimeField('Criado em', auto_now_add=True, db_default=Now())
    resolvido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pendencias_resolvidas', verbose_name='Resolvido por',
    )
    resolvido_em = models.DateTimeField('Resolvido em', null=True, blank=True)
    arquivou_carregamento = models.BooleanField(
        'Arquivou carregamento?', default=False,
        help_text='True se a resolução desta pendência causou o arquivamento de um Carregamento.',
    )

    class Meta:
        verbose_name = 'Pendência'
        verbose_name_plural = 'Pendências'
        ordering = ['-criado_em']

    def __str__(self):
        return f'[{self.get_status_display()}] {self.grupo} — {self.texto[:60]}'
