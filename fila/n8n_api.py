"""
API para integração n8n: OST e CT-e são criados/atualizados via JSON.
O n8n desmembra PDF, extrai dados, comprime, envia ao MinIO e envia aqui os campos + pdf_storage_key.
"""
import re
from datetime import date, datetime, time

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import OST, CTe

# Campos graváveis (n8n envia nomes iguais ao model)
OST_FIELDS = [
    'filial', 'serie', 'documento', 'data_manifesto', 'hora_manifesto',
    'remetente', 'destinatario', 'motorista', 'placa_cavalo', 'placa_carreta',
    'total_frete', 'pedagio', 'valor_tarifa_empresa', 'produto', 'peso',
    'nota_fiscal', 'data_nf', 'chave_acesso', 'pdf_storage_key',
]

CTE_FIELDS = [
    'filial', 'serie', 'numero_cte', 'data_emissao', 'hora_emissao',
    'remetente', 'municipio_remetente', 'destinatario', 'municipio_destinatario',
    'produto_predominante', 'vlr_tarifa', 'peso_bruto', 'frete_peso', 'pedagio',
    'valor_total', 'serie_nf', 'nota_fiscal', 'chave_nfe', 'dt', 'cnpj_proprietario',
    'placa_cavalo', 'placa_carreta', 'motorista', 'pdf_storage_key',
]


def _parse_numero_ost(numero_ost):
    if not numero_ost or not isinstance(numero_ost, str):
        return '', '', ''
    s = numero_ost.strip()
    parts = re.split(r'[.\-/]', s, maxsplit=2)
    filial = parts[0] if len(parts) > 0 else ''
    serie = parts[1] if len(parts) > 1 else ''
    documento = parts[2] if len(parts) > 2 else ''
    return filial, serie, documento


def _parse_date(val):
    if val is None or val == '':
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            pass
        for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(s[:10], fmt).date()
            except ValueError:
                continue
    return None


def _parse_time(val):
    if val is None or val == '':
        return None
    if isinstance(val, time):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        for fmt in ('%H:%M:%S', '%H:%M'):
            try:
                return datetime.strptime(s, fmt).time()
            except ValueError:
                continue
    return None


def _normalizar_nota_fiscal_ost(val):
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    s = str(val).strip()
    if not s:
        return []
    if ' + ' in s:
        return [x.strip() for x in s.split(' + ') if x.strip()]
    return [s]


def _encontrar_ost_existente(filial, serie, documento, nota_fiscal):
    if not documento and not (filial or serie):
        return None
    qs = OST.objects.filter(filial=filial or '', serie=serie or '', documento=documento or '')
    nf_norm = sorted(str(x) for x in (nota_fiscal or []))
    for ost in qs:
        ost_nf = sorted(str(x) for x in (ost.nota_fiscal or []))
        if ost_nf == nf_norm:
            return ost
    return None


def _encontrar_cte_existente(filial, serie, numero_cte):
    if not (filial or serie or numero_cte):
        return None
    return CTe.objects.filter(
        filial=filial or '', serie=serie or '', numero_cte=numero_cte or ''
    ).first()


def _norm_placa(p):
    if not p:
        return ''
    return str(p).replace('-', '').strip()[:10]


def _extrair_payload_ost(data: dict) -> dict:
    filial = (data.get('filial') or '').strip()
    serie = (data.get('serie') or '').strip()
    documento = (data.get('documento') or '').strip()
    if data.get('numero_ost') and not (filial and serie and documento):
        f, s, d = _parse_numero_ost(str(data.get('numero_ost') or ''))
        filial = filial or f
        serie = serie or s
        documento = documento or d
    nota_fiscal = _normalizar_nota_fiscal_ost(data.get('nota_fiscal'))
    pdf_storage_key = (data.get('pdf_storage_key') or '').strip()
    return {
        'filial': filial,
        'serie': serie,
        'documento': documento,
        'nota_fiscal': nota_fiscal,
        'pdf_storage_key': pdf_storage_key,
        'data_manifesto': _parse_date(data.get('data_manifesto')),
        'hora_manifesto': _parse_time(data.get('hora_manifesto')),
        'remetente': (data.get('remetente') or '')[:300],
        'destinatario': (data.get('destinatario') or '')[:300],
        'motorista': (data.get('motorista') or '')[:200],
        'placa_cavalo': _norm_placa(data.get('placa_cavalo')),
        'placa_carreta': _norm_placa(data.get('placa_carreta')),
        'total_frete': (data.get('total_frete') or '')[:50],
        'pedagio': (data.get('pedagio') or '')[:50],
        'valor_tarifa_empresa': (data.get('valor_tarifa_empresa') or '')[:50],
        'produto': (data.get('produto') or '')[:500],
        'peso': (data.get('peso') or '')[:50],
        'data_nf': (data.get('data_nf') or '')[:500],
        'chave_acesso': (data.get('chave_acesso') or '')[:50],
    }


def _extrair_payload_cte(data: dict) -> dict:
    pdf_storage_key = (data.get('pdf_storage_key') or '').strip()
    return {
        'filial': (data.get('filial') or '')[:20],
        'serie': (data.get('serie') or '')[:20],
        'numero_cte': (data.get('numero_cte') or '')[:50],
        'pdf_storage_key': pdf_storage_key,
        'data_emissao': _parse_date(data.get('data_emissao')),
        'hora_emissao': _parse_time(data.get('hora_emissao')),
        'remetente': (data.get('remetente') or '')[:500],
        'municipio_remetente': (data.get('municipio_remetente') or '')[:200],
        'destinatario': (data.get('destinatario') or '')[:500],
        'municipio_destinatario': (data.get('municipio_destinatario') or '')[:200],
        'produto_predominante': (data.get('produto_predominante') or '')[:500],
        'vlr_tarifa': (data.get('vlr_tarifa') or '')[:50],
        'peso_bruto': (data.get('peso_bruto') or '')[:50],
        'frete_peso': (data.get('frete_peso') or '')[:50],
        'pedagio': (data.get('pedagio') or '')[:50],
        'valor_total': (data.get('valor_total') or '')[:50],
        'serie_nf': (data.get('serie_nf') or '')[:20],
        'nota_fiscal': (data.get('nota_fiscal') or '')[:50],
        'chave_nfe': (data.get('chave_nfe') or '')[:44],
        'dt': (data.get('dt') or '')[:100],
        'cnpj_proprietario': (data.get('cnpj_proprietario') or '')[:30],
        'placa_cavalo': (data.get('placa_cavalo') or '').replace('-', '').strip()[:10],
        'placa_carreta': (data.get('placa_carreta') or '').replace('-', '').strip()[:10],
        'motorista': (data.get('motorista') or '')[:200],
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_n8n_ost_sync(request):
    """
    POST JSON: dados da OST já extraídos pelo n8n + ``pdf_storage_key`` (chave no MinIO após upload).

    Opcional: ``apenas_criar``: true → se já existir (filial+série+documento+NF), não atualiza (200, ignorado).

    Identificação: ``filial``, ``serie``, ``documento`` e ``nota_fiscal`` (lista ou string).
    Alternativa: ``numero_ost`` no formato ``16.001.12345``.
    """
    data = request.data if isinstance(request.data, dict) else {}
    payload = _extrair_payload_ost(data)
    if not payload['pdf_storage_key']:
        return Response(
            {'ok': False, 'erro': 'Campo obrigatório: pdf_storage_key (chave do objeto já enviado ao MinIO).'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not payload['documento'] and not (payload['filial'] or payload['serie']):
        return Response(
            {'ok': False, 'erro': 'Informe filial/série/documento ou numero_ost.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    apenas_criar = bool(data.get('apenas_criar') or data.get('somente_novo'))
    existente = _encontrar_ost_existente(
        payload['filial'], payload['serie'], payload['documento'], payload['nota_fiscal']
    )
    if existente:
        if apenas_criar and existente.pdf_storage_key:
            return Response({
                'ok': True,
                'acao': 'ignorado',
                'motivo': 'Registro já existe com PDF (apenas_criar=true).',
                'id': existente.pk,
                'pdf_storage_key': existente.pdf_storage_key,
            }, status=status.HTTP_200_OK)
        for k in OST_FIELDS:
            if k in payload:
                setattr(existente, k, payload[k])
        existente.save()
        return Response({
            'ok': True,
            'acao': 'atualizado',
            'id': existente.pk,
            'pdf_storage_key': existente.pdf_storage_key,
        }, status=status.HTTP_200_OK)
    ost = OST.objects.create(**{k: payload[k] for k in OST_FIELDS if k in payload})
    return Response({
        'ok': True,
        'acao': 'criado',
        'id': ost.pk,
        'pdf_storage_key': ost.pdf_storage_key,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_n8n_cte_sync(request):
    """
    POST JSON: dados do CT-e + ``pdf_storage_key`` (MinIO). Opcional ``apenas_criar`` como na OST.
    Identificação: filial + série + numero_cte.
    """
    data = request.data if isinstance(request.data, dict) else {}
    payload = _extrair_payload_cte(data)
    if not payload['pdf_storage_key']:
        return Response(
            {'ok': False, 'erro': 'Campo obrigatório: pdf_storage_key.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not (payload['filial'] or payload['serie'] or payload['numero_cte']):
        return Response(
            {'ok': False, 'erro': 'Informe filial, serie e/ou numero_cte.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    apenas_criar = bool(data.get('apenas_criar') or data.get('somente_novo'))
    existente = _encontrar_cte_existente(
        payload['filial'], payload['serie'], payload['numero_cte']
    )
    if existente:
        if apenas_criar and existente.pdf_storage_key:
            return Response({
                'ok': True,
                'acao': 'ignorado',
                'motivo': 'Registro já existe com PDF (apenas_criar=true).',
                'id': existente.pk,
                'pdf_storage_key': existente.pdf_storage_key,
            }, status=status.HTTP_200_OK)
        for k in CTE_FIELDS:
            if k in payload:
                setattr(existente, k, payload[k])
        existente.save()
        return Response({
            'ok': True,
            'acao': 'atualizado',
            'id': existente.pk,
            'pdf_storage_key': existente.pdf_storage_key,
        }, status=status.HTTP_200_OK)
    cte = CTe.objects.create(**{k: payload[k] for k in CTE_FIELDS if k in payload})
    return Response({
        'ok': True,
        'acao': 'criado',
        'id': cte.pk,
        'pdf_storage_key': cte.pdf_storage_key,
    }, status=status.HTTP_201_CREATED)
