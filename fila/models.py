from django.conf import settings
from django.db import models
from django.db.models.functions import Now


class Carregamento(models.Model):
    """
    Registro de carregamento extraído de XML (n8n).
    Campos padrão do XML + extras em JSON para campos imprevisíveis.
    """
    # Identificação da NFe
    chave_acesso = models.CharField('Chave de Acesso', max_length=44, unique=True, db_index=True)
    serie_nfe = models.CharField('Série NFe', max_length=10, blank=True)
    nota_fiscal = models.CharField('Nota Fiscal', max_length=20, blank=True, db_index=True)
    datahora_emissao = models.DateTimeField('Data/Hora Emissão', null=True, blank=True)

    # Emitente
    emit_nome = models.CharField('Emitente Nome', max_length=200, blank=True)
    emit_cnpj = models.CharField('Emitente CNPJ', max_length=18, blank=True, db_index=True)

    # Destinatário
    dest_nome = models.CharField('Destinatário Nome', max_length=200, blank=True)
    dest_cnpj = models.CharField('Destinatário CNPJ', max_length=18, blank=True, db_index=True)

    # Produto e valores
    xProd_produto = models.CharField('Produto (xProd)', max_length=500, blank=True)
    cfop = models.CharField('CFOP', max_length=10, blank=True)
    qCom_peso = models.DecimalField(
        'Peso (qCom)',
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True
    )
    vProd_valor = models.DecimalField(
        'Valor (vProd)',
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Frete e transporte
    modFrete_tomador = models.CharField('Modalidade Frete / Tomador', max_length=100, blank=True)
    nome_cnpj = models.CharField('Nome/CNPJ (frete)', max_length=200, blank=True)
    transp_cnpj = models.CharField('Transportadora CNPJ', max_length=18, blank=True)

    # Campos extras imprevisíveis do XML (sem schema fixo)
    extras = models.JSONField(
        'Extras',
        default=dict,
        blank=True,
        help_text='Campos adicionais do XML que variam por fluxo (ex: numero_lacre, codigo_balanca).'
    )

    # Controle da fila
    fluxo = models.CharField(
        'Fluxo de carregamento',
        max_length=80,
        blank=True,
        db_index=True,
        help_text='Ex: Pedágio, Harsco, Bemisa-Usiminas, Bemisa-TCB.'
    )
    arquivado = models.BooleanField('Arquivado', default=False, db_index=True)
    manifestado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='carregamentos_manifestados',
        verbose_name='Manifestado por',
    )
    manifestado_em = models.DateTimeField('Manifestado em', null=True, blank=True)
    ost = models.ForeignKey(
        'OST',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='carregamentos',
        verbose_name='OST vinculada',
        help_text='Preenchido quando o item foi manifestado automaticamente pelo match com OST processada.',
    )
    criado_em = models.DateTimeField('Criado em', auto_now_add=True, db_default=Now())
    atualizado_em = models.DateTimeField('Atualizado em', auto_now=True, db_default=Now())

    class Meta:
        ordering = ['criado_em', 'datahora_emissao']
        verbose_name = 'Carregamento'
        verbose_name_plural = 'Carregamentos'

    def __str__(self):
        return f'{self.nota_fiscal or self.chave_acesso[:20]} - {self.xProd_produto[:50] or "NFe"}'

    def get_cte_ost_display(self):
        """Retorna 'Filial/Série/Documento' da OST vinculada ou string vazia."""
        if not self.ost:
            return ''
        parts = [self.ost.filial or '', self.ost.serie or '', self.ost.documento or '']
        return '/'.join(p for p in parts if p).strip() or ''

    def _fluxo_contains_token(self, nome):
        """True se fluxo contém o nome como um dos tokens (ex.: fluxo 'Escória, Pedágio' contém 'Escória')."""
        if not nome:
            return False
        needle = (nome or '').strip()
        tokens = [x.strip() for x in (self.fluxo or '').split(',') if x.strip()]
        return any(t == needle for t in tokens)

    def _is_fluxo_pedagio(self):
        fluxo_norm = (self.fluxo or '').upper().replace('Á', 'A').replace('Ê', 'E').strip()
        if fluxo_norm == 'PEDAGIO':
            return True
        tokens = [x.strip().upper().replace('Á', 'A').replace('Ê', 'E') for x in (self.fluxo or '').split(',') if x.strip()]
        return 'PEDAGIO' in tokens

    def _is_fluxo_escoria(self):
        fluxo_norm = (self.fluxo or '').upper().replace('Ó', 'O').replace('Í', 'I').strip()
        if fluxo_norm == 'ESCORIA':
            return True
        tokens = [x.strip().upper().replace('Ó', 'O').replace('Í', 'I') for x in (self.fluxo or '').split(',') if x.strip()]
        return 'ESCORIA' in tokens

    def _usiminas_logo_gif_dest(self):
        """True se for fluxo em que Usiminas usa logo + gif + pin + destinatário (Pedágio ou Escória)."""
        return self._is_fluxo_pedagio() or self._is_fluxo_escoria()

    def _is_bemisa_pedra_branca_para_positiva(self):
        """Remetente BEMISA PEDRA BRANCA e destinatário MINERACAO POSITIVA."""
        emit = (self.emit_nome or '').upper()
        dest = (self.dest_nome or '').upper()
        return 'BEMISA' in emit and 'PEDRA BRANCA' in emit and 'MINERACAO POSITIVA' in dest

    def _norm_cnpj(self, cnpj):
        """Retorna apenas os dígitos do CNPJ para comparação."""
        if not cnpj:
            return ''
        return ''.join(c for c in str(cnpj) if c.isdigit())

    def _is_bemisa_pedra_branca_pedagio_tcb(self):
        """Remetente BEMISA PEDRA BRANCA (emit_cnpj 57966337000256), dest BEMISA PARTICIPACOES (dest_cnpj 00514998000495), fluxo Pedágio → logo + gif + pin + TCB."""
        emit = (self.emit_nome or '').upper()
        dest = (self.dest_nome or '').upper()
        if not ('BEMISA' in emit and 'PEDRA BRANCA' in emit):
            return False
        if 'BEMISA PARTICIPACOES' not in dest:
            return False
        if not self._is_fluxo_pedagio():
            return False
        return (
            self._norm_cnpj(self.emit_cnpj) == '57966337000256'
            and self._norm_cnpj(self.dest_cnpj) == '00514998000495'
        )

    def _is_mgagro_gerdau_pedagio(self):
        """Fluxo Pedágio: remetente MG AGRO (emit_cnpj 24680718000487), destinatário GERDAU ACOMINAS (dest_cnpj 17227422000105) → mgagro-logo + gif + gerdau-logo."""
        emit = (self.emit_nome or '').upper()
        dest = (self.dest_nome or '').upper()
        if not self._is_fluxo_pedagio():
            return False
        if 'MG AGRO' not in emit:
            return False
        if 'GERDAU ACOMINAS' not in dest:
            return False
        return (
            self._norm_cnpj(self.emit_cnpj) == '24680718000487'
            and self._norm_cnpj(self.dest_cnpj) == '17227422000105'
        )

    def get_card_title_logo(self):
        """Retorna o path estático da logo para o título do card, ou None."""
        emit = (self.emit_nome or '').upper()
        dest = (self.dest_nome or '').upper()
        if self._is_bemisa_pedra_branca_para_positiva():
            return 'fila/images/bemisa-pedra-branca-logo.png'
        if self._is_bemisa_pedra_branca_pedagio_tcb():
            return 'fila/images/bemisa-pedra-branca-logo.png'
        if self._is_mgagro_gerdau_pedagio():
            return 'fila/images/mgagro-logo.png'
        if 'BEMISA' in emit:
            return 'fila/images/bemisa-logo.png'
        if 'USIMINAS' in emit and ('SAO FELIX' in dest or self._usiminas_logo_gif_dest()):
            return 'fila/images/usiminas-logo.png'
        if 'MG OXIDOS' in emit or 'MG OXIDOS MINERACAO' in emit:
            return 'fila/images/mgoxidos-logo.png'
        return None

    def get_card_title_suffix_logo(self):
        """Quando o fluxo é Bemisa-Usiminas ou Bemisa-Positiva (ou Bemisa Pedra Branca → Positiva), retorna a logo do parceiro."""
        emit = (self.emit_nome or '').upper()
        if self._is_bemisa_pedra_branca_para_positiva():
            return 'fila/images/positiva-logo.png'
        if 'BEMISA' in emit and self.fluxo == 'Bemisa-Usiminas':
            return 'fila/images/usiminas-logo.png'
        if 'BEMISA' in emit and self.fluxo == 'Bemisa-Positiva':
            return 'fila/images/positiva-logo.png'
        if self._is_mgagro_gerdau_pedagio():
            return 'fila/images/gerdau-logo.png'
        return None

    def get_card_title_suffix(self):
        """Retorna o texto ao lado da logo no título (ex.: TCB, nome do destino)."""
        emit = (self.emit_nome or '').upper()
        dest = (self.dest_nome or '').upper()
        if self._is_bemisa_pedra_branca_para_positiva():
            return ''  # Logo exibida via get_card_title_suffix_logo
        if self._is_bemisa_pedra_branca_pedagio_tcb():
            return 'TCB'
        if self._is_mgagro_gerdau_pedagio():
            return ''  # Logo exibida via get_card_title_suffix_logo
        if 'BEMISA' in emit and self.fluxo == 'Bemisa-TCB':
            return 'TCB'
        if 'BEMISA' in emit and self.fluxo == 'Bemisa-Usiminas':
            return ''  # Logo exibida via get_card_title_suffix_logo
        if 'BEMISA' in emit and self.fluxo == 'Bemisa-Positiva':
            return ''  # Logo exibida via get_card_title_suffix_logo
        if 'BEMISA' in emit:
            return self.fluxo or ''
        if 'USIMINAS' in emit and 'SAO FELIX' in dest:
            return self.dest_nome or ''
        if 'USIMINAS' in emit and self._usiminas_logo_gif_dest():
            return self.dest_nome or ''
        if 'MG OXIDOS' in emit or 'MG OXIDOS MINERACAO' in emit:
            return self.fluxo or ''
        return self.fluxo or 'NFe'

    def get_card_title_truck_gif(self):
        """Retorna o path do GIF de caminhão para o título (Bemisa, Usiminas, MG Agro–Gerdau Pedágio, etc.)."""
        emit = (self.emit_nome or '').upper()
        dest = (self.dest_nome or '').upper()
        if self._is_mgagro_gerdau_pedagio():
            return 'fila/images/truck1.gif'
        if 'BEMISA' in emit:
            return 'fila/images/truck1.gif'
        if 'USIMINAS' in emit and ('SAO FELIX' in dest or self._usiminas_logo_gif_dest()):
            return 'fila/images/truck1.gif'
        return None


class OST(models.Model):
    """
    Ordem de Serviço de Transporte – dados extraídos do PDF (processador).
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

    # PDF da página no MinIO (ost/{upload_id}/{page}.pdf)
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
    Conhecimento de Transporte Eletrônico – dados extraídos do PDF (processador de CT-e).
    Uma página do PDF = um CTe. PDF da página é armazenado no MinIO (ctes/).
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
