from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    Produto,
    RegraFaturamento,
    RegraPagador,
    RegraPeso,
    RegraTerminal,
    RegraValor,
    Rota,
)


def _digits_only(value: str) -> str:
    return ''.join(ch for ch in (value or '') if ch.isdigit())


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rota_lookup(request, cnpj_emit, cnpj_dest):
    emit = _digits_only(cnpj_emit)
    dest = _digits_only(cnpj_dest)
    rota = Rota.objects.filter(cnpj_emit=emit, cnpj_dest=dest).first()
    return Response({'mensagem': rota.mensagem if rota else 'Rota não encontrada'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def faturamento_lookup(request, cnpj_emit, cnpj_dest):
    emit = _digits_only(cnpj_emit)
    dest = _digits_only(cnpj_dest)
    regra = RegraFaturamento.objects.filter(cnpj_emit=emit, cnpj_dest=dest).first()
    return Response({'tipo': regra.tipo if regra else 'conhecimento_de_transporte'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pagador_lookup(request, cnpj_emit, cnpj_dest):
    emit = _digits_only(cnpj_emit)
    dest = _digits_only(cnpj_dest)
    regra = RegraPagador.objects.filter(cnpj_emit=emit, cnpj_dest=dest).first()
    if not regra:
        return Response({})
    return Response({'pagador': regra.pagador})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def peso_lookup(request, cnpj_emit, cnpj_dest):
    emit = _digits_only(cnpj_emit)
    dest = _digits_only(cnpj_dest)
    regra = RegraPeso.objects.filter(cnpj_emit=emit, cnpj_dest=dest).first()
    return Response({'campo_peso': regra.campo_peso if regra else 'pesoL'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def valor_lookup(request, cnpj_emit, cnpj_dest):
    emit = _digits_only(cnpj_emit)
    dest = _digits_only(cnpj_dest)
    regra = RegraValor.objects.filter(cnpj_emit=emit, cnpj_dest=dest).first()
    return Response({'campo_valor': regra.campo_valor if regra else 'vLiq'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def produto_lookup(request, nome_produto):
    nome = (nome_produto or '').strip()
    if not nome:
        return Response({})
    produto = Produto.objects.filter(nome_produto__iexact=nome).first()
    if not produto:
        produto = Produto.objects.filter(nome_produto__icontains=nome).first()
    if not produto:
        return Response({})
    return Response({'codigo': produto.codigo})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def terminal_lookup(request, cnpj_emit, cnpj_dest):
    emit = _digits_only(cnpj_emit)
    dest = _digits_only(cnpj_dest)
    regra = RegraTerminal.objects.filter(cnpj_emit=emit, cnpj_dest=dest).first()
    if not regra:
        return Response({})
    payload = {'tipo': regra.tipo}
    if regra.tipo == RegraTerminal.TIPO_TERMINAL and regra.valor:
        payload['valor'] = regra.valor
    return Response(payload)
