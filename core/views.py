from django.shortcuts import render, redirect, get_object_or_404
from django.db import models
from django.db.models import Q, Count, Case, When, Value, IntegerField, F, CharField
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate
from fila.menu_perms import require_menu_perm
from django.contrib import messages
from datetime import datetime, date
from decimal import Decimal
from calendar import monthrange
from django.http import FileResponse, Http404
from django.core.files.storage import default_storage
import os

from .models import (
    Proprietario,
    Gestor,
    Cavalo,
    Carreta,
    Motorista,
    LogCarreta,
    HistoricoGestor,
    CavaloDocumento,
    CarretaDocumento,
    ProprietarioDocumento,
    MotoristaDocumento,
)


def _abrir_arquivo_storage_or_404(key: str):
    """Abre um arquivo salvo no storage padrão (MinIO) ou gera 404."""
    if not key:
        raise Http404('Arquivo não encontrado.')
    if not default_storage.exists(key):
        raise Http404('Arquivo não encontrado.')
    return default_storage.open(key, 'rb')


def _file_response_from_storage(key: str, filename_base: str, request):
    f = _abrir_arquivo_storage_or_404(key)
    filename = filename_base or os.path.basename(key) or 'arquivo.pdf'
    inline = request.GET.get('inline') in ('1', 'true', 'yes')
    response = FileResponse(f, as_attachment=not inline, filename=filename)
    if inline:
        response['Content-Disposition'] = f'inline; filename=\"{filename}\"'
    return response


@login_required
@require_menu_perm('agregamento')
def index(request):
    parceiros_ativos = Proprietario.objects.filter(status='sim').count()
    total_cavalos = Cavalo.objects.exclude(carreta__isnull=True).count()
    total_carretas = Carreta.objects.count()
    carretas_disponiveis = Carreta.objects.exclude(
        id__in=Cavalo.objects.exclude(carreta__isnull=True).values_list('carreta_id', flat=True)
    ).count()
    veiculos_escoria = Cavalo.objects.filter(fluxo='escoria', carreta__isnull=False).count()
    veiculos_minerio = Cavalo.objects.filter(fluxo='minerio', carreta__isnull=False).count()
    outros_fluxos = Cavalo.objects.filter(carreta__isnull=False).filter(
        Q(fluxo__isnull=True) | Q(fluxo='') | ~Q(fluxo__in=['escoria', 'minerio'])
    ).count()
    context = {
        'parceiros_ativos': parceiros_ativos,
        'total_cavalos': total_cavalos,
        'total_carretas': total_carretas,
        'carretas_disponiveis': carretas_disponiveis,
        'veiculos_escoria': veiculos_escoria,
        'veiculos_minerio': veiculos_minerio,
        'outros_fluxos': outros_fluxos,
    }
    return render(request, 'core/index.html', context)


# ─── Proprietários ─────────────────────────────────────────────────────
@login_required
@require_menu_perm('agregamento')
def proprietario_list(request):
    for p in Proprietario.objects.all():
        p.atualizar_status_automatico()
    data_inicio = request.GET.get('data_inicio', '')
    data_fim = request.GET.get('data_fim', '')
    parceiros_ativos = Proprietario.objects.filter(status='sim').prefetch_related('cavalos').annotate(
        cavalos_com_carreta_count=Count('cavalos', filter=Q(cavalos__carreta__isnull=False))
    ).filter(cavalos_com_carreta_count__gt=0)
    dados_parceiros = []
    for parceiro in parceiros_ativos:
        cavalos_com_carreta = list(parceiro.cavalos.filter(carreta__isnull=False, situacao='ativo').order_by('placa')[:3])
        if not cavalos_com_carreta:
            continue
        cavalos_data = []
        placas_cavalos = []
        for cavalo in cavalos_com_carreta[:3]:
            if cavalo.placa:
                cavalos_data.append({'placa': cavalo.placa, 'id': cavalo.pk})
                placas_cavalos.append(cavalo.placa.upper().strip())
        while len(cavalos_data) < 3:
            cavalos_data.append({'placa': '', 'id': None})
        faturamento_total = Decimal('0.00')
        whatsapp_limpo = (parceiro.whatsapp or '').replace(' ', '').replace('(', '').replace(')', '').replace('-', '')
        dados_parceiros.append({
            'parceiro': parceiro,
            'cavalo_1': cavalos_data[0],
            'cavalo_2': cavalos_data[1],
            'cavalo_3': cavalos_data[2],
            'whatsapp_limpo': whatsapp_limpo,
            'faturamento_total': faturamento_total,
        })
    return render(request, 'core/proprietario_list.html', {
        'dados_parceiros': dados_parceiros,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
    })


@login_required
@require_menu_perm('agregamento')
def proprietario_detail(request, pk):
    proprietario = get_object_or_404(Proprietario, pk=pk)
    cavalos = proprietario.cavalos.all()
    return render(request, 'core/proprietario_detail.html', {'proprietario': proprietario, 'cavalos': cavalos})


@login_required
@require_menu_perm('agregamento')
def proprietario_download_documento(request, pk):
    proprietario = get_object_or_404(Proprietario, pk=pk)
    if not proprietario.documento:
        raise Http404('Documento não encontrado.')
    key = proprietario.documento.name
    filename_base = f'proprietario_{proprietario.codigo or proprietario.pk}.pdf'
    return _file_response_from_storage(key, filename_base, request)


@login_required
@require_menu_perm('agregamento')
def proprietario_download_documento_extra(request, pk):
    doc = get_object_or_404(ProprietarioDocumento, pk=pk)
    if not doc.arquivo:
        raise Http404('Documento não encontrado.')
    key = doc.arquivo.name
    filename_base = os.path.basename(key)
    return _file_response_from_storage(key, filename_base, request)


@login_required
@require_menu_perm('agregamento')
def proprietario_remover_documento(request, pk):
    if request.method != 'POST':
        return redirect('core:proprietario_detail', pk=pk)
    proprietario = get_object_or_404(Proprietario, pk=pk)
    if proprietario.documento:
        proprietario.documento.delete(save=True)
        messages.success(request, 'Documento removido e excluído do armazenamento.')
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and next_url.startswith('/') and len(next_url) > 1:
        return redirect(next_url)
    return redirect('core:proprietario_detail', pk=proprietario.pk)


@login_required
@require_menu_perm('agregamento')
def proprietario_remover_documento_extra(request, pk):
    if request.method != 'POST':
        doc = get_object_or_404(ProprietarioDocumento, pk=pk)
        return redirect('core:proprietario_detail', pk=doc.proprietario_id)
    doc = get_object_or_404(ProprietarioDocumento, pk=pk)
    proprietario_pk = doc.proprietario_id
    if doc.arquivo:
        doc.arquivo.delete(save=False)
    doc.delete()
    messages.success(request, 'Documento anexado removido e excluído do armazenamento.')
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and next_url.startswith('/') and len(next_url) > 1:
        return redirect(next_url)
    return redirect('core:proprietario_detail', pk=proprietario_pk)


@login_required
@require_menu_perm('agregamento')
def proprietario_create(request):
    if request.method == 'POST':
        codigo = request.POST.get('codigo', '').strip() or None
        proprietario = Proprietario.objects.create(
            codigo=codigo,
            nome_razao_social=request.POST.get('nome_razao_social', ''),
            tipo=request.POST.get('tipo', ''),
            status=request.POST.get('status', 'sim'),
            whatsapp=request.POST.get('whatsapp', ''),
            observacoes=request.POST.get('observacoes', ''),
            documento=request.FILES.get('documento'),
        )
        proprietario.atualizar_status_automatico()
        for f in request.FILES.getlist('documentos_extras'):
            ProprietarioDocumento.objects.create(proprietario=proprietario, arquivo=f)
        return redirect('core:proprietario_detail', pk=proprietario.pk)
    return render(request, 'core/proprietario_form.html', {'form_type': 'create'})


@login_required
@require_menu_perm('agregamento')
def proprietario_edit(request, pk):
    proprietario = get_object_or_404(Proprietario, pk=pk)
    if request.method == 'POST':
        proprietario.codigo = request.POST.get('codigo', '').strip() or None
        proprietario.nome_razao_social = request.POST.get('nome_razao_social', '')
        proprietario.tipo = request.POST.get('tipo', '')
        proprietario.status = request.POST.get('status', 'sim')
        proprietario.whatsapp = request.POST.get('whatsapp', '')
        proprietario.observacoes = request.POST.get('observacoes', '')
        if 'documento' in request.FILES:
            proprietario.documento = request.FILES['documento']
        proprietario.save()
        for f in request.FILES.getlist('documentos_extras'):
            ProprietarioDocumento.objects.create(proprietario=proprietario, arquivo=f)
        proprietario.atualizar_status_automatico()
        return redirect('core:proprietario_detail', pk=proprietario.pk)
    return render(request, 'core/proprietario_form.html', {'proprietario': proprietario, 'form_type': 'edit'})


# ─── Cavalos ───────────────────────────────────────────────────────────
@login_required
@require_menu_perm('cavalos')
def cavalo_list(request):
    # Apenas cavalos Ativos com carreta acoplada (template Cavalos)
    cavalos = Cavalo.objects.select_related('motorista', 'carreta', 'gestor').filter(
        situacao='ativo', carreta__isnull=False
    )
    from django.db import transaction
    with transaction.atomic():
        for cavalo in cavalos.filter(motorista__isnull=True):
            cavalo.situacao = 'parado'
            cavalo.save(update_fields=['situacao'])
    situacao_filter = request.GET.get('situacao', '')
    tipo_filter = request.GET.get('tipo', '')
    fluxo_filter = request.GET.get('fluxo', '')
    if situacao_filter:
        cavalos = cavalos.filter(situacao=situacao_filter)
    if tipo_filter:
        cavalos = cavalos.filter(tipo=tipo_filter)
    if fluxo_filter:
        cavalos = cavalos.filter(fluxo=fluxo_filter)
    # Ordem: 1.Classificação (Agregados, Frotas, Terceiros) 2.Situação (Ativo, Parado) 3.Fluxo (escória, minério, None) 4.Tipo (Toco, Trucado, Bi-truck) 5.Motorista (A-Z)
    cavalos = cavalos.annotate(
        ordem_classificacao=Case(
            When(classificacao='agregado', then=Value(0)),
            When(classificacao='frota', then=Value(1)),
            When(classificacao='terceiro', then=Value(2)),
            default=Value(0),
            output_field=IntegerField(),
        ),
        ordem_situacao=Case(
            When(situacao='ativo', then=Value(0)),
            When(situacao='parado', then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        ),
        ordem_fluxo=Case(
            When(fluxo='escoria', then=Value(0)),
            When(fluxo='minerio', then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        ),
        ordem_tipo=Case(
            When(tipo='toco', then=Value(0)),
            When(tipo='trucado', then=Value(1)),
            When(tipo='bi_truck', then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        ),
        motorista_nome_ordem=Case(
            When(motorista__isnull=False, then=F('motorista__nome')),
            default=Value(''),
            output_field=CharField(),
        ),
    ).order_by('ordem_classificacao', 'ordem_situacao', 'ordem_fluxo', 'ordem_tipo', 'motorista_nome_ordem')
    todos_cavalos_agregados = Cavalo.objects.filter(Q(classificacao='agregado') | Q(classificacao__isnull=True))
    return render(request, 'core/cavalo_list.html', {
        'cavalos': cavalos,
        'situacao_filter': situacao_filter,
        'tipo_filter': tipo_filter,
        'fluxo_filter': fluxo_filter,
        'contador_trucado': todos_cavalos_agregados.filter(tipo='trucado').count(),
        'contador_toco': todos_cavalos_agregados.filter(tipo='toco').count(),
        'contador_parado': todos_cavalos_agregados.filter(Q(situacao='parado') | Q(situacao='desagregado')).count(),
        'contador_escoria': todos_cavalos_agregados.filter(fluxo='escoria').count(),
        'contador_minerio': todos_cavalos_agregados.filter(fluxo='minerio').count(),
    })


@login_required
@require_menu_perm('cavalos')
def cavalo_detail(request, pk):
    cavalo = get_object_or_404(
        Cavalo.objects.select_related('proprietario', 'gestor', 'carreta', 'motorista').prefetch_related('documentos_extras'),
        pk=pk
    )
    logs = cavalo.logs.all()[:10]
    return render(request, 'core/cavalo_detail.html', {'cavalo': cavalo, 'logs': logs})


@login_required
@require_menu_perm('cavalos')
def cavalo_download_documento(request, pk):
    cavalo = get_object_or_404(Cavalo, pk=pk)
    if not cavalo.documento:
        raise Http404('Documento não encontrado.')
    key = cavalo.documento.name
    filename_base = f'cavalo_{cavalo.placa or cavalo.pk}.pdf'
    return _file_response_from_storage(key, filename_base, request)


@login_required
@require_menu_perm('cavalos')
def cavalo_download_documento_extra(request, pk):
    doc = get_object_or_404(CavaloDocumento, pk=pk)
    if not doc.arquivo:
        raise Http404('Documento não encontrado.')
    key = doc.arquivo.name
    filename_base = os.path.basename(key)
    return _file_response_from_storage(key, filename_base, request)


@login_required
@require_menu_perm('cavalos')
def cavalo_remover_documento(request, pk):
    if request.method != 'POST':
        return redirect('core:cavalo_detail', pk=pk)
    cavalo = get_object_or_404(Cavalo, pk=pk)
    if cavalo.documento:
        cavalo.documento.delete(save=True)
        messages.success(request, 'Documento principal removido e excluído do armazenamento.')
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and next_url.startswith('/') and len(next_url) > 1:
        return redirect(next_url)
    return redirect('core:cavalo_detail', pk=cavalo.pk)


@login_required
@require_menu_perm('cavalos')
def cavalo_remover_documento_extra(request, pk):
    if request.method != 'POST':
        doc = get_object_or_404(CavaloDocumento, pk=pk)
        return redirect('core:cavalo_detail', pk=doc.cavalo_id)
    doc = get_object_or_404(CavaloDocumento, pk=pk)
    cavalo_pk = doc.cavalo_id
    if doc.arquivo:
        doc.arquivo.delete(save=False)
    doc.delete()
    messages.success(request, 'Documento anexado removido e excluído do armazenamento.')
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and next_url.startswith('/') and len(next_url) > 1:
        return redirect(next_url)
    return redirect('core:cavalo_detail', pk=cavalo_pk)


def _cavalo_form_context(cavalo=None, form_type='create'):
    proprietarios = Proprietario.objects.all()
    gestores = Gestor.objects.all()
    motoristas = Motorista.objects.all().order_by('nome')
    carretas_acopladas_ids = Cavalo.objects.exclude(carreta__isnull=True).values_list('carreta_id', flat=True)
    if cavalo:
        carretas_acopladas_ids = Cavalo.objects.exclude(carreta__isnull=True).exclude(pk=cavalo.pk).values_list('carreta_id', flat=True)
    carretas_disponiveis = Carreta.objects.exclude(id__in=carretas_acopladas_ids)
    if cavalo and cavalo.carreta:
        carretas_disponiveis = carretas_disponiveis | Carreta.objects.filter(pk=cavalo.carreta.pk)
    return {
        'cavalo': cavalo,
        'form_type': form_type,
        'proprietarios': proprietarios,
        'gestores': gestores,
        'motoristas': motoristas,
        'carretas_disponiveis': carretas_disponiveis,
    }


@login_required
@require_menu_perm('cavalos')
def cavalo_create(request):
    if request.method == 'POST':
        cavalo = Cavalo.objects.create(
            placa=request.POST.get('placa', ''),
            ano=request.POST.get('ano') or None,
            cor=request.POST.get('cor', ''),
            fluxo=request.POST.get('fluxo', ''),
            tipo=request.POST.get('tipo', ''),
            classificacao=request.POST.get('classificacao', ''),
            situacao=request.POST.get('situacao', ''),
            proprietario_id=request.POST.get('proprietario') or None,
            gestor_id=request.POST.get('gestor') or None,
            observacoes=request.POST.get('observacoes', ''),
            emissao_laudo=request.POST.get('emissao_laudo') or None,
            documento=request.FILES.get('documento'),
        )
        if 'foto' in request.FILES:
            cavalo.foto = request.FILES['foto']
        if cavalo.tipo != 'bi_truck':
            carreta_id = request.POST.get('carreta') or None
            if carreta_id and carreta_id != 's_placa':
                try:
                    carreta = Carreta.objects.get(pk=carreta_id)
                    if cavalo.classificacao and carreta.classificacao and cavalo.classificacao != carreta.classificacao:
                        messages.error(request, f'Erro: A carreta selecionada é de "{carreta.get_classificacao_display()}" mas o cavalo é "{cavalo.get_classificacao_display()}". Eles devem ter a mesma classificação.')
                        return render(request, 'core/cavalo_form.html', _cavalo_form_context(None, 'create'))
                    cavalo.carreta = carreta
                except Carreta.DoesNotExist:
                    pass
        motorista_id = request.POST.get('motorista') or None
        if motorista_id:
            try:
                motorista = Motorista.objects.get(pk=motorista_id)
                if motorista.cavalo and motorista.cavalo.pk != cavalo.pk:
                    motorista.cavalo = None
                    motorista.save()
                motorista.cavalo = cavalo
                motorista.save()
            except Motorista.DoesNotExist:
                pass
        cavalo.save()
        for f in request.FILES.getlist('documentos_extras'):
            CavaloDocumento.objects.create(cavalo=cavalo, arquivo=f)
        return redirect('core:cavalo_detail', pk=cavalo.pk)
    return render(request, 'core/cavalo_form.html', _cavalo_form_context(None, 'create'))


@login_required
@require_menu_perm('cavalos')
def cavalo_edit(request, pk):
    cavalo = get_object_or_404(Cavalo, pk=pk)
    if request.method == 'POST':
        cavalo.placa = request.POST.get('placa', '')
        cavalo.ano = request.POST.get('ano') or None
        cavalo.cor = request.POST.get('cor', '')
        cavalo.fluxo = request.POST.get('fluxo', '')
        cavalo.tipo = request.POST.get('tipo', '')
        cavalo.classificacao = request.POST.get('classificacao', '')
        cavalo.situacao = request.POST.get('situacao', '')
        cavalo.proprietario_id = request.POST.get('proprietario') or None
        cavalo.gestor_id = request.POST.get('gestor') or None
        cavalo.observacoes = request.POST.get('observacoes', '')
        cavalo.emissao_laudo = request.POST.get('emissao_laudo') or None
        if 'documento' in request.FILES:
            cavalo.documento = request.FILES['documento']
        if 'foto' in request.FILES:
            cavalo.foto = request.FILES['foto']
        if cavalo.tipo == 'bi_truck':
            cavalo.carreta = None
        else:
            carreta_id = request.POST.get('carreta') or None
            if carreta_id and carreta_id != 's_placa':
                try:
                    carreta = Carreta.objects.get(pk=carreta_id)
                    if cavalo.classificacao and carreta.classificacao and cavalo.classificacao != carreta.classificacao:
                        messages.error(request, f'Erro: A carreta selecionada é de "{carreta.get_classificacao_display()}" mas o cavalo é "{cavalo.get_classificacao_display()}". Eles devem ter a mesma classificação.')
                        return render(request, 'core/cavalo_form.html', _cavalo_form_context(cavalo, 'edit'))
                    cavalo_anterior = getattr(carreta, 'cavalo_acoplado', None)
                    if cavalo_anterior and cavalo_anterior.pk != cavalo.pk:
                        cavalo_anterior.carreta = None
                        cavalo_anterior.save()
                    cavalo.carreta = carreta
                except Carreta.DoesNotExist:
                    cavalo.carreta = None
            else:
                cavalo.carreta = None
        motorista_id = request.POST.get('motorista') or None
        if motorista_id:
            try:
                motorista = Motorista.objects.get(pk=motorista_id)
                if motorista.cavalo and motorista.cavalo.pk != cavalo.pk:
                    motorista.cavalo = None
                    motorista.save()
                motorista.cavalo = cavalo
                motorista.save()
            except Motorista.DoesNotExist:
                pass
        else:
            try:
                if cavalo.motorista:
                    cavalo.motorista.cavalo = None
                    cavalo.motorista.save()
            except Motorista.DoesNotExist:
                pass
        cavalo.save()
        for f in request.FILES.getlist('documentos_extras'):
            CavaloDocumento.objects.create(cavalo=cavalo, arquivo=f)
        return redirect('core:cavalo_detail', pk=cavalo.pk)
    return render(request, 'core/cavalo_form.html', _cavalo_form_context(cavalo, 'edit'))


# ─── Carretas ─────────────────────────────────────────────────────────
@login_required
@require_menu_perm('agregamento')
def carreta_list(request):
    # Apenas carretas de classificação Agregamento
    carretas = Carreta.objects.filter(classificacao='agregado')
    disponivel_filter = request.GET.get('disponivel', '')
    carretas_acopladas_ids = Cavalo.objects.exclude(carreta__isnull=True).values_list('carreta_id', flat=True)
    if disponivel_filter == 'sim':
        carretas = carretas.exclude(id__in=carretas_acopladas_ids)
    elif disponivel_filter == 'nao':
        carretas = carretas.filter(id__in=carretas_acopladas_ids)
    carretas_agregadas = Carreta.objects.filter(classificacao='agregado')
    return render(request, 'core/carreta_list.html', {
        'carretas': carretas,
        'disponivel_filter': disponivel_filter,
        'contador_total_agregamento': carretas_agregadas.count(),
        'contador_disponiveis_agregamento': carretas_agregadas.exclude(id__in=carretas_acopladas_ids).count(),
        'contador_paradas_agregamento': carretas_agregadas.filter(situacao='parado').count(),
    })


@login_required
@require_menu_perm('agregamento')
def carreta_detail(request, pk):
    carreta = get_object_or_404(
        Carreta.objects.prefetch_related('documentos_extras'),
        pk=pk
    )
    return render(request, 'core/carreta_detail.html', {'carreta': carreta})


@login_required
@require_menu_perm('agregamento')
def carreta_download_documento(request, pk):
    carreta = get_object_or_404(Carreta, pk=pk)
    if not carreta.documento:
        raise Http404('Documento não encontrado.')
    key = carreta.documento.name
    filename_base = f'carreta_{carreta.placa or carreta.pk}.pdf'
    return _file_response_from_storage(key, filename_base, request)


@login_required
@require_menu_perm('agregamento')
def carreta_download_documento_extra(request, pk):
    doc = get_object_or_404(CarretaDocumento, pk=pk)
    if not doc.arquivo:
        raise Http404('Documento não encontrado.')
    key = doc.arquivo.name
    filename_base = os.path.basename(key)
    return _file_response_from_storage(key, filename_base, request)


@login_required
@require_menu_perm('agregamento')
def carreta_remover_documento(request, pk):
    if request.method != 'POST':
        return redirect('core:carreta_detail', pk=pk)
    carreta = get_object_or_404(Carreta, pk=pk)
    if carreta.documento:
        carreta.documento.delete(save=True)
        messages.success(request, 'Documento principal removido e excluído do armazenamento.')
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and next_url.startswith('/') and len(next_url) > 1:
        return redirect(next_url)
    return redirect('core:carreta_detail', pk=carreta.pk)


@login_required
@require_menu_perm('agregamento')
def carreta_remover_documento_extra(request, pk):
    if request.method != 'POST':
        doc = get_object_or_404(CarretaDocumento, pk=pk)
        return redirect('core:carreta_detail', pk=doc.carreta_id)
    doc = get_object_or_404(CarretaDocumento, pk=pk)
    carreta_pk = doc.carreta_id
    if doc.arquivo:
        doc.arquivo.delete(save=False)
    doc.delete()
    messages.success(request, 'Documento anexado removido e excluído do armazenamento.')
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and next_url.startswith('/') and len(next_url) > 1:
        return redirect(next_url)
    return redirect('core:carreta_detail', pk=carreta_pk)


@login_required
@require_menu_perm('agregamento')
def carreta_create(request):
    if request.method == 'POST':
        ultima_lavagem_str = request.POST.get('ultima_lavagem', '').strip()
        ultima_lavagem = None
        if ultima_lavagem_str:
            try:
                ultima_lavagem = datetime.strptime(ultima_lavagem_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                pass
        carreta = Carreta.objects.create(
            placa=request.POST.get('placa', ''),
            marca=request.POST.get('marca', ''),
            modelo=request.POST.get('modelo', ''),
            ano=request.POST.get('ano') or None,
            cor=request.POST.get('cor', ''),
            ultima_lavagem=ultima_lavagem,
            polietileno=request.POST.get('polietileno', ''),
            cones=request.POST.get('cones', ''),
            localizador=request.POST.get('localizador', ''),
            lona_facil=request.POST.get('lona_facil', ''),
            step=request.POST.get('step', ''),
            tipo=request.POST.get('tipo', ''),
            classificacao=request.POST.get('classificacao', ''),
            situacao=request.POST.get('situacao', 'ativo'),
            observacoes=request.POST.get('observacoes', ''),
        )
        if 'foto' in request.FILES:
            carreta.foto = request.FILES['foto']
        if 'documento' in request.FILES:
            carreta.documento = request.FILES['documento']
        carreta.emissao_laudo = request.POST.get('emissao_laudo') or None
        carreta.save()
        for f in request.FILES.getlist('documentos_extras'):
            CarretaDocumento.objects.create(carreta=carreta, arquivo=f)
        return redirect('core:carreta_detail', pk=carreta.pk)
    return render(request, 'core/carreta_form.html', {'form_type': 'create'})


@login_required
@require_menu_perm('agregamento')
def carreta_edit(request, pk):
    carreta = get_object_or_404(Carreta, pk=pk)
    if request.method == 'POST':
        carreta.placa = request.POST.get('placa', '')
        carreta.marca = request.POST.get('marca', '')
        carreta.modelo = request.POST.get('modelo', '')
        carreta.ano = request.POST.get('ano') or None
        carreta.cor = request.POST.get('cor', '')
        ultima_lavagem_str = request.POST.get('ultima_lavagem', '').strip()
        if ultima_lavagem_str:
            try:
                carreta.ultima_lavagem = datetime.strptime(ultima_lavagem_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                carreta.ultima_lavagem = None
        else:
            carreta.ultima_lavagem = None
        carreta.polietileno = request.POST.get('polietileno', '')
        carreta.cones = request.POST.get('cones', '')
        carreta.localizador = request.POST.get('localizador', '')
        carreta.lona_facil = request.POST.get('lona_facil', '')
        carreta.step = request.POST.get('step', '')
        carreta.tipo = request.POST.get('tipo', '')
        carreta.classificacao = request.POST.get('classificacao', '')
        carreta.situacao = request.POST.get('situacao', 'ativo')
        carreta.observacoes = request.POST.get('observacoes', '')
        carreta.emissao_laudo = request.POST.get('emissao_laudo') or None
        if 'foto' in request.FILES:
            carreta.foto = request.FILES['foto']
        if 'documento' in request.FILES:
            carreta.documento = request.FILES['documento']
        carreta.save()
        for f in request.FILES.getlist('documentos_extras'):
            CarretaDocumento.objects.create(carreta=carreta, arquivo=f)
        return redirect('core:carreta_detail', pk=carreta.pk)
    return render(request, 'core/carreta_form.html', {'carreta': carreta, 'form_type': 'edit'})


# ─── Motoristas ───────────────────────────────────────────────────────
@login_required
@require_menu_perm('agregamento')
def motorista_list(request):
    motoristas = Motorista.objects.select_related('cavalo', 'cavalo__carreta').filter(cavalo__isnull=False)
    return render(request, 'core/motorista_list.html', {'motoristas': motoristas})


@login_required
@require_menu_perm('agregamento')
def motorista_detail(request, pk):
    motorista = get_object_or_404(
        Motorista.objects.select_related('cavalo', 'cavalo__carreta').prefetch_related('documentos_extras'),
        pk=pk
    )
    document_filename = os.path.basename(motorista.documento.name) if motorista.documento and motorista.documento.name else None
    return render(request, 'core/motorista_detail.html', {
        'motorista': motorista,
        'document_filename': document_filename,
    })


@login_required
@require_menu_perm('agregamento')
def motorista_download_documento(request, pk):
    motorista = get_object_or_404(Motorista, pk=pk)
    if not motorista.documento:
        raise Http404('Documento não encontrado.')
    key = motorista.documento.name
    filename_base = f'motorista_{motorista.nome or motorista.pk}.pdf'
    return _file_response_from_storage(key, filename_base, request)


@login_required
@require_menu_perm('agregamento')
def motorista_download_documento_extra(request, pk):
    doc = get_object_or_404(MotoristaDocumento, pk=pk)
    if not doc.arquivo:
        raise Http404('Documento não encontrado.')
    key = doc.arquivo.name
    filename_base = os.path.basename(key)
    return _file_response_from_storage(key, filename_base, request)


@login_required
@require_menu_perm('agregamento')
def motorista_remover_documento(request, pk):
    if request.method != 'POST':
        return redirect('core:motorista_detail', pk=pk)
    motorista = get_object_or_404(Motorista, pk=pk)
    if motorista.documento:
        motorista.documento.delete(save=True)
        messages.success(request, 'Documento removido e excluído do armazenamento.')
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and next_url.startswith('/') and len(next_url) > 1:
        return redirect(next_url)
    return redirect('core:motorista_detail', pk=motorista.pk)


@login_required
@require_menu_perm('agregamento')
def motorista_remover_documento_extra(request, pk):
    if request.method != 'POST':
        doc = get_object_or_404(MotoristaDocumento, pk=pk)
        return redirect('core:motorista_detail', pk=doc.motorista_id)
    doc = get_object_or_404(MotoristaDocumento, pk=pk)
    motorista_pk = doc.motorista_id
    if doc.arquivo:
        doc.arquivo.delete(save=False)
    doc.delete()
    messages.success(request, 'Documento anexado removido e excluído do armazenamento.')
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and next_url.startswith('/') and len(next_url) > 1:
        return redirect(next_url)
    return redirect('core:motorista_detail', pk=motorista_pk)


@login_required
@require_menu_perm('agregamento')
def motorista_create(request):
    if request.method == 'POST':
        motorista = Motorista.objects.create(
            nome=request.POST.get('nome', ''),
            cpf=request.POST.get('cpf', ''),
            whatsapp=request.POST.get('whatsapp', ''),
            cavalo_id=request.POST.get('cavalo') or None,
        )
        if 'foto' in request.FILES:
            motorista.foto = request.FILES['foto']
        if 'documento' in request.FILES:
            motorista.documento = request.FILES['documento']
        motorista.save()
        for f in request.FILES.getlist('documentos_extras'):
            MotoristaDocumento.objects.create(motorista=motorista, arquivo=f)
        return redirect('core:motorista_detail', pk=motorista.pk)
    return render(request, 'core/motorista_form.html', {'form_type': 'create', 'cavalos': Cavalo.objects.all()})


@login_required
@require_menu_perm('agregamento')
def motorista_edit(request, pk):
    motorista = get_object_or_404(Motorista, pk=pk)
    if request.method == 'POST':
        motorista.nome = request.POST.get('nome', '')
        motorista.cpf = request.POST.get('cpf', '')
        motorista.whatsapp = request.POST.get('whatsapp', '')
        motorista.cavalo_id = request.POST.get('cavalo') or None
        if 'foto' in request.FILES:
            motorista.foto = request.FILES['foto']
        if 'documento' in request.FILES:
            motorista.documento = request.FILES['documento']
        motorista.save()
        for f in request.FILES.getlist('documentos_extras'):
            MotoristaDocumento.objects.create(motorista=motorista, arquivo=f)
        return redirect('core:motorista_detail', pk=motorista.pk)
    return render(request, 'core/motorista_form.html', {'motorista': motorista, 'form_type': 'edit', 'cavalos': Cavalo.objects.all()})


# ─── Logs ─────────────────────────────────────────────────────────────
@login_required
@require_menu_perm('agregamento')
def log_list(request):
    logs = LogCarreta.objects.all()
    tipo_filter = request.GET.get('tipo', '')
    placa_filter = request.GET.get('placa', '')
    data_inicio = request.GET.get('data_inicio', '')
    data_fim = request.GET.get('data_fim', '')
    if tipo_filter:
        logs = logs.filter(tipo=tipo_filter)
    if placa_filter:
        logs = logs.filter(
            Q(placa_cavalo__icontains=placa_filter)
            | Q(carreta_anterior__icontains=placa_filter)
            | Q(carreta_nova__icontains=placa_filter)
            | Q(motorista_anterior__icontains=placa_filter)
            | Q(motorista_novo__icontains=placa_filter)
            | Q(proprietario_anterior__icontains=placa_filter)
            | Q(proprietario_novo__icontains=placa_filter)
        )
    if data_inicio:
        try:
            logs = logs.filter(data_hora__gte=datetime.strptime(data_inicio, '%Y-%m-%d'))
        except ValueError:
            pass
    if data_fim:
        try:
            logs = logs.filter(data_hora__lte=datetime.strptime(data_fim, '%Y-%m-%d'))
        except ValueError:
            pass
    paginator = Paginator(logs, 50)
    logs_page = paginator.get_page(request.GET.get('page'))
    return render(request, 'core/log_list.html', {
        'logs': logs_page,
        'tipo_filter': tipo_filter,
        'placa_filter': placa_filter,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
    })


# ─── AJAX ─────────────────────────────────────────────────────────────
@login_required
@require_menu_perm('agregamento')
def ajax_carretas_classificacoes(request):
    from django.http import JsonResponse
    classificacoes = {str(c['id']): c['classificacao'] or '' for c in Carreta.objects.all().values('id', 'classificacao')}
    return JsonResponse(classificacoes)


# ─── API JWT ──────────────────────────────────────────────────────────
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView


@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    usuario = request.data.get('usuario')
    senha = request.data.get('senha')
    if not usuario or not senha:
        return Response({'erro': 'Informe usuário e senha.'}, status=status.HTTP_400_BAD_REQUEST)
    user = authenticate(request, username=usuario, password=senha)
    if user is None:
        return Response({'erro': 'Credenciais inválidas.'}, status=status.HTTP_401_UNAUTHORIZED)
    if not user.is_active:
        return Response({'erro': 'Usuário desativado. Contate o administrador.'}, status=status.HTTP_403_FORBIDDEN)
    refresh = RefreshToken.for_user(user)
    return Response({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'usuario': {
            'nome': user.get_full_name() or user.username,
            'email': user.email,
            'admin': user.is_staff,
        },
    })


api_refresh_token = TokenRefreshView.as_view()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_me(request):
    user = request.user
    return Response({
        'nome': user.get_full_name() or user.username,
        'email': user.email,
        'admin': user.is_staff,
    })
