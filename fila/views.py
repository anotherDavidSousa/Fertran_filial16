from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count, Q
from django.http import JsonResponse, FileResponse, Http404
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from .menu_perms import require_menu_perm
from django.core.files.storage import default_storage
from .models import Carregamento, OST, CTe
import json
import re
import unicodedata
from datetime import datetime


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




@login_required
@require_menu_perm('processador')
def processador_view(request):
    """OST/CT-e: processamento via n8n + API JSON (ver processador.html)."""
    return render(request, 'fila/processador.html')
