from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Programacao


def _digits_only(value: str) -> str:
    return ''.join(ch for ch in (value or '') if ch.isdigit())


def _norm_pagador(pagador) -> str:
    """Alinha com modFrete da NF-e: '0' ou '1'."""
    s = str(pagador).strip()
    for ch in s:
        if ch in '01':
            return ch
    return ''


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def programacao_lookup(request, cnpj_emit, cnpj_dest, pagador):
    emit = _digits_only(cnpj_emit)
    dest = _digits_only(cnpj_dest)
    pg = _norm_pagador(pagador)
    if not emit or not dest or pg not in ('0', '1'):
        return Response({})

    obj = Programacao.objects.filter(
        cnpj_emit=emit, cnpj_dest=dest, pagador=pg
    ).first()
    if not obj:
        return Response({})

    data = {
        'codigo': obj.codigo,
        'tipo_faturamento': obj.tipo_faturamento,
        'campo_peso': obj.campo_peso,
        'campo_valor': obj.campo_valor,
    }
    fv = (obj.fornecedor_vale_pedagio or '').strip()
    if fv:
        data['fornecedor_vale_pedagio'] = fv
    return Response(data)
