from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count, Q
from django.http import JsonResponse, FileResponse, Http404
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from .menu_perms import require_menu_perm
from django.core.files.storage import default_storage
from django.contrib import messages
from .models import Carregamento, OST, CTe
from .ost_extractor import ExtratorOST
from .processador_cte import ExtratorCTe
import json
import re
import unicodedata
import uuid
from io import BytesIO
from datetime import datetime

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    PdfReader = PdfWriter = None


def logout_view(request):
    """Faz logout e redireciona para a tela de login (aceita GET para o link Sair)."""
    logout(request)
    return redirect('login')


@login_required
@require_menu_perm('fila')
def fila_view(request, fluxo_slug=None):
    """
    Fila dinâmica de carregamentos.
    fluxo_slug: slug do fluxo para filtrar (ex: pedagio, bemisa-usiminas).
    """
    total_fila = Carregamento.objects.filter(arquivado=False).count()
    total_arquivados = Carregamento.objects.filter(arquivado=True).count()

    # Fluxos: aceita fluxo com múltiplas categorias (ex.: "Escória, Pedágio") – cada token vira uma aba
    fluxos_raw = list(
        Carregamento.objects.filter(arquivado=False).values_list('fluxo', flat=True).distinct()
    )
    tokens_set = set()
    for f in fluxos_raw:
        for t in (x.strip() for x in (f or '').split(',') if x.strip()):
            tokens_set.add(t)
    # Ordenar e montar lista com contagem por token (item conta em cada aba cujo token está no fluxo)
    tokens_ordenados = sorted(tokens_set)
    fluxos_list = []
    for nome in tokens_ordenados:
        pattern = _fluxo_token_regex(nome)
        total = Carregamento.objects.filter(arquivado=False, fluxo__iregex=pattern).count()
        fluxos_list.append({
            'nome': nome,
            'slug': _fluxo_to_slug(nome),
            'total': total,
        })
    if not tokens_ordenados:
        fluxos_list.append({'nome': 'Sem fluxo', 'slug': 'sem-fluxo', 'total': total_fila})
    if total_fila > 0:
        fluxos_list.insert(0, {'nome': 'Todos', 'slug': 'todos', 'total': total_fila})

    cards_por_fluxo = {f['nome']: f['total'] for f in fluxos_list}
    card_total_fila = total_fila
    card_manifestados = total_arquivados

    # Itens da fila: filtrar por fluxo (um item com "Escória, Pedágio" aparece nas duas abas)
    filtro = Q(arquivado=False)
    fluxo_ativo = None
    if fluxo_slug and fluxo_slug != 'todos':
        for f in fluxos_list:
            if f['slug'] == fluxo_slug and f['nome'] != 'Todos':
                fluxo_ativo = f['nome']
                valor_fluxo = '' if f['nome'] == 'Sem fluxo' else f['nome']
                pattern = _fluxo_token_regex(valor_fluxo)
                filtro &= Q(fluxo__iregex=pattern)
                break
    if fluxo_slug == 'todos' or (not fluxo_slug and fluxos_list and fluxos_list[0]['nome'] == 'Todos'):
        fluxo_ativo = 'Todos'

    # Fila: mais antigo primeiro (ordem crescente de chegada)
    itens = Carregamento.objects.filter(filtro).order_by('criado_em', 'datahora_emissao')[:200]

    context = {
        'fluxos': fluxos_list,
        'fluxo_ativo': fluxo_ativo or (fluxos_list[0]['nome'] if fluxos_list else None),
        'fluxo_slug_ativo': fluxo_slug or (fluxos_list[0]['slug'] if fluxos_list else ''),
        'card_total_fila': card_total_fila,
        'cards_por_fluxo': cards_por_fluxo,
        'card_manifestados': card_manifestados,
        'itens': itens,
    }
    if request.GET.get('partial'):
        return render(request, 'fila/partials/fila_cards.html', context)
    return render(request, 'fila/fila.html', context)


@login_required
@require_menu_perm('fila')
def item_detail(request, pk):
    """Detalhe de um item da fila (para AJAX ou página)."""
    item = get_object_or_404(Carregamento, pk=pk)
    return render(request, 'fila/partials/item_detalhe.html', {'item': item})


def _xml_storage_key(item):
    """Retorna a chave do objeto XML no MinIO para este carregamento."""
    # Permite override via extra (n8n pode enviar o path usado no upload)
    for key in ('xml_key', 'xml_minio_key', 'xml_path'):
        val = item.extras.get(key) if item.extras else None
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    # Convenção padrão: carregamentos/{chave_acesso}-nfe.xml
    return f'carregamentos/{item.chave_acesso}-nfe.xml'


@login_required
@require_menu_perm('fila')
@require_GET
def item_download_xml(request, pk):
    """Faz download do XML do carregamento a partir do MinIO (django-storages + boto3)."""
    item = get_object_or_404(Carregamento, pk=pk)
    storage_key = _xml_storage_key(item)
    if not default_storage.exists(storage_key):
        raise Http404('Arquivo XML não encontrado no armazenamento.')
    f = default_storage.open(storage_key, 'rb')
    filename = f'nfe_{item.chave_acesso}.xml'
    try:
        return FileResponse(f, as_attachment=True, filename=filename)
    except Exception:
        if hasattr(f, 'close'):
            f.close()
        raise


@login_required
@require_menu_perm('fila')
@require_GET
def item_download_ost_pdf(request, pk):
    """
    PDF da OST vinculada ao carregamento (manifestado).
    ?inline=1 → abre para visualização no navegador (nova aba); sem parâmetro → download.
    """
    item = get_object_or_404(Carregamento, pk=pk)
    if not item.ost or not item.ost.pdf_storage_key:
        raise Http404('Nenhum PDF de OST vinculado a este item.')
    key = item.ost.pdf_storage_key
    if not default_storage.exists(key):
        raise Http404('Arquivo PDF da OST não encontrado no armazenamento.')
    f = default_storage.open(key, 'rb')
    filial = item.ost.filial or ''
    serie = item.ost.serie or ''
    doc = item.ost.documento or ''
    filename = f'ost_{filial}_{serie}_{doc}.pdf'.strip('_') or 'ost.pdf'
    inline = request.GET.get('inline') in ('1', 'true', 'yes')
    try:
        response = FileResponse(f, as_attachment=not inline, filename=filename)
        if inline:
            response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    except Exception:
        if hasattr(f, 'close'):
            f.close()
        raise


def _fluxo_to_slug(nome):
    if not nome:
        return 'sem-fluxo'
    # Remove acentos
    nome = unicodedata.normalize('NFKD', nome)
    nome = nome.encode('ascii', 'ignore').decode('ascii')
    return nome.lower().replace(' ', '-').replace('_', '-')


def _fluxo_token_regex(valor_fluxo):
    """Retorna padrão regex para match de valor_fluxo como token (ex.: 'Escória' em 'Escória, Pedágio')."""
    if not valor_fluxo:
        return r'^$'
    esc = re.escape(valor_fluxo.strip())
    return r'(^|,)\s*' + esc + r'\s*($|,)'


def _parse_date(s):
    """Retorna date ou None a partir de string YYYY-MM-DD."""
    if not s:
        return None
    try:
        from datetime import datetime
        return datetime.strptime(s.strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


@login_required
def home_view(request):
    """Dashboard: exibidores, gráficos e estatísticas dos carregamentos com filtro de período."""
    hoje = timezone.localdate()
    data_inicio = _parse_date(request.GET.get('data_inicio')) or hoje
    data_fim = _parse_date(request.GET.get('data_fim')) or hoje
    if data_fim < data_inicio:
        data_fim = data_inicio

    # Carregamentos que entraram no sistema no período (por criado_em)
    base_qs = Carregamento.objects.filter(
        criado_em__date__gte=data_inicio,
        criado_em__date__lte=data_fim,
    )

    total_periodo = base_qs.count()

    # Por fluxo (para gráfico pizza)
    from django.db.models import Sum
    fluxo_stats = (
        base_qs.values('fluxo')
        .annotate(total=Count('id'))
        .order_by('-total')
    )
    pie_fluxos = [
        {'label': (f['fluxo'] or 'Sem fluxo'), 'total': f['total']}
        for f in fluxo_stats
    ]

    # Peso por fluxo (gráfico de barras verticais)
    fluxo_peso = (
        base_qs.values('fluxo')
        .annotate(peso=Sum('qCom_peso'))
        .order_by('-peso')
    )
    peso_por_fluxo = [
        {'label': (f['fluxo'] or 'Sem fluxo'), 'peso': float(f['peso'] or 0)}
        for f in fluxo_peso
    ]

    # Manifestados no período (arquivados e manifestado_em no período)
    manifestados_no_periodo_qs = Carregamento.objects.filter(
        arquivado=True,
        manifestado_em__date__gte=data_inicio,
        manifestado_em__date__lte=data_fim,
    )
    total_manifestados_periodo = manifestados_no_periodo_qs.count()

    # Resumo de valores (peso) no período
    resumo_valores = base_qs.aggregate(soma_peso=Sum('qCom_peso'))
    soma_peso = resumo_valores['soma_peso'] or 0
    # Formato PT-BR: ponto como separador de milhares (ex: 1.234.567)
    soma_peso_formatado = f'{float(soma_peso):,.0f}'.replace(',', '.')

    context = {
        'data_inicio': data_inicio.isoformat(),
        'data_fim': data_fim.isoformat(),
        'hoje': hoje.isoformat(),
        'total_periodo': total_periodo,
        'total_manifestados_periodo': total_manifestados_periodo,
        'pie_fluxos': pie_fluxos,
        'peso_por_fluxo': peso_por_fluxo,
        'pie_fluxos_json': json.dumps(pie_fluxos),
        'peso_por_fluxo_json': json.dumps(peso_por_fluxo),
        'soma_peso_formatado': soma_peso_formatado,
    }
    return render(request, 'fila/home.html', context)


@login_required
@require_menu_perm('fila')
@require_POST
def item_manifestar_view(request, pk):
    """Marca o item como manifestado (arquivado). Retorna JSON para AJAX."""
    item = get_object_or_404(Carregamento, pk=pk)
    item.arquivado = True
    item.manifestado_por = request.user
    item.manifestado_em = timezone.now()
    item.save(update_fields=['arquivado', 'manifestado_por', 'manifestado_em', 'atualizado_em'])
    return JsonResponse({'ok': True})


@login_required
@require_menu_perm('fila')
def arquivados_view(request):
    """Lista de carregamentos manifestados com filtros (período, motorista, placa, fluxo, remetente, destinatário, nota fiscal)."""
    qs = Carregamento.objects.filter(arquivado=True).order_by('-manifestado_em', '-criado_em')

    # Filtros a partir dos parâmetros GET
    data_inicio = _parse_date(request.GET.get('data_inicio'))
    data_fim = _parse_date(request.GET.get('data_fim'))
    motorista = (request.GET.get('motorista') or '').strip()
    placa = (request.GET.get('placa') or '').strip()
    fluxo = (request.GET.get('fluxo') or '').strip()
    remetente = (request.GET.get('remetente') or '').strip()
    destinatario = (request.GET.get('destinatario') or '').strip()
    # Nota fiscal: uma ou várias separadas por vírgula
    nota_fiscal_raw = (request.GET.get('nota_fiscal') or '').strip()
    notas_fiscais = [x.strip() for x in nota_fiscal_raw.split(',') if x.strip()]

    if data_inicio:
        qs = qs.filter(Q(manifestado_em__date__gte=data_inicio) | Q(manifestado_em__isnull=True, criado_em__date__gte=data_inicio))
    if data_fim:
        qs = qs.filter(Q(manifestado_em__date__lte=data_fim) | Q(manifestado_em__isnull=True, criado_em__date__lte=data_fim))
    if motorista:
        qs = qs.filter(Q(extras__Motorista__icontains=motorista) | Q(extras__motorista__icontains=motorista))
    if placa:
        qs = qs.filter(Q(extras__Placa__icontains=placa) | Q(extras__placa__icontains=placa))
    if fluxo:
        qs = qs.filter(fluxo__icontains=fluxo)
    if remetente:
        qs = qs.filter(emit_nome__icontains=remetente)
    if destinatario:
        qs = qs.filter(dest_nome__icontains=destinatario)
    if notas_fiscais:
        qs = qs.filter(nota_fiscal__in=notas_fiscais)

    total_arquivados = Carregamento.objects.filter(arquivado=True).count()
    total_filtrado = qs.count()
    itens = qs[:500]

    context = {
        'itens': itens,
        'total_arquivados': total_arquivados,
        'total_filtrado': total_filtrado,
        'filtros': {
            'data_inicio': request.GET.get('data_inicio') or '',
            'data_fim': request.GET.get('data_fim') or '',
            'motorista': request.GET.get('motorista') or '',
            'placa': request.GET.get('placa') or '',
            'fluxo': request.GET.get('fluxo') or '',
            'remetente': request.GET.get('remetente') or '',
            'destinatario': request.GET.get('destinatario') or '',
            'nota_fiscal': request.GET.get('nota_fiscal') or '',
        },
    }
    return render(request, 'fila/arquivados.html', context)


def _lista_carregamentos_item_ost(ost):
    """Converte OST em item unificado para a tabela Lista de carregamentos."""
    from django.urls import reverse
    doc = ' / '.join(filter(None, [ost.filial or '', ost.serie or '', ost.documento or '']))
    if not doc:
        doc = '—'
    if ost.data_manifesto:
        data_display = ost.data_manifesto.strftime('%d/%m/%Y')
        if ost.hora_manifesto:
            data_display += ' ' + ost.hora_manifesto.strftime('%H:%M')
    else:
        data_display = ost.criado_em.strftime('%d/%m/%Y %H:%M') if ost.criado_em else '—'
    nf_display = ', '.join(str(x) for x in (ost.nota_fiscal or [])) if ost.nota_fiscal else '—'
    sort_date = ost.data_manifesto or (ost.criado_em.date() if ost.criado_em else None)
    sort_time = ost.hora_manifesto or (ost.criado_em.time() if ost.criado_em else None)
    return {
        'documento_display': doc,
        'data_display': data_display,
        'remetente': ost.remetente or '—',
        'destinatario': ost.destinatario or '—',
        'nota_fiscal_display': nf_display,
        'motorista': ost.motorista or '—',
        'placa_cavalo': ost.placa_cavalo or '—',
        'placa_carreta': ost.placa_carreta or '—',
        'produto_display': ost.produto or '—',
        'peso_display': ost.peso or '—',
        'tem_pdf': bool(ost.pdf_storage_key),
        'pdf_url': reverse('ost_download_pdf', args=[ost.pk]) + '?inline=1' if ost.pdf_storage_key else None,
        'sort_key': (sort_date, sort_time),
    }


def _lista_carregamentos_item_cte(cte):
    """Converte CTe em item unificado para a tabela Lista de carregamentos."""
    from django.urls import reverse
    doc = ' / '.join(filter(None, [cte.filial or '', cte.serie or '', cte.numero_cte or '']))
    if not doc:
        doc = '—'
    if cte.data_emissao:
        data_display = cte.data_emissao.strftime('%d/%m/%Y')
        if cte.hora_emissao:
            data_display += ' ' + cte.hora_emissao.strftime('%H:%M')
    else:
        data_display = cte.criado_em.strftime('%d/%m/%Y %H:%M') if cte.criado_em else '—'
    sort_date = cte.data_emissao or (cte.criado_em.date() if cte.criado_em else None)
    sort_time = cte.hora_emissao or (cte.criado_em.time() if cte.criado_em else None)
    return {
        'documento_display': doc,
        'data_display': data_display,
        'remetente': cte.remetente or '—',
        'destinatario': cte.destinatario or '—',
        'nota_fiscal_display': cte.nota_fiscal or '—',
        'motorista': cte.motorista or '—',
        'placa_cavalo': cte.placa_cavalo or '—',
        'placa_carreta': cte.placa_carreta or '—',
        'produto_display': cte.produto_predominante or '—',
        'peso_display': cte.peso_bruto or '—',
        'tem_pdf': bool(cte.pdf_storage_key),
        'pdf_url': reverse('cte_download_pdf', args=[cte.pk]) + '?inline=1' if cte.pdf_storage_key else None,
        'sort_key': (sort_date, sort_time),
    }


@login_required
@require_menu_perm('fila')
def lista_carregamentos_view(request):
    """Lista de OSTs e CT-es processados na mesma tabela (mesmos filtros)."""
    data_inicio = _parse_date(request.GET.get('data_inicio'))
    data_fim = _parse_date(request.GET.get('data_fim'))
    motorista = (request.GET.get('motorista') or '').strip()
    placa = (request.GET.get('placa') or '').strip()
    remetente = (request.GET.get('remetente') or '').strip()
    destinatario = (request.GET.get('destinatario') or '').strip()
    nota_fiscal_raw = (request.GET.get('nota_fiscal') or '').strip()
    notas_fiscais = [x.strip() for x in nota_fiscal_raw.split(',') if x.strip()]

    # OSTs
    qs_ost = OST.objects.filter(
        Q(filial__gt='') | Q(serie__gt='') | Q(documento__gt='')
    )
    if data_inicio:
        qs_ost = qs_ost.filter(
            Q(data_manifesto__gte=data_inicio) | Q(data_manifesto__isnull=True, criado_em__date__gte=data_inicio)
        )
    if data_fim:
        qs_ost = qs_ost.filter(
            Q(data_manifesto__lte=data_fim) | Q(data_manifesto__isnull=True, criado_em__date__lte=data_fim)
        )
    if motorista:
        qs_ost = qs_ost.filter(motorista__icontains=motorista)
    if placa:
        qs_ost = qs_ost.filter(Q(placa_cavalo__icontains=placa) | Q(placa_carreta__icontains=placa))
    if remetente:
        qs_ost = qs_ost.filter(remetente__icontains=remetente)
    if destinatario:
        qs_ost = qs_ost.filter(destinatario__icontains=destinatario)
    if notas_fiscais:
        q_nf = Q()
        for nf in notas_fiscais:
            q_nf |= Q(nota_fiscal__contains=[nf])
            try:
                q_nf |= Q(nota_fiscal__contains=[int(nf)])
            except ValueError:
                pass
        qs_ost = qs_ost.filter(q_nf)

    # CT-es
    qs_cte = CTe.objects.filter(
        Q(filial__gt='') | Q(serie__gt='') | Q(numero_cte__gt='')
    )
    if data_inicio:
        qs_cte = qs_cte.filter(
            Q(data_emissao__gte=data_inicio) | Q(data_emissao__isnull=True, criado_em__date__gte=data_inicio)
        )
    if data_fim:
        qs_cte = qs_cte.filter(
            Q(data_emissao__lte=data_fim) | Q(data_emissao__isnull=True, criado_em__date__lte=data_fim)
        )
    if motorista:
        qs_cte = qs_cte.filter(motorista__icontains=motorista)
    if placa:
        qs_cte = qs_cte.filter(Q(placa_cavalo__icontains=placa) | Q(placa_carreta__icontains=placa))
    if remetente:
        qs_cte = qs_cte.filter(remetente__icontains=remetente)
    if destinatario:
        qs_cte = qs_cte.filter(destinatario__icontains=destinatario)
    if notas_fiscais:
        q_nf_cte = Q()
        for nf in notas_fiscais:
            q_nf_cte |= Q(nota_fiscal__icontains=nf)
        qs_cte = qs_cte.filter(q_nf_cte)

    itens_raw = []
    for ost in qs_ost:
        itens_raw.append(_lista_carregamentos_item_ost(ost))
    for cte in qs_cte:
        itens_raw.append(_lista_carregamentos_item_cte(cte))

    # Ordenar por data/hora (mais recente primeiro)
    def _sort_key(x):
        d, t = x['sort_key']
        if d is None:
            return (1, 0, 0)
        secs = (t.hour * 3600 + t.minute * 60 + t.second) if t else 0
        return (0, -d.toordinal(), -secs)

    itens = sorted(itens_raw, key=_sort_key)
    for d in itens:
        d.pop('sort_key', None)

    total_osts = OST.objects.filter(
        Q(filial__gt='') | Q(serie__gt='') | Q(documento__gt='')
    ).count()
    total_ctes = CTe.objects.filter(
        Q(filial__gt='') | Q(serie__gt='') | Q(numero_cte__gt='')
    ).count()
    total_filtrado = len(itens)

    context = {
        'itens': itens,
        'total_osts': total_osts,
        'total_ctes': total_ctes,
        'total_filtrado': total_filtrado,
        'filtros': {
            'data_inicio': request.GET.get('data_inicio') or '',
            'data_fim': request.GET.get('data_fim') or '',
            'motorista': request.GET.get('motorista') or '',
            'placa': request.GET.get('placa') or '',
            'remetente': request.GET.get('remetente') or '',
            'destinatario': request.GET.get('destinatario') or '',
            'nota_fiscal': request.GET.get('nota_fiscal') or '',
        },
    }
    return render(request, 'fila/lista_carregamentos.html', context)


@login_required
@require_menu_perm('fila')
@require_GET
def ost_download_pdf(request, pk):
    """Download do PDF da OST por pk da OST. ?inline=1 para abrir no navegador."""
    ost = get_object_or_404(OST, pk=pk)
    if not ost.pdf_storage_key or not default_storage.exists(ost.pdf_storage_key):
        raise Http404('PDF desta OST não encontrado.')
    f = default_storage.open(ost.pdf_storage_key, 'rb')
    filial = ost.filial or ''
    serie = ost.serie or ''
    doc = ost.documento or ''
    filename = f'ost_{filial}_{serie}_{doc}.pdf'.strip('_') or 'ost.pdf'
    inline = request.GET.get('inline') in ('1', 'true', 'yes')
    try:
        response = FileResponse(f, as_attachment=not inline, filename=filename)
        if inline:
            response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    except Exception:
        if hasattr(f, 'close'):
            f.close()
        raise


@login_required
@require_menu_perm('fila')
@require_GET
def cte_download_pdf(request, pk):
    """Download do PDF do CT-e por pk do CTe. ?inline=1 para abrir no navegador."""
    cte = get_object_or_404(CTe, pk=pk)
    if not cte.pdf_storage_key or not default_storage.exists(cte.pdf_storage_key):
        raise Http404('PDF deste CT-e não encontrado.')
    f = default_storage.open(cte.pdf_storage_key, 'rb')
    filial = cte.filial or ''
    serie = cte.serie or ''
    num = cte.numero_cte or ''
    filename = f'cte_{filial}_{serie}_{num}.pdf'.strip('_') or 'cte.pdf'
    inline = request.GET.get('inline') in ('1', 'true', 'yes')
    try:
        response = FileResponse(f, as_attachment=not inline, filename=filename)
        if inline:
            response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    except Exception:
        if hasattr(f, 'close'):
            f.close()
        raise


def esqueci_senha_view(request):
    """Página 'Esqueceu a senha' – orienta a contactar o administrador."""
    return render(request, 'fila/esqueci_senha.html')


def solicitar_acesso_view(request):
    """Página 'Solicitar acesso' – orienta a contactar o administrador."""
    return render(request, 'fila/solicitar_acesso.html')


def _parse_numero_ost(numero_ost):
    """Separa numero_ost em filial, série, documento (ex.: 16.001.12345 ou 16-001-12345)."""
    if not numero_ost or not isinstance(numero_ost, str):
        return '', '', ''
    s = numero_ost.strip()
    parts = re.split(r'[.\-/]', s, maxsplit=2)
    filial = parts[0] if len(parts) > 0 else ''
    serie = parts[1] if len(parts) > 1 else ''
    documento = parts[2] if len(parts) > 2 else ''
    return filial, serie, documento


def _parse_data_manifesto(s):
    """Converte 'dd/mm/yyyy' em date ou None."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    try:
        return datetime.strptime(s, '%d/%m/%Y').date()
    except ValueError:
        return None


def _parse_hora_manifesto(s):
    """Converte 'hh:mm:ss' ou 'hh:mm' em time ou None."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def _dados_ost_para_model(d):
    """Converte um dicionário do extrator para atributos do model OST."""
    filial, serie, documento = _parse_numero_ost(d.get('numero_ost'))
    nf_raw = d.get('nf_ticket')
    if isinstance(nf_raw, str) and ' + ' in nf_raw:
        nota_fiscal = [x.strip() for x in nf_raw.split(' + ') if x.strip()]
    elif nf_raw:
        nota_fiscal = [str(nf_raw)]
    else:
        nota_fiscal = []
    return {
        'filial': filial,
        'serie': serie,
        'documento': documento,
        'data_manifesto': _parse_data_manifesto(d.get('data_averbacao')),
        'hora_manifesto': _parse_hora_manifesto(d.get('hora_averbacao')),
        'remetente': (d.get('remetente') or '')[:300],
        'destinatario': (d.get('destinatario') or '')[:300],
        'motorista': (d.get('motorista') or '')[:200],
        'placa_cavalo': (d.get('placa_1') or '')[:10],
        'placa_carreta': (d.get('placa_2') or '')[:10],
        'total_frete': (d.get('total_frete') or '')[:50],
        'pedagio': (d.get('pedagio') or '')[:50],
        'valor_tarifa_empresa': (d.get('valor_tarifa') or '')[:50],
        'produto': (d.get('produto') or '')[:500] if d.get('produto') else '',
        'peso': (d.get('peso') or '')[:50],
        'nota_fiscal': nota_fiscal,
        'data_nf': (d.get('data_nf') or '')[:500],
        'chave_acesso': (d.get('chave_nf') or '')[:50],
    }


def _demembrar_e_enviar_pagina_minio(content: bytes, page_index: int, upload_id: str) -> str:
    """Gera PDF de uma única página e salva no MinIO. Retorna a chave do objeto."""
    reader = PdfReader(BytesIO(content))
    writer = PdfWriter()
    writer.add_page(reader.pages[page_index])
    buf = BytesIO()
    writer.write(buf)
    buf.seek(0)
    key = f'ost/{upload_id}/{page_index}.pdf'
    default_storage.save(key, buf)
    return key


def _encontrar_ost_existente(filial, serie, documento, nota_fiscal):
    """Retorna OST existente com mesmo documento (filial/série/documento) e mesma lista de nota fiscal, ou None."""
    if not documento and not (filial or serie):
        return None
    qs = OST.objects.filter(filial=filial or '', serie=serie or '', documento=documento or '')
    nf_norm = sorted(str(x) for x in (nota_fiscal or []))
    for ost in qs:
        ost_nf = sorted(str(x) for x in (ost.nota_fiscal or []))
        if ost_nf == nf_norm:
            return ost
    return None


def _dados_cte_para_model(d):
    """Converte um dicionário do extrator CT-e para atributos do model CTe."""
    def _trunc(s, n):
        return (s or '')[:n] if s else ''
    return {
        'filial': _trunc(d.get('filial'), 20),
        'serie': _trunc(d.get('serie'), 20),
        'numero_cte': _trunc(d.get('numero_cte'), 50),
        'data_emissao': _parse_data_manifesto(d.get('data_emissao')),
        'hora_emissao': _parse_hora_manifesto(d.get('hora_emissao')),
        'remetente': _trunc(d.get('remetente'), 500),
        'municipio_remetente': _trunc(d.get('municipio_remetente'), 200),
        'destinatario': _trunc(d.get('destinatario'), 500),
        'municipio_destinatario': _trunc(d.get('municipio_destinatario'), 200),
        'produto_predominante': _trunc(d.get('produto_predominante'), 500),
        'vlr_tarifa': _trunc(d.get('vlr_tarifa'), 50),
        'peso_bruto': _trunc(d.get('peso_bruto'), 50),
        'frete_peso': _trunc(d.get('frete_peso'), 50),
        'pedagio': _trunc(d.get('pedagio'), 50),
        'valor_total': _trunc(d.get('valor_total'), 50),
        'serie_nf': _trunc(d.get('serie_nf'), 20),
        'nota_fiscal': _trunc(d.get('nota_fiscal'), 50),
        'chave_nfe': _trunc(d.get('chave_nfe'), 44),
        'dt': _trunc(d.get('dt'), 100),
        'cnpj_proprietario': _trunc(d.get('cnpj_proprietario'), 30),
        'placa_cavalo': _trunc(d.get('placa_cavalo'), 10),
        'placa_carreta': _trunc(d.get('placa_carreta'), 10),
        'motorista': _trunc(d.get('motorista'), 200),
    }


def _demembrar_e_enviar_pagina_minio_cte(content: bytes, page_index: int, upload_id: str) -> str:
    """Gera PDF de uma única página e salva no MinIO (pasta ctes/). Retorna a chave do objeto."""
    reader = PdfReader(BytesIO(content))
    writer = PdfWriter()
    writer.add_page(reader.pages[page_index])
    buf = BytesIO()
    writer.write(buf)
    buf.seek(0)
    key = f'ctes/{upload_id}/{page_index}.pdf'
    default_storage.save(key, buf)
    return key


def _encontrar_cte_existente(filial, serie, numero_cte):
    """Retorna CTe existente com mesmo filial/série/numero_cte, ou None."""
    if not (filial or serie or numero_cte):
        return None
    return CTe.objects.filter(
        filial=filial or '', serie=serie or '', numero_cte=numero_cte or ''
    ).first()


@login_required
@require_menu_perm('processador')
def processador_view(request):
    """Processador de PDFs: CTe, OST, Contratos. OST: extrai dados, demembra PDF (1 página = 1 arquivo) e salva no MinIO.
    Anti-duplicata: mesmo documento + mesma nota fiscal não cria novo registro; se já existir OST com PDF, não sobrescreve.
    Se existir OST sem PDF, atualiza com o PDF e dados extraídos."""
    if request.method == 'POST':
        if (request.FILES.get('ost_pdf') or request.FILES.get('cte_pdf')) and (not PdfReader or not PdfWriter):
            messages.error(request, 'Biblioteca pypdf não disponível para demembrar os PDFs.')
            return redirect('processador')

        ost_file = request.FILES.get('ost_pdf')
        if ost_file and ost_file.name.lower().endswith('.pdf'):
            try:
                content = b''.join(ost_file.chunks())
                upload_id = uuid.uuid4().hex
                extrator = ExtratorOST(BytesIO(content))
                criados = 0
                atualizados = 0
                ignorados_duplicata = 0
                for page_index, records in extrator.processar_pdf_por_pagina():
                    key = _demembrar_e_enviar_pagina_minio(content, page_index, upload_id)
                    for d in records:
                        attrs = _dados_ost_para_model(d)
                        attrs['pdf_storage_key'] = key
                        existente = _encontrar_ost_existente(
                            attrs['filial'], attrs['serie'], attrs['documento'], attrs['nota_fiscal']
                        )
                        if existente:
                            if existente.pdf_storage_key:
                                ignorados_duplicata += 1
                                continue
                            for k, v in attrs.items():
                                setattr(existente, k, v)
                            existente.save()
                            atualizados += 1
                        else:
                            OST.objects.create(**attrs)
                            criados += 1
                partes = []
                if criados:
                    partes.append(f'{criados} criado(s)')
                if atualizados:
                    partes.append(f'{atualizados} atualizado(s) com PDF')
                if ignorados_duplicata:
                    partes.append(f'{ignorados_duplicata} duplicata(s) ignorada(s)')
                msg = f'OST: {"; ".join(partes)}. PDFs em ost/{upload_id}/.' if partes else f'OST: nenhum registro novo. {ignorados_duplicata} duplicata(s). PDFs em ost/{upload_id}/.'
                messages.success(request, msg)
            except Exception as e:
                messages.error(request, f'Erro ao processar PDF OST: {e}')
        elif ost_file:
            messages.warning(request, 'Envie um arquivo PDF para OST.')

        # --- CT-e ---
        cte_file = request.FILES.get('cte_pdf')
        if cte_file and cte_file.name.lower().endswith('.pdf'):
            try:
                content = b''.join(cte_file.chunks())
                upload_id = uuid.uuid4().hex
                extrator = ExtratorCTe(BytesIO(content))
                criados = 0
                atualizados = 0
                ignorados_duplicata = 0
                for page_index, records in extrator.processar_pdf_por_pagina():
                    key = _demembrar_e_enviar_pagina_minio_cte(content, page_index, upload_id)
                    for d in records:
                        attrs = _dados_cte_para_model(d)
                        attrs['pdf_storage_key'] = key
                        existente = _encontrar_cte_existente(
                            attrs['filial'], attrs['serie'], attrs['numero_cte']
                        )
                        if existente:
                            if existente.pdf_storage_key:
                                ignorados_duplicata += 1
                                continue
                            for k, v in attrs.items():
                                setattr(existente, k, v)
                            existente.save()
                            atualizados += 1
                        else:
                            CTe.objects.create(**attrs)
                            criados += 1
                partes = []
                if criados:
                    partes.append(f'{criados} criado(s)')
                if atualizados:
                    partes.append(f'{atualizados} atualizado(s) com PDF')
                if ignorados_duplicata:
                    partes.append(f'{ignorados_duplicata} duplicata(s) ignorada(s)')
                msg = f'CT-e: {"; ".join(partes)}. PDFs em ctes/{upload_id}/.' if partes else f'CT-e: nenhum registro novo. {ignorados_duplicata} duplicata(s). PDFs em ctes/{upload_id}/.'
                messages.success(request, msg)
            except Exception as e:
                messages.error(request, f'Erro ao processar PDF CT-e: {e}')
        elif cte_file:
            messages.warning(request, 'Envie um arquivo PDF para CT-e.')

        return redirect('processador')
    return render(request, 'fila/processador.html')
