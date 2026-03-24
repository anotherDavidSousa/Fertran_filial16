from django.db import models


def _digits_only(value: str) -> str:
    return ''.join(ch for ch in (value or '') if ch.isdigit())


class Programacao(models.Model):
    """
    Programação por par emitente/destinatário e pagador do frete (modFrete: 0 ou 1).
    Expõe JSON alinhado a get_programacao() no cliente novaui.
    """

    TIPO_OST = 'ordem_de_servico'
    TIPO_CTE = 'conhecimento_de_transporte'
    TIPO_CHOICES = [
        (TIPO_OST, 'Ordem de serviço'),
        (TIPO_CTE, 'Conhecimento de transporte'),
    ]

    cnpj_emit = models.CharField(max_length=20, db_index=True)
    cnpj_dest = models.CharField(max_length=20, db_index=True)
    PAGADOR_REM = '0'
    PAGADOR_DEST = '1'
    PAGADOR_CHOICES = [
        (PAGADOR_REM, 'Remetente paga'),
        (PAGADOR_DEST, 'Destinatário paga'),
    ]
    pagador = models.CharField(
        max_length=1,
        db_index=True,
        choices=PAGADOR_CHOICES,
        help_text='0=remetente paga, 1=destinatário paga (modFrete na NF-e)',
    )
    codigo = models.CharField(max_length=40, help_text='Identificador da programação (ex.: PRG001)')
    tipo_faturamento = models.CharField(
        max_length=40,
        choices=TIPO_CHOICES,
        default=TIPO_CTE,
    )
    campo_peso = models.CharField(
        max_length=40,
        default='pesoL',
        help_text='pesoL | pesoqCom | pesoB | atlas_prod (atributos DadosXML)',
    )
    campo_valor = models.CharField(
        max_length=40,
        default='vLiq',
        help_text='vLiq | vProd',
    )
    fornecedor_vale_pedagio = models.CharField(
        max_length=50,
        blank=True,
        help_text='Código do fornecedor de vale pedágio; vazio = não enviar no JSON',
    )
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['cnpj_emit', 'cnpj_dest', 'pagador'],
                name='uq_programacao_emit_dest_pagador',
            ),
        ]
        ordering = ['cnpj_emit', 'cnpj_dest', 'pagador']
        verbose_name = 'Programação'
        verbose_name_plural = 'Programações'

    def save(self, *args, **kwargs):
        self.cnpj_emit = _digits_only(self.cnpj_emit)
        self.cnpj_dest = _digits_only(self.cnpj_dest)
        p = (self.pagador or '').strip()
        for ch in p:
            if ch in '01':
                self.pagador = ch
                break
        else:
            self.pagador = ''
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.cnpj_emit}->{self.cnpj_dest} pag={self.pagador} [{self.codigo}]'
