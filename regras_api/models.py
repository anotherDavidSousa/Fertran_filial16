from django.db import models


def _digits_only(value: str) -> str:
    return ''.join(ch for ch in (value or '') if ch.isdigit())


class RegraParBase(models.Model):
    cnpj_emit = models.CharField(max_length=20, db_index=True)
    cnpj_dest = models.CharField(max_length=20, db_index=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.cnpj_emit = _digits_only(self.cnpj_emit)
        self.cnpj_dest = _digits_only(self.cnpj_dest)
        super().save(*args, **kwargs)


class Rota(RegraParBase):
    mensagem = models.CharField(max_length=200)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['cnpj_emit', 'cnpj_dest'], name='uq_rota_emit_dest'),
        ]
        ordering = ['cnpj_emit', 'cnpj_dest']

    def __str__(self):
        return f'{self.cnpj_emit} -> {self.cnpj_dest}: {self.mensagem}'


class RegraFaturamento(RegraParBase):
    TIPO_OST = 'ordem_de_servico'
    TIPO_CTE = 'conhecimento_de_transporte'
    TIPO_CHOICES = [
        (TIPO_OST, 'Ordem de serviço'),
        (TIPO_CTE, 'Conhecimento de transporte'),
    ]
    tipo = models.CharField(max_length=40, choices=TIPO_CHOICES, default=TIPO_CTE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['cnpj_emit', 'cnpj_dest'], name='uq_faturamento_emit_dest'),
        ]
        ordering = ['cnpj_emit', 'cnpj_dest']

    def __str__(self):
        return f'{self.cnpj_emit} -> {self.cnpj_dest}: {self.tipo}'


class RegraPagador(RegraParBase):
    pagador = models.CharField(max_length=1, help_text='0=remetente, 1=destinatario')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['cnpj_emit', 'cnpj_dest'], name='uq_pagador_emit_dest'),
        ]
        ordering = ['cnpj_emit', 'cnpj_dest']

    def __str__(self):
        return f'{self.cnpj_emit} -> {self.cnpj_dest}: {self.pagador}'


class RegraPeso(RegraParBase):
    campo_peso = models.CharField(max_length=40, default='pesoL')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['cnpj_emit', 'cnpj_dest'], name='uq_peso_emit_dest'),
        ]
        ordering = ['cnpj_emit', 'cnpj_dest']

    def __str__(self):
        return f'{self.cnpj_emit} -> {self.cnpj_dest}: {self.campo_peso}'


class RegraValor(RegraParBase):
    campo_valor = models.CharField(max_length=40, default='vLiq')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['cnpj_emit', 'cnpj_dest'], name='uq_valor_emit_dest'),
        ]
        ordering = ['cnpj_emit', 'cnpj_dest']

    def __str__(self):
        return f'{self.cnpj_emit} -> {self.cnpj_dest}: {self.campo_valor}'


class Produto(models.Model):
    nome_produto = models.CharField(max_length=255, unique=True)
    codigo = models.CharField(max_length=50)
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nome_produto']

    def __str__(self):
        return f'{self.nome_produto} -> {self.codigo}'


class RegraTerminal(RegraParBase):
    TIPO_USIMINAS = 'usiminas'
    TIPO_TERMINAL = 'terminal'
    TIPO_CHOICES = [
        (TIPO_USIMINAS, 'Usiminas'),
        (TIPO_TERMINAL, 'Terminal fixo'),
    ]
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    valor = models.CharField(max_length=30, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['cnpj_emit', 'cnpj_dest'], name='uq_terminal_emit_dest'),
        ]
        ordering = ['cnpj_emit', 'cnpj_dest']

    def __str__(self):
        return f'{self.cnpj_emit} -> {self.cnpj_dest}: {self.tipo}'
