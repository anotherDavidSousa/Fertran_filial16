import secrets

from django.conf import settings
from django.db import models
from django.db.models.functions import Now



class OST(models.Model):
    """
    Ordem de Serviço de Transporte — dados normalmente enviados pelo n8n (extração fora do Django).
    Numero_ost é separado em Filial / Série / Documento.
    """
    # Numero OST separado em três colunas (ex.: 16.001.12345 → filial=16, serie=001, documento=12345)
    filial = models.CharField('Filial', max_length=20, blank=True, db_index=True)
    serie = models.CharField('Série', max_length=20, blank=True, db_index=True)
    documento = models.CharField('Documento', max_length=50, blank=True, db_index=True)

    data_manifesto = models.DateField('Data manifesto', null=True, blank=True)
    hora_manifesto = models.TimeField('Hora manifesto', null=True, blank=True)

    remetente = models.CharField('Remetente', max_length=300, blank=True)
    destinatario = models.CharField('Destinatário', max_length=300, blank=True)
    motorista = models.CharField('Motorista', max_length=200, blank=True)

    placa_cavalo = models.CharField('Placa cavalo', max_length=10, blank=True)
    placa_carreta = models.CharField('Placa carreta', max_length=10, blank=True)

    total_frete = models.CharField('Total frete', max_length=50, blank=True)
    pedagio = models.CharField('Pedágio', max_length=50, blank=True)
    valor_tarifa_empresa = models.CharField('Valor tarifa empresa', max_length=50, blank=True)

    produto = models.CharField('Produto', max_length=500, blank=True)
    peso = models.CharField('Peso', max_length=50, blank=True)

    # Várias NFs/datas separadas por " + " (ex.: "822814 + 823032")
    nota_fiscal = models.JSONField('Nota fiscal', default=list, blank=True, help_text='Lista de NFs ou string única')
    data_nf = models.CharField('Data NF', max_length=500, blank=True, help_text='Datas separadas por " + "')

    chave_acesso = models.CharField('Chave de acesso NF', max_length=50, blank=True, db_index=True)

    # PDF da página no MinIO (ex.: ost/{nota_ou_documento}.pdf)
    pdf_storage_key = models.CharField(
        'Chave do PDF no MinIO',
        max_length=500,
        blank=True,
        help_text='Objeto no bucket para download do PDF desta OST.',
    )

    criado_em = models.DateTimeField('Criado em', auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'OST'
        verbose_name_plural = 'OSTs'

    def __str__(self):
        return f'OST {self.filial}.{self.serie}.{self.documento}' if (self.filial or self.serie or self.documento) else f'OST #{self.pk}'


class CTe(models.Model):
    """
    Conhecimento de Transporte Eletrônico — dados enviados pelo n8n; PDF no MinIO (ctes/…).
    """
    filial = models.CharField('Filial', max_length=20, blank=True, db_index=True)
    serie = models.CharField('Série', max_length=20, blank=True, db_index=True)
    numero_cte = models.CharField('Número CT-e', max_length=50, blank=True, db_index=True)

    data_emissao = models.DateField('Data emissão', null=True, blank=True)
    hora_emissao = models.TimeField('Hora emissão', null=True, blank=True)

    remetente = models.CharField('Remetente', max_length=500, blank=True)
    municipio_remetente = models.CharField('Município remetente', max_length=200, blank=True)
    destinatario = models.CharField('Destinatário', max_length=500, blank=True)
    municipio_destinatario = models.CharField('Município destinatário', max_length=200, blank=True)

    produto_predominante = models.CharField('Produto predominante', max_length=500, blank=True)
    vlr_tarifa = models.CharField('Valor tarifa', max_length=50, blank=True)
    peso_bruto = models.CharField('Peso bruto', max_length=50, blank=True)
    frete_peso = models.CharField('Frete peso', max_length=50, blank=True)
    pedagio = models.CharField('Pedágio', max_length=50, blank=True)
    valor_total = models.CharField('Valor total', max_length=50, blank=True)

    serie_nf = models.CharField('Série NF', max_length=20, blank=True, help_text='Série do documento NF-e (ex.: 0)')
    nota_fiscal = models.CharField('Nota fiscal', max_length=50, blank=True, db_index=True, help_text='Número da NF-e')
    chave_nfe = models.CharField('Chave NF-e', max_length=44, blank=True, db_index=True)
    dt = models.CharField('DT', max_length=100, blank=True)
    cnpj_proprietario = models.CharField('CNPJ/CPF proprietário', max_length=30, blank=True)

    placa_cavalo = models.CharField('Placa cavalo', max_length=10, blank=True)
    placa_carreta = models.CharField('Placa carreta', max_length=10, blank=True)
    motorista = models.CharField('Motorista', max_length=200, blank=True)

    pdf_storage_key = models.CharField(
        'Chave do PDF no MinIO',
        max_length=500,
        blank=True,
        help_text='Objeto no bucket para download do PDF deste CT-e (pasta ctes/).',
    )

    criado_em = models.DateTimeField('Criado em', auto_now_add=True)

    class Meta:
        ordering = ['-data_emissao', '-criado_em']
        verbose_name = 'CT-e'
        verbose_name_plural = 'CT-es'

    def __str__(self):
        return f'CT-e {self.filial}/{self.serie}/{self.numero_cte}' if (self.filial or self.serie or self.numero_cte) else f'CT-e #{self.pk}'


class ApiKey(models.Model):
    """Chave estática para integrações (ex.: n8n) com header X-Api-Key."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='api_keys',
        verbose_name='Usuário',
    )
    token = models.CharField(max_length=64, unique=True, db_index=True, blank=True)
    descricao = models.CharField('Descrição', max_length=200, blank=True)
    ativo = models.BooleanField('Ativo', default=True)
    criado_em = models.DateTimeField('Criado em', auto_now_add=True)
    ultimo_uso = models.DateTimeField('Último uso', null=True, blank=True)

    class Meta:
        verbose_name = 'API Key'
        verbose_name_plural = 'API Keys'

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.descricao or self.token[:8]}… ({self.user})'

    @classmethod
    def gerar_para_usuario(cls, user, descricao=''):
        return cls.objects.create(user=user, descricao=descricao)
