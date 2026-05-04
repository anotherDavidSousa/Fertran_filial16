import json
from django.contrib.auth import logout
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.core.files.storage import default_storage
from django.http import Http404, FileResponse
from django.db.models import Q, Count
from django.utils import timezone

from .models import OST, CTe
from .menu_perms import require_menu_perm


def logout_view(request):
    logout(request)
    return render(request, 'login.html', {'mensagem': 'Você saiu do sistema.'})


def _parse_date(s):
    if not s:
        return None
    from datetime import date as _date
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            pass
    return None


# ── Home / Dashboard ──────────────────────────────────────────────────────────

@login_required
def home_view(request):
    return redirect('core:cavalo_list')


# ── Lista de Carregamentos (OST + CTe) ────────────────────────────────────────

def _lista_carregamentos_item_ost(ost):
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
    """Lista de OSTs e CT-es processados na mesma tabela."""
    data_inicio = _parse_date(request.GET.get('data_inicio'))
    data_fim = _parse_date(request.GET.get('data_fim'))
    motorista = (request.GET.get('motorista') or '').strip()
    placa = (request.GET.get('placa') or '').strip()
    remetente = (request.GET.get('remetente') or '').strip()
    destinatario = (request.GET.get('destinatario') or '').strip()
    nota_fiscal_raw = (request.GET.get('nota_fiscal') or '').strip()
    notas_fiscais = [x.strip() for x in nota_fiscal_raw.split(',') if x.strip()]

    # Só executa as queries se pelo menos um filtro estiver ativo
    filtro_ativo = bool(data_inicio or data_fim or motorista or placa or remetente or destinatario or notas_fiscais)

    if filtro_ativo:
        qs_ost = OST.objects.filter(Q(filial__gt='') | Q(serie__gt='') | Q(documento__gt=''))
        if data_inicio:
            qs_ost = qs_ost.filter(Q(data_manifesto__gte=data_inicio) | Q(data_manifesto__isnull=True, criado_em__date__gte=data_inicio))
        if data_fim:
            qs_ost = qs_ost.filter(Q(data_manifesto__lte=data_fim) | Q(data_manifesto__isnull=True, criado_em__date__lte=data_fim))
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

        qs_cte = CTe.objects.filter(Q(filial__gt='') | Q(serie__gt='') | Q(numero_cte__gt=''))
        if data_inicio:
            qs_cte = qs_cte.filter(Q(data_emissao__gte=data_inicio) | Q(data_emissao__isnull=True, criado_em__date__gte=data_inicio))
        if data_fim:
            qs_cte = qs_cte.filter(Q(data_emissao__lte=data_fim) | Q(data_emissao__isnull=True, criado_em__date__lte=data_fim))
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

        itens_raw = [_lista_carregamentos_item_ost(o) for o in qs_ost]
        itens_raw += [_lista_carregamentos_item_cte(c) for c in qs_cte]

        def _sort_key(x):
            d, t = x['sort_key']
            if d is None:
                return (1, 0, 0)
            secs = (t.hour * 3600 + t.minute * 60 + t.second) if t else 0
            return (0, -d.toordinal(), -secs)

        itens = sorted(itens_raw, key=_sort_key)
        for d in itens:
            d.pop('sort_key', None)
    else:
        itens = []

    total_osts = OST.objects.filter(Q(filial__gt='') | Q(serie__gt='') | Q(documento__gt='')).count()
    total_ctes = CTe.objects.filter(Q(filial__gt='') | Q(serie__gt='') | Q(numero_cte__gt='')).count()

    context = {
        'itens': itens,
        'filtro_ativo': filtro_ativo,
        'total_osts': total_osts,
        'total_ctes': total_ctes,
        'total_filtrado': len(itens),
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
    """Download do PDF da OST. ?inline=1 para abrir no navegador."""
    ost = get_object_or_404(OST, pk=pk)
    if not ost.pdf_storage_key or not default_storage.exists(ost.pdf_storage_key):
        raise Http404('PDF desta OST nao encontrado.')
    f = default_storage.open(ost.pdf_storage_key, 'rb')
    filename = ('ost_%s_%s_%s.pdf' % (ost.filial or '', ost.serie or '', ost.documento or '')).strip('_') or 'ost.pdf'
    inline = request.GET.get('inline') in ('1', 'true', 'yes')
    try:
        response = FileResponse(f, as_attachment=not inline, filename=filename)
        if inline:
            response['Content-Disposition'] = 'inline; filename="%s"' % filename
        return response
    except Exception:
        if hasattr(f, 'close'):
            f.close()
        raise


@login_required
@require_menu_perm('fila')
@require_GET
def cte_download_pdf(request, pk):
    """Download do PDF do CT-e. ?inline=1 para abrir no navegador."""
    cte = get_object_or_404(CTe, pk=pk)
    if not cte.pdf_storage_key or not default_storage.exists(cte.pdf_storage_key):
        raise Http404('PDF deste CT-e nao encontrado.')
    f = default_storage.open(cte.pdf_storage_key, 'rb')
    filename = ('cte_%s_%s_%s.pdf' % (cte.filial or '', cte.serie or '', cte.numero_cte or '')).strip('_') or 'cte.pdf'
    inline = request.GET.get('inline') in ('1', 'true', 'yes')
    try:
        response = FileResponse(f, as_attachment=not inline, filename=filename)
        if inline:
            response['Content-Disposition'] = 'inline; filename="%s"' % filename
        return response
    except Exception:
        if hasattr(f, 'close'):
            f.close()
        raise


def esqueci_senha_view(request):
    return render(request, 'fila/esqueci_senha.html')


def solicitar_acesso_view(request):
    return render(request, 'fila/solicitar_acesso.html')


@login_required
@require_menu_perm('processador')
def processador_view(request):
    return render(request, 'fila/processador.html')
