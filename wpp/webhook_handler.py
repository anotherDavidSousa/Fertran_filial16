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
    # raw UAZAPI type values
    'image', 'video', 'document', 'audio', 'ptt', 'sticker', 'gif',
    # resolved *Message names
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


def _fetch_media(url: str, token: str) -> bytes | None:
    """Download media with streaming + size cap to avoid OOM on large videos."""
    try:
        r = requests.get(url, headers={'token': token}, timeout=60, stream=True)
        r.raise_for_status()
        # Respect content-length if present
        cl = int(r.headers.get('content-length', 0))
        if cl and cl > _MAX_MEDIA_BYTES:
            logger.warning('Media too large (%d bytes) — skipping download from %s', cl, url)
            return None
        chunks = []
        downloaded = 0
        for chunk in r.iter_content(chunk_size=131072):  # 128 KB chunks
            downloaded += len(chunk)
            if downloaded > _MAX_MEDIA_BYTES:
                logger.warning('Media exceeded 80 MB during download — aborting %s', url)
                return None
            chunks.append(chunk)
        return b''.join(chunks)
    except Exception as exc:
        logger.error('Media download failed from %s: %s', url, exc)
        return None


def _bg_download_media(msg_id: str, url: str, token: str,
                       is_group: bool, chat_jid: str, ts: datetime, msg_type: str) -> None:
    """Background thread: download media → upload to MinIO → update Mensagem row."""
    from django.db import close_old_connections
    try:
        close_old_connections()
        ext = os.path.splitext(url.split('?')[0])[1] or ''
        filename = f'{msg_type}{ext}'
        content = _fetch_media(url, token)
        if not content:
            return
        key = _minio_key(is_group, chat_jid, ts, msg_id, filename)
        ct = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
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
    folder = 'grupos' if is_group else 'contatos'
    return f'wpp/{folder}/{safe_jid}/{date_str}/{time_str}_{msg_id[:16]}_{safe_name}'


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

    # Media URL — UAZAPI may use 'content', 'mediaUrl', 'fileURL', or 'url'
    _content = msg_obj.get('content') or ''
    file_url = (
        msg_obj.get('mediaUrl') or msg_obj.get('fileURL') or
        msg_obj.get('url') or
        (_content if isinstance(_content, str) and _content.startswith('http') else '') or ''
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

    if Mensagem.objects.filter(msg_id=msg_id).exists():
        logger.debug('WPP duplicate msg_id=%s — skipping', msg_id)
        return

    try:
        ts = datetime.fromtimestamp(int(raw_ts), tz=dt_tz.utc) if raw_ts else timezone.now()
    except Exception:
        ts = timezone.now()

    tipo = _TYPE_MAP.get(msg_type, Mensagem.TYPE_OTHER)

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
        timestamp=ts,
    )
    logger.info('WPP message SAVED: msg_id=%s chat=%s type=%s', msg_id, chat_jid, tipo)

    # Download media asynchronously so the webhook returns immediately
    if file_url and msg_type in _MEDIA_TYPES and instance:
        t = threading.Thread(
            target=_bg_download_media,
            args=(msg_id, file_url, instance.token, is_group, chat_jid, ts, msg_type),
            daemon=True,
            name=f'wpp-media-{msg_id[:12]}',
        )
        t.start()
