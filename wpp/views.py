import json
import logging
from datetime import datetime, timezone as dt_tz

from django.contrib.auth.decorators import login_required
from django.db.models import Count, OuterRef, Q, Subquery
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from fila.menu_perms import require_menu_perm

from .models import Contato, GrupoConfig, Mensagem, Pendencia, WppInstance

logger = logging.getLogger(__name__)

# ── Shared queryset helpers ────────────────────────────────────────────────────

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


def _contatos_qs():
    """Contacts that have at least one message, annotated with last message info."""
    last = Mensagem.objects.filter(jid_chat=OuterRef('jid')).order_by('-timestamp')
    return (
        Contato.objects
        .annotate(
            last_msg_texto=Subquery(last.values('texto')[:1]),
            last_msg_time=Subquery(last.values('timestamp')[:1]),
            last_msg_tipo=Subquery(last.values('tipo')[:1]),
        )
        .filter(last_msg_time__isnull=False)
        .order_by('-last_msg_time', 'nome')
    )


def _conversas_list():
    """Merged, time-sorted list of groups + contacts as plain dicts for the sidebar."""
    _epoch = datetime(1970, 1, 1, tzinfo=dt_tz.utc)
    conversas = []
    for g in _grupos_qs():
        conversas.append({
            'jid': g.jid,
            'nome': g.nome or g.jid,
            'tipo': 'grupo',
            'last_msg_texto': g.last_msg_texto,
            'last_msg_time': g.last_msg_time,
            'last_msg_tipo': g.last_msg_tipo,
            'placa_cavalo': g.placa_cavalo,
            'pendencias_abertas_count': g.pendencias_abertas_count,
            'foto_url': g.foto_url,
        })
    for c in _contatos_qs():
        conversas.append({
            'jid': c.jid,
            'nome': c.nome or c.jid,
            'tipo': 'contato',
            'last_msg_texto': c.last_msg_texto,
            'last_msg_time': c.last_msg_time,
            'last_msg_tipo': c.last_msg_tipo,
            'placa_cavalo': '',
            'pendencias_abertas_count': 0,
            'foto_url': c.foto_url,
        })
    conversas.sort(key=lambda x: x['last_msg_time'] or _epoch, reverse=True)
    return conversas


def _chat_context(jid):
    """Returns (grupo, contato, mensagens, pendencias, carregamento) for a given JID."""
    grupo = GrupoConfig.objects.filter(jid=jid).select_related('instance').first()
    contato = None
    if not grupo:
        contato = Contato.objects.filter(jid=jid).first()

    mensagens = list(
        Mensagem.objects
        .filter(jid_chat=jid)
        .order_by('timestamp')
        .select_related('enviado_por')
    )[-100:]

    pendencias_grupo = []
    carregamento = None
    if grupo:
        pendencias_grupo = list(
            grupo.pendencias
            .select_related('criado_por', 'resolvido_por')
            .order_by('-criado_em')
        )
        try:
            carregamento = grupo.carregamento_ativo()
        except Exception:
            logger.exception('carregamento_ativo failed for grupo jid=%s', grupo.jid)

    return grupo, contato, mensagens, pendencias_grupo, carregamento


# ── Page views ─────────────────────────────────────────────────────────────────

@login_required
@require_menu_perm('wpp')
def inbox(request, jid=None):
    """Main WhatsApp-like shell — conversation list + optional pre-loaded chat."""
    conversas = _conversas_list()

    active_grupo, active_contato, mensagens, pendencias_grupo, carregamento = None, None, [], [], None
    if jid:
        active_grupo, active_contato, mensagens, pendencias_grupo, carregamento = _chat_context(jid)

    try:
        perfil = request.user.wpp_perfil
    except Exception:
        perfil = None

    return render(request, 'wpp/wpp_app.html', {
        'conversas': conversas,
        'active_jid': jid or '',
        'active_grupo': active_grupo,
        'active_contato': active_contato,
        'mensagens': mensagens,
        'pendencias_grupo': pendencias_grupo,
        'carregamento': carregamento,
        'perfil': perfil,
    })


@login_required
@require_menu_perm('wpp')
def chat_partial(request, jid):
    """Returns HTML partial for the chat panel — called via AJAX when switching conversations."""
    grupo, contato, mensagens, pendencias_grupo, carregamento = _chat_context(jid)
    return render(request, 'wpp/partials/chat_panel.html', {
        'grupo': grupo,
        'contato': contato,
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
    """Conversation list (groups + contacts) with last message preview — used to refresh left panel."""
    _type_icon = {
        'image': '📷 Foto', 'audio': '🎤 Áudio',
        'video': '📹 Vídeo', 'document': '📄 Documento',
    }
    result = []
    for c in _conversas_list():
        tipo = c['last_msg_tipo']
        if tipo and tipo != 'text':
            preview = _type_icon.get(tipo, '📎 Mídia')
        elif c['last_msg_texto']:
            preview = c['last_msg_texto'][:60]
        else:
            preview = ''

        result.append({
            'jid': c['jid'],
            'nome': c['nome'],
            'tipo': c['tipo'],
            'placa_cavalo': c['placa_cavalo'],
            'preview': preview,
            'last_time': c['last_msg_time'].isoformat() if c['last_msg_time'] else None,
            'pend_count': c['pendencias_abertas_count'],
            'foto_url': c['foto_url'],
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
            'id', 'sender_jid', 'sender_nome', 'from_me', 'tipo', 'texto',
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
    grupo_obj = GrupoConfig.objects.filter(jid=jid).first()
    contato_obj = None if grupo_obj else Contato.objects.filter(jid=jid).first()
    msg = Mensagem.objects.create(
        msg_id=msg_id,
        grupo=grupo_obj,
        contato=contato_obj,
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
@require_POST
def sync_foto(request, jid):
    """Fetch profile picture for a JID from UAZAPI and persist it."""
    instance = WppInstance.objects.filter(ativo=True).first()
    if not instance:
        return JsonResponse({'erro': 'Nenhuma instância ativa'}, status=503)

    from .adapter import UazapiAdapter
    ok, url = UazapiAdapter(instance).get_picture(jid)
    logger.info('WPP sync_foto jid=%r ok=%s url=%r', jid, ok, url)
    if not ok or not url:
        return JsonResponse({'foto_url': ''})

    if jid.endswith('@g.us'):
        GrupoConfig.objects.filter(jid=jid).update(foto_url=url)
    else:
        Contato.objects.filter(jid=jid).update(foto_url=url)

    return JsonResponse({'foto_url': url})


@login_required
@require_menu_perm('wpp')
def media_proxy(request, key):
    """Stream MinIO media through Django so internal Docker hostnames stay hidden."""
    import mimetypes
    import boto3
    from botocore.client import Config
    from django.conf import settings as dj_settings

    try:
        s3 = boto3.client(
            's3',
            endpoint_url=dj_settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=dj_settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=dj_settings.AWS_SECRET_ACCESS_KEY,
            config=Config(signature_version='s3v4'),
        )
        obj = s3.get_object(Bucket=dj_settings.AWS_STORAGE_BUCKET_NAME, Key=key)
        body = obj['Body'].read()
        content_type = obj.get('ContentType') or mimetypes.guess_type(key)[0] or 'application/octet-stream'
        filename = key.split('/')[-1]
        # Inline for images/video/audio so browser displays them; attachment otherwise
        inline_types = ('image/', 'video/', 'audio/')
        disposition = 'inline' if any(content_type.startswith(t) for t in inline_types) else 'attachment'
        response = HttpResponse(body, content_type=content_type)
        response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
        response['Content-Length'] = len(body)
        return response
    except Exception as exc:
        logger.error('media_proxy failed for key=%r: %s', key, exc)
        return HttpResponse(status=404)


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

    # UAZAPI real format uses "EventType"; fallback to "event" / "type"
    event = (
        payload.get('EventType') or payload.get('event') or
        payload.get('type') or ''
    ).lower()

    logger.info('WPP webhook event=%r keys=%s', event, list(payload.keys()))

    # Accept any event name that contains "message"
    if 'message' in event:
        from .webhook_handler import handle_message
        try:
            handle_message(payload)
        except Exception as exc:
            logger.exception('Error processing webhook message: %s', exc)

    return HttpResponse(status=200)
