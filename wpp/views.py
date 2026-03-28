import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from fila.menu_perms import require_menu_perm

from .models import GrupoConfig, Mensagem, Pendencia, WppInstance

logger = logging.getLogger(__name__)


# ── Page views ─────────────────────────────────────────────────────────────────

@login_required
@require_menu_perm('wpp')
def inbox(request):
    grupos = GrupoConfig.objects.filter(ativo=True).select_related('instance').order_by('nome')
    pendencias_abertas = Pendencia.objects.filter(status=Pendencia.STATUS_ABERTA).count()
    return render(request, 'wpp/inbox.html', {
        'grupos': grupos,
        'pendencias_abertas': pendencias_abertas,
    })


@login_required
@require_menu_perm('wpp')
def chat(request, jid):
    grupo = GrupoConfig.objects.filter(jid=jid).select_related('instance').first()
    pendencias = []
    carregamento = None
    if grupo:
        pendencias = list(
            grupo.pendencias.select_related('criado_por', 'resolvido_por').order_by('-criado_em')
        )
        carregamento = grupo.carregamento_ativo()
    # Last 50 messages for initial render
    mensagens = Mensagem.objects.filter(jid_chat=jid).order_by('timestamp').select_related('enviado_por')[:50]
    return render(request, 'wpp/chat.html', {
        'grupo': grupo,
        'jid': jid,
        'mensagens': mensagens,
        'pendencias': pendencias,
        'carregamento': carregamento,
    })


@login_required
@require_menu_perm('wpp')
def pendencias(request):
    abertas = (
        Pendencia.objects
        .filter(status=Pendencia.STATUS_ABERTA)
        .select_related('grupo', 'criado_por')
        .order_by('criado_em')
    )
    resolvidas_recentes = (
        Pendencia.objects
        .filter(status=Pendencia.STATUS_RESOLVIDA)
        .select_related('grupo', 'criado_por', 'resolvido_por')
        .order_by('-resolvido_em')[:30]
    )
    return render(request, 'wpp/pendencias.html', {
        'abertas': abertas,
        'resolvidas_recentes': resolvidas_recentes,
    })


@login_required
@require_menu_perm('wpp')
def config(request):
    instances = WppInstance.objects.all()
    try:
        perfil = request.user.wpp_perfil
    except Exception:
        perfil = None

    if request.method == 'POST':
        from .models import PerfilUsuario
        assinatura = (request.POST.get('assinatura') or '').strip()
        if assinatura:
            PerfilUsuario.objects.update_or_create(
                user=request.user,
                defaults={'assinatura': assinatura},
            )
        from django.shortcuts import redirect
        return redirect('wpp:config')

    return render(request, 'wpp/config.html', {
        'instances': instances,
        'perfil': perfil,
    })


# ── AJAX endpoints ─────────────────────────────────────────────────────────────

@login_required
@require_menu_perm('wpp')
def mensagens_json(request, jid):
    """Polling endpoint — returns messages newer than `since_id`."""
    since_id = request.GET.get('since_id', 0)
    qs = Mensagem.objects.filter(jid_chat=jid)
    if since_id:
        try:
            qs = qs.filter(id__gt=int(since_id))
        except ValueError:
            pass
    msgs = list(
        qs.order_by('timestamp').values(
            'id', 'sender_nome', 'from_me', 'tipo', 'texto',
            'media_minio_key', 'timestamp', 'enviado_por__username',
        )
    )
    # Convert datetimes to ISO strings for JSON
    for m in msgs:
        if m['timestamp']:
            m['timestamp'] = m['timestamp'].isoformat()
    return JsonResponse({'mensagens': msgs})


@login_required
@require_menu_perm('wpp')
@require_POST
def enviar_mensagem(request, jid):
    try:
        body = json.loads(request.body)
        texto = (body.get('texto') or '').strip()
    except Exception:
        return JsonResponse({'erro': 'Corpo JSON inválido'}, status=400)

    if not texto:
        return JsonResponse({'erro': 'Texto vazio'}, status=400)

    assinatura = ''
    try:
        assinatura = request.user.wpp_perfil.assinatura
    except Exception:
        pass

    mensagem_final = f'*{assinatura}:* {texto}' if assinatura else texto

    instance = WppInstance.objects.filter(ativo=True).first()
    if not instance:
        return JsonResponse({'erro': 'Nenhuma instância ativa'}, status=503)

    from .adapter import UazapiAdapter
    adapter = UazapiAdapter(instance)
    ok, resp = adapter.send_text(jid, mensagem_final)
    if not ok:
        return JsonResponse({'erro': resp}, status=502)

    msg_id = resp.get('id') or resp.get('messageid') or f'sent-{jid}-{timezone.now().timestamp()}'
    msg = Mensagem.objects.create(
        msg_id=msg_id,
        grupo=GrupoConfig.objects.filter(jid=jid).first(),
        jid_chat=jid,
        sender_nome=assinatura or request.user.get_full_name() or request.user.username,
        from_me=True,
        enviado_por=request.user,
        tipo=Mensagem.TYPE_TEXT,
        texto=mensagem_final,
        timestamp=timezone.now(),
    )
    return JsonResponse({'ok': True, 'id': msg.pk})


@login_required
@require_menu_perm('wpp')
@require_POST
def criar_pendencia(request):
    try:
        body = json.loads(request.body)
        grupo_jid = body.get('grupo_jid', '')
        texto = (body.get('texto') or '').strip()
    except Exception:
        return JsonResponse({'erro': 'Corpo JSON inválido'}, status=400)

    if not texto or not grupo_jid:
        return JsonResponse({'erro': 'grupo_jid e texto são obrigatórios'}, status=400)

    grupo = GrupoConfig.objects.filter(jid=grupo_jid).first()
    if not grupo:
        return JsonResponse({'erro': 'Grupo não encontrado'}, status=404)

    p = Pendencia.objects.create(grupo=grupo, texto=texto, criado_por=request.user)
    return JsonResponse({
        'ok': True,
        'id': p.pk,
        'criado_em': p.criado_em.isoformat(),
        'criado_por': request.user.get_full_name() or request.user.username,
    })


@login_required
@require_menu_perm('wpp')
@require_POST
def resolver_pendencia(request, pk):
    from .fila_integration import tentar_arquivar_carregamento

    p = Pendencia.objects.filter(pk=pk, status=Pendencia.STATUS_ABERTA).first()
    if not p:
        return JsonResponse({'erro': 'Pendência não encontrada ou já resolvida'}, status=404)

    p.status = Pendencia.STATUS_RESOLVIDA
    p.resolvido_por = request.user
    p.resolvido_em = timezone.now()
    arquivou = tentar_arquivar_carregamento(p.grupo)
    p.arquivou_carregamento = arquivou
    p.save()

    return JsonResponse({
        'ok': True,
        'arquivou_carregamento': arquivou,
        'resolvido_em': p.resolvido_em.isoformat(),
    })


@login_required
@require_menu_perm('wpp')
@require_POST
def sync_grupos(request):
    instance = WppInstance.objects.filter(ativo=True).first()
    if not instance:
        return JsonResponse({'erro': 'Nenhuma instância ativa'}, status=503)

    from .adapter import UazapiAdapter
    adapter = UazapiAdapter(instance)
    ok, groups = adapter.list_groups()
    if not ok:
        return JsonResponse({'erro': groups}, status=502)

    if not isinstance(groups, list):
        groups = groups.get('groups') or groups.get('data') or []

    count = 0
    for g in groups:
        jid = g.get('id') or g.get('jid') or ''
        nome = g.get('name') or g.get('subject') or ''
        if not jid:
            continue
        obj, created = GrupoConfig.objects.get_or_create(
            jid=jid, defaults={'instance': instance, 'nome': nome},
        )
        if not created and nome and obj.nome != nome:
            obj.nome = nome
            obj.save(update_fields=['nome', 'placa_cavalo'])
        obj.sincronizado_em = timezone.now()
        obj.save(update_fields=['sincronizado_em'])
        count += 1

    return JsonResponse({'ok': True, 'grupos_sincronizados': count})


# ── Webhook (no session auth) ──────────────────────────────────────────────────

@csrf_exempt
def webhook(request):
    """Receives UAZAPI webhook events. Authenticated via token header (optional)."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    from django.conf import settings as dj_settings
    expected = getattr(dj_settings, 'UAZAPI_WEBHOOK_SECRET', '')
    if expected:
        received = (
            request.headers.get('Authorization', '')
            or request.headers.get('X-Token', '')
        )
        if received != expected:
            return HttpResponse(status=401)

    try:
        payload = json.loads(request.body)
    except Exception:
        return HttpResponse(status=400)

    event = payload.get('event', '')
    if event == 'message':
        from .webhook_handler import handle_message
        try:
            handle_message(payload)
        except Exception as exc:
            logger.exception('Error processing webhook message: %s', exc)

    return HttpResponse(status=200)
