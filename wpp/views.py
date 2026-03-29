import json
import logging

from django.contrib.auth.decorators import login_required
from django.db.models import Count, OuterRef, Q, Subquery
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from fila.menu_perms import require_menu_perm

from .models import GrupoConfig, Mensagem, Pendencia, WppInstance

logger = logging.getLogger(__name__)

# ── Shared queryset helper ─────────────────────────────────────────────────────

def _grupos_qs():
    """Groups annotated with last message preview and open pendência count."""
    last = Mensagem.objects.filter(jid_chat=OuterRef('jid')).order_by('-timestamp')
    return (
        GrupoConfig.objects
        .filter(ativo=True)
        .select_related('instance')
        .annotate(
            last_msg_texto=Subquery(last.values('texto')[:1]),
            last_msg_time=Subquery(last.values('timestamp')[:1]),
            last_msg_tipo=Subquery(last.values('tipo')[:1]),
            pendencias_abertas_count=Count(
                'pendencias', filter=Q(pendencias__status=Pendencia.STATUS_ABERTA)
            ),
        )
        .order_by('-last_msg_time', 'nome')
    )


def _chat_context(jid):
    """Returns (grupo, mensagens, pendencias, carregamento) for a given JID."""
    grupo = GrupoConfig.objects.filter(jid=jid).select_related('instance').first()
    if not grupo:
        return None, [], [], None
    mensagens = list(
        Mensagem.objects
        .filter(jid_chat=jid)
        .order_by('timestamp')
        .select_related('enviado_por')
    )[-100:]
    pendencias_grupo = list(
        grupo.pendencias
        .select_related('criado_por', 'resolvido_por')
        .order_by('-criado_em')
    )
    carregamento = grupo.carregamento_ativo()
    return grupo, mensagens, pendencias_grupo, carregamento


# ── Page views ─────────────────────────────────────────────────────────────────

@login_required
@require_menu_perm('wpp')
def inbox(request, jid=None):
    """Main WhatsApp-like shell — group list + optional pre-loaded chat."""
    grupos = _grupos_qs()

    active_grupo, mensagens, pendencias_grupo, carregamento = None, [], [], None
    if jid:
        active_grupo, mensagens, pendencias_grupo, carregamento = _chat_context(jid)

    try:
        perfil = request.user.wpp_perfil
    except Exception:
        perfil = None

    return render(request, 'wpp/wpp_app.html', {
        'grupos': grupos,
        'active_jid': jid or '',
        'active_grupo': active_grupo,
        'mensagens': mensagens,
        'pendencias_grupo': pendencias_grupo,
        'carregamento': carregamento,
        'perfil': perfil,
    })


@login_required
@require_menu_perm('wpp')
def chat_partial(request, jid):
    """Returns HTML partial for the chat panel — called via AJAX when switching groups."""
    grupo, mensagens, pendencias_grupo, carregamento = _chat_context(jid)
    return render(request, 'wpp/partials/chat_panel.html', {
        'grupo': grupo,
        'jid': jid,
        'mensagens': mensagens,
        'pendencias_grupo': pendencias_grupo,
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


# ── AJAX / API endpoints ───────────────────────────────────────────────────────

@login_required
@require_menu_perm('wpp')
def grupos_json(request):
    """Group list with last message preview and pending counts — used to refresh left panel."""
    _type_icon = {
        'image': '📷 Foto', 'audio': '🎤 Áudio',
        'video': '📹 Vídeo', 'document': '📄 Documento',
    }
    result = []
    for g in _grupos_qs():
        if g.last_msg_tipo and g.last_msg_tipo != 'text':
            preview = _type_icon.get(g.last_msg_tipo, '📎 Mídia')
        elif g.last_msg_texto:
            preview = g.last_msg_texto[:60]
        else:
            preview = ''

        result.append({
            'jid': g.jid,
            'nome': g.nome or g.jid,
            'placa_cavalo': g.placa_cavalo,
            'preview': preview,
            'last_time': g.last_msg_time.isoformat() if g.last_msg_time else None,
            'pend_count': g.pendencias_abertas_count,
        })
    return JsonResponse({'grupos': result})


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
    for m in msgs:
        if m['timestamp']:
            m['timestamp'] = timezone.localtime(m['timestamp']).isoformat()
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

    msg_id = (
        resp.get('id') or resp.get('messageid')
        or f'sent-{jid}-{timezone.now().timestamp()}'
    )
    now = timezone.now()
    msg = Mensagem.objects.create(
        msg_id=msg_id,
        grupo=GrupoConfig.objects.filter(jid=jid).first(),
        jid_chat=jid,
        sender_nome=assinatura or request.user.get_full_name() or request.user.username,
        from_me=True,
        enviado_por=request.user,
        tipo=Mensagem.TYPE_TEXT,
        texto=mensagem_final,
        timestamp=now,
    )
    return JsonResponse({
        'ok': True,
        'id': msg.pk,
        'timestamp': timezone.localtime(now).isoformat(),
        'sender_nome': msg.sender_nome,
        'texto': mensagem_final,
    })


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
        'criado_em': timezone.localtime(p.criado_em).isoformat(),
        'criado_por': request.user.get_full_name() or request.user.username,
        'texto': texto,
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
        'resolvido_em': timezone.localtime(p.resolvido_em).isoformat(),
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


@login_required
@require_menu_perm('wpp')
def media_proxy(request, key):
    """Authenticated redirect to the MinIO/S3 media URL."""
    from django.core.files.storage import default_storage
    url = default_storage.url(key)
    return HttpResponseRedirect(url)


# ── Webhook (no session auth) ──────────────────────────────────────────────────

@csrf_exempt
def webhook(request):
    """Receives UAZAPI webhook events. Authenticated via optional token header."""
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

    event = (payload.get('event') or payload.get('type') or '').lower()

    # Log every webhook for debugging (first 500 chars to avoid log spam)
    logger.info('WPP webhook event=%r keys=%s body_preview=%s',
                event, list(payload.keys()), str(payload)[:500])

    # UAZAPI sends: "message", "messages", "messages.upsert", "message.upsert"
    _MSG_EVENTS = {'message', 'messages', 'messages.upsert', 'message.upsert'}
    if event in _MSG_EVENTS or 'message' in event:
        from .webhook_handler import handle_message
        try:
            handle_message(payload)
        except Exception as exc:
            logger.exception('Error processing webhook message: %s', exc)

    return HttpResponse(status=200)
