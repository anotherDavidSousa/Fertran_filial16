"""
Processes incoming UAZAPI webhook payloads.

Real UAZAPI payload shape (observed):
{
  "BaseUrl": "https://fertranchat.uazapi.com",
  "EventType": "messages",
  "instanceName": "...",
  "token": "...",
  "owner": "...",
  "chatSource": "...",
  "chat": {
    "id": "<chat_id>",
    "name": "...",
    "isGroup": true/false,
    ...
  },
  "message": {
    "id": "<msg_id>",
    "from": "<sender_jid>",
    "to": "<chat_jid>",
    "body": "texto",
    "type": "chat" | "image" | "audio" | ...,
    "fromMe": false,
    "notifyName": "Nome",
    "timestamp": 1234567890,
    "mediaUrl": "...",
    ...
  }
}
"""
import logging
import mimetypes
import os
import threading
from datetime import datetime, timezone as dt_tz

import requests
from django.conf import settings
from django.utils import timezone

from .models import Contato, GrupoConfig, Mensagem, WppInstance

logger = logging.getLogger(__name__)

_MEDIA_TYPES = {
    # raw UAZAPI type values (lowercased)
    'image', 'video', 'document', 'audio', 'ptt', 'sticker', 'gif',
    # after _MEDIATYPE_MAP reassignment (camelCase, capital M)
    'imageMessage', 'videoMessage', 'documentMessage', 'audioMessage',
    'stickerMessage', 'gifMessage',
    # fully-lowercased variants (from direct UAZAPI type field)
    'imagemessage', 'videomessage', 'documentmessage', 'audiomessage', 'stickermessage',
}

_TYPE_MAP = {
    'chat':              Mensagem.TYPE_TEXT,
    'text':              Mensagem.TYPE_TEXT,
    'conversation':      Mensagem.TYPE_TEXT,
    'extendedText':      Mensagem.TYPE_TEXT,
    'image':             Mensagem.TYPE_IMAGE,
    'imageMessage':      Mensagem.TYPE_IMAGE,
    'video':             Mensagem.TYPE_VIDEO,
    'videoMessage':      Mensagem.TYPE_VIDEO,
    'gifMessage':        Mensagem.TYPE_VIDEO,   # GIFs are looping videos in WA
    'document':          Mensagem.TYPE_DOCUMENT,
    'documentMessage':   Mensagem.TYPE_DOCUMENT,
    'audio':             Mensagem.TYPE_AUDIO,
    'audioMessage':      Mensagem.TYPE_AUDIO,
    'ptt':               Mensagem.TYPE_AUDIO,   # push-to-talk = áudio
    'sticker':           Mensagem.TYPE_STICKER,
    'stickerMessage':    Mensagem.TYPE_STICKER,
    'reaction':          'reaction',  # handled separately — not persisted as new message
}


def _minio_client():
    import boto3
    from botocore.client import Config
    return boto3.client(
        's3',
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=Config(signature_version='s3v4'),
    )


def _upload_to_minio(content: bytes, key: str, content_type: str = 'application/octet-stream') -> bool:
    try:
        _minio_client().put_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        return True
    except Exception as exc:
        logger.error('MinIO upload failed for %s: %s', key, exc)
        return False


_MAX_MEDIA_BYTES = 80 * 1024 * 1024  # 80 MB cap


def _fetch_media(url: str, token: str) -> tuple:
    """Download media with streaming + size cap. Returns (bytes, mime_type) or (None, '')."""
    try:
        headers = {'token': token} if token else {}
        r = requests.get(url, headers=headers, timeout=60, stream=True)
        r.raise_for_status()
        cl = int(r.headers.get('content-length', 0))
        if cl and cl > _MAX_MEDIA_BYTES:
            logger.warning('Media too large (%d bytes) — skipping download from %s', cl, url)
            return None, ''
        chunks = []
        downloaded = 0
        for chunk in r.iter_content(chunk_size=131072):
            downloaded += len(chunk)
            if downloaded > _MAX_MEDIA_BYTES:
                logger.warning('Media exceeded 80 MB during download — aborting %s', url)
                return None, ''
            chunks.append(chunk)
        mime = r.headers.get('content-type', '').split(';')[0].strip()
        return b''.join(chunks), mime
    except Exception as exc:
        logger.error('Media download failed from %s: %s', url, exc)
        return None, ''


def _bg_download_media(msg_id: str, url: str, instance_id: int,
                       is_group: bool, chat_jid: str, ts: datetime, msg_type: str) -> None:
    """Background thread: download media → upload to MinIO → update Mensagem row.

    Strategy (IMPORTANT):
    WhatsApp CDN URLs (mmg.whatsapp.net, media-*.whatsapp.net) serve
    end-to-end ENCRYPTED blobs — downloading them directly produces garbage.
    UAZAPI's /message/download endpoint handles decryption and returns either:
      - {fileURL, mimetype}  → download from their server (decrypted)
      - {base64, mimetype}   → decode in-memory

    We ALWAYS call UAZAPI first. The raw CDN `url` is only used as a last
    resort for non-WhatsApp-CDN URLs that may not be encrypted.
    """
    import base64 as _b64
    from django.db import close_old_connections
    try:
        close_old_connections()

        content = None
        filename = msg_type  # fallback

        from .models import WppInstance
        from .adapter import UazapiAdapter
        inst = WppInstance.objects.filter(pk=instance_id).first()

        # ── Step 1: UAZAPI download API (decrypts WhatsApp media) ──────────────
        if inst:
            ok, resp = UazapiAdapter(inst).download_media(msg_id)
            logger.info('WPP media UAZAPI dl msg_id=%s ok=%s keys=%s preview=%r',
                        msg_id, ok,
                        list(resp.keys()) if isinstance(resp, dict) else type(resp).__name__,
                        str(resp)[:200])
            if ok and isinstance(resp, dict):
                b64 = resp.get('base64') or resp.get('data') or ''
                if b64:
                    try:
                        content = _b64.b64decode(b64)
                    except Exception as exc:
                        logger.error('WPP media base64 decode failed msg_id=%s: %s', msg_id, exc)
                    mime = resp.get('mimetype') or resp.get('mimeType') or ''
                    fn   = resp.get('filename') or resp.get('fileName') or ''
                    ext  = (os.path.splitext(fn)[1] if fn else '') or \
                           (mimetypes.guess_extension(mime) or '')
                    filename = f'{msg_type}{ext}' if ext else msg_type

                elif resp.get('fileURL') or resp.get('url'):
                    dl_url = resp.get('fileURL') or resp.get('url')
                    content, resp_mime = _fetch_media(dl_url, inst.token)
                    mime   = resp.get('mimetype') or resp.get('mimeType') or resp_mime or ''
                    url_ext = os.path.splitext(dl_url.split('?')[0])[1] if dl_url else ''
                    # Prefer MIME-derived extension over URL extension when URL
                    # extension is an encrypted/binary placeholder (.enc, .bin)
                    _bad_exts = {'.enc', '.bin', '.tmp', ''}
                    if url_ext and url_ext.lower() not in _bad_exts:
                        ext = url_ext
                    else:
                        ext = (mimetypes.guess_extension(mime) or url_ext or '')
                    filename = f'{msg_type}{ext}' if ext else msg_type

        # ── Step 2: fallback — direct URL only for non-WhatsApp-CDN sources ───
        # (mmg.whatsapp.net and media-*.whatsapp.net are encrypted; skip them)
        if not content and url and 'whatsapp.net' not in url:
            token = inst.token if inst else ''
            content, resp_mime = _fetch_media(url, token)
            url_ext = os.path.splitext(url.split('?')[0])[1]
            ext = url_ext or (mimetypes.guess_extension(resp_mime) or '' if resp_mime else '')
            filename = f'{msg_type}{ext}' if ext else msg_type

        if not content:
            logger.warning('WPP media: no content for msg_id=%s', msg_id)
            return

        key = _minio_key(is_group, chat_jid, ts, msg_id, filename)
        ct  = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        if _upload_to_minio(content, key, ct):
            Mensagem.objects.filter(msg_id=msg_id).update(media_minio_key=key)
            logger.info('WPP media saved (bg): %s', key)
    except Exception as exc:
        logger.error('Background media download failed for msg_id=%s: %s', msg_id, exc)
    finally:
        try:
            from django.db import close_old_connections
            close_old_connections()
        except Exception:
            pass


def _minio_key(is_group: bool, jid: str, ts: datetime, msg_id: str, filename: str) -> str:
    safe_jid = jid.replace('@', '_').replace('/', '_')
    date_str = ts.strftime('%Y-%m-%d')
    time_str = ts.strftime('%H-%M-%S')
    safe_name = os.path.basename(filename) or 'media'
    # Sanitize msg_id: remove characters that cause URL/path issues
    safe_id = msg_id[:16].replace(':', '-').replace('/', '-')
    folder = 'grupos' if is_group else 'contatos'
    return f'wpp/{folder}/{safe_jid}/{date_str}/{time_str}_{safe_id}_{safe_name}'


def handle_message(payload: dict):
    """Persist a received UAZAPI message event to the database."""

    # ── Extract from UAZAPI real format ──────────────────────────────────────
    msg_obj  = payload.get('message') or {}
    chat_obj = payload.get('chat') or {}

    # If message key is missing, fall back to legacy 'data' key
    if not msg_obj:
        msg_obj = payload.get('data') or {}

    # Message ID
    msg_id = (
        msg_obj.get('id') or msg_obj.get('messageid') or
        msg_obj.get('messageId') or msg_obj.get('msgId') or ''
    )

    # Chat JID — prefer msg_obj.to (the actual chat), fall back to chat_obj.id
    chat_jid = (
        msg_obj.get('to') or msg_obj.get('chatId') or
        msg_obj.get('remoteJid') or msg_obj.get('chatid') or
        chat_obj.get('id') or ''
    )

    # Sender JID
    sender_jid = (
        msg_obj.get('from') or msg_obj.get('sender') or
        msg_obj.get('author') or msg_obj.get('senderJid') or ''
    )

    # Sender display name
    sender_name = (
        msg_obj.get('notifyName') or msg_obj.get('pushName') or
        msg_obj.get('senderName') or chat_obj.get('name') or ''
    )

    # Is group?
    is_group = bool(
        msg_obj.get('isGroup') or msg_obj.get('isGroupMsg') or
        chat_obj.get('isGroup') or
        (chat_jid.endswith('@g.us') if chat_jid else False)
    )

    # From me?
    from_me = bool(msg_obj.get('fromMe') or msg_obj.get('self'))

    # Message type
    msg_type = (
        msg_obj.get('type') or msg_obj.get('messageType') or
        msg_obj.get('msgType') or 'chat'
    ).lower()

    # For generic 'media' type, resolve to a specific subtype.
    # UAZAPI sends a `mediaType` field (e.g. 'image', 'video', 'audio', 'document',
    # 'gif', 'ptt', 'sticker') and/or a MIME-based mimetype.
    if msg_type == 'media':
        media_type_hint = (msg_obj.get('mediaType') or '').lower()  # 'image','video','audio','document','gif','ptt','sticker'
        mimetype = (msg_obj.get('mimetype') or msg_obj.get('mimeType') or '').lower()
        filename = (msg_obj.get('fileName') or msg_obj.get('filename') or '').lower()

        _MEDIATYPE_MAP = {
            'image': 'imageMessage',
            'video': 'videoMessage',
            'gif':   'videoMessage',   # GIFs are looping videos in WA
            'audio': 'audioMessage',
            'ptt':   'audioMessage',
            'document': 'documentMessage',
            'sticker': 'stickerMessage',
        }
        if media_type_hint in _MEDIATYPE_MAP:
            msg_type = _MEDIATYPE_MAP[media_type_hint]
        elif mimetype.startswith('image/') or filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            msg_type = 'imageMessage'
        elif mimetype.startswith('video/') or filename.endswith(('.mp4', '.mov', '.avi', '.webm')):
            msg_type = 'videoMessage'
        elif mimetype.startswith('audio/') or filename.endswith(('.mp3', '.ogg', '.m4a', '.wav')):
            msg_type = 'audioMessage'
        elif mimetype or filename:
            msg_type = 'documentMessage'
        else:
            logger.debug('WPP type=media with unknown subtype — msg_obj keys: %s', list(msg_obj.keys()))

    # Text body
    text = (
        msg_obj.get('body') or msg_obj.get('text') or
        msg_obj.get('caption') or msg_obj.get('message') or ''
    )

    # Media URL — UAZAPI may use 'content' (dict or str), 'mediaUrl', 'fileURL', 'url'
    _content = msg_obj.get('content') or ''
    # content can be a dict like {'URL': 'https://...'} or a plain URL string
    if isinstance(_content, dict):
        _content_url = _content.get('URL') or _content.get('url') or ''
    elif isinstance(_content, str) and _content.startswith('http'):
        _content_url = _content
    else:
        _content_url = ''
    file_url = (
        msg_obj.get('mediaUrl') or msg_obj.get('fileURL') or
        msg_obj.get('url') or _content_url or ''
    )

    # Timestamp
    raw_ts = (
        msg_obj.get('timestamp') or msg_obj.get('messageTimestamp') or
        msg_obj.get('t') or 0
    )

    logger.info(
        'WPP handle_message: msg_id=%r chat_jid=%r sender=%r is_group=%s '
        'from_me=%s type=%r text=%r',
        msg_id, chat_jid, sender_jid, is_group, from_me, msg_type, str(text)[:80],
    )

    if not msg_id or not chat_jid:
        logger.warning(
            'WPP missing msg_id=%r or chat_jid=%r — skipping. '
            'message keys: %s  chat keys: %s',
            msg_id, chat_jid, list(msg_obj.keys()), list(chat_obj.keys()),
        )
        return

    # ── Reaction handling ────────────────────────────────────────────────────
    # Reactions are NOT saved as new messages; they update the target message.
    if msg_type == 'reaction':
        emoji = text  # UAZAPI puts the emoji in body/text
        # Find the target message ID from multiple possible fields
        target_id = (
            msg_obj.get('reactionMessage', {}) if isinstance(msg_obj.get('reactionMessage'), dict) else {}
        )
        target_msg_id = (
            target_id.get('key', {}).get('id') if isinstance(target_id.get('key'), dict) else ''
        ) or (
            msg_obj.get('reactionMessageId') or msg_obj.get('reacted_message_id') or
            msg_obj.get('reactedMsgId') or msg_obj.get('contextInfo', {}).get('stanzaId', '') or ''
        )
        logger.info('WPP reaction emoji=%r target_msg_id=%r sender=%r (full keys: %s)',
                    emoji, target_msg_id, sender_jid, list(msg_obj.keys()))
        if target_msg_id and emoji:
            from django.db import transaction
            with transaction.atomic():
                target = Mensagem.objects.filter(msg_id=target_msg_id).select_for_update().first()
                if target:
                    reacoes = dict(target.reacoes or {})
                    key = sender_jid or sender_name or 'anon'
                    if emoji:
                        reacoes[key] = emoji
                    else:
                        reacoes.pop(key, None)
                    target.reacoes = reacoes
                    target.save(update_fields=['reacoes'])
                    logger.info('WPP reaction saved: %r on msg_id=%s', emoji, target_msg_id)
        return  # do NOT create a new Mensagem row for reactions

    if Mensagem.objects.filter(msg_id=msg_id).exists():
        logger.debug('WPP duplicate msg_id=%s — skipping', msg_id)
        return

    try:
        ts = datetime.fromtimestamp(int(raw_ts), tz=dt_tz.utc) if raw_ts else timezone.now()
    except Exception:
        ts = timezone.now()

    tipo = _TYPE_MAP.get(msg_type, Mensagem.TYPE_OTHER)

    # ── Quoted/reply context ─────────────────────────────────────────────────
    # UAZAPI may provide quoted message info in several shapes:
    #   msg_obj['contextInfo']['quotedMessage'] + ['stanzaId']
    #   msg_obj['quotedMsg'] dict
    #   msg_obj['quotedMessage'] dict
    quoted_msg_id = ''
    quoted_sender = ''
    quoted_texto  = ''
    quoted_tipo   = ''

    ctx = msg_obj.get('contextInfo') or {}
    if isinstance(ctx, dict):
        quoted_msg_id = ctx.get('stanzaId') or ctx.get('quotedMsgId') or ''
        qsender = ctx.get('participant') or ctx.get('sender') or ''
        quoted_sender = qsender.split('@')[0] if qsender else ''
        q_inner = ctx.get('quotedMessage') or {}
        if isinstance(q_inner, dict):
            # quotedMessage is typically {conversationType: {text/caption:...}}
            for _v in q_inner.values():
                if isinstance(_v, dict):
                    quoted_texto = (_v.get('text') or _v.get('caption') or
                                    _v.get('body') or '')[:300]
                    break
        quoted_tipo = list(q_inner.keys())[0] if q_inner else ''

    # Fallback: 'quotedMsg' / 'quotedMessage' flat dict
    if not quoted_msg_id:
        qm = msg_obj.get('quotedMsg') or msg_obj.get('quotedMessage') or {}
        if isinstance(qm, dict):
            quoted_msg_id  = qm.get('id') or qm.get('msgId') or qm.get('messageId') or ''
            quoted_sender  = (qm.get('notifyName') or qm.get('pushName') or
                              (qm.get('sender', '') or '').split('@')[0] or '')
            quoted_texto   = (qm.get('body') or qm.get('text') or
                              qm.get('caption') or '')[:300]
            quoted_tipo    = qm.get('type') or ''

    grupo   = None
    contato = None

    if is_group:
        grupo = GrupoConfig.objects.filter(jid=chat_jid).first()
        if not grupo:
            # Auto-create group on first message received
            instance = WppInstance.objects.filter(ativo=True).first()
            if instance:
                chat_name = (
                    payload.get('chat', {}).get('name') or
                    payload.get('chat', {}).get('subject') or
                    chat_jid
                )
                grupo, created = GrupoConfig.objects.get_or_create(
                    jid=chat_jid,
                    defaults={'instance': instance, 'nome': chat_name},
                )
                if created:
                    logger.info('WPP auto-created GrupoConfig jid=%s nome=%r', chat_jid, chat_name)
    else:
        contato, _ = Contato.objects.get_or_create(
            jid=sender_jid or chat_jid,
            defaults={
                'nome': sender_name,
                'telefone': (sender_jid or chat_jid).split('@')[0],
            },
        )

    # Resolve instance for media token
    instance = getattr(grupo, 'instance', None) or WppInstance.objects.filter(ativo=True).first()

    # Save message immediately (media_minio_key filled by background thread)
    Mensagem.objects.create(
        msg_id=msg_id,
        grupo=grupo,
        contato=contato,
        jid_chat=chat_jid,
        sender_jid=sender_jid,
        sender_nome=sender_name,
        from_me=from_me,
        tipo=tipo,
        texto=text,
        media_minio_key='',
        quoted_msg_id=quoted_msg_id,
        quoted_sender_nome=quoted_sender,
        quoted_texto=quoted_texto,
        quoted_tipo=quoted_tipo,
        timestamp=ts,
    )
    logger.info('WPP message SAVED: msg_id=%s chat=%s type=%s quoted=%r',
                msg_id, chat_jid, tipo, quoted_msg_id or None)

    # Download media asynchronously so the webhook returns immediately.
    # Fire even when file_url is empty — the background thread will use UAZAPI download API.
    if msg_type in _MEDIA_TYPES and instance:
        t = threading.Thread(
            target=_bg_download_media,
            args=(msg_id, file_url, instance.pk, is_group, chat_jid, ts, msg_type),
            daemon=True,
            name=f'wpp-media-{msg_id[:12]}',
        )
        t.start()
