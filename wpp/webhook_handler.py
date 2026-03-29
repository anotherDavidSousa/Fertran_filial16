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
from datetime import datetime, timezone as dt_tz

import requests
from django.conf import settings
from django.utils import timezone

from .models import Contato, GrupoConfig, Mensagem, WppInstance

logger = logging.getLogger(__name__)

_MEDIA_TYPES = {'image', 'video', 'document', 'audio', 'ptt', 'sticker'}

_TYPE_MAP = {
    'chat':              Mensagem.TYPE_TEXT,
    'text':              Mensagem.TYPE_TEXT,
    'conversation':      Mensagem.TYPE_TEXT,
    'extendedText':      Mensagem.TYPE_TEXT,
    'image':             Mensagem.TYPE_IMAGE,
    'imageMessage':      Mensagem.TYPE_IMAGE,
    'video':             Mensagem.TYPE_VIDEO,
    'videoMessage':      Mensagem.TYPE_VIDEO,
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


def _fetch_media(url: str, token: str) -> bytes | None:
    try:
        r = requests.get(url, headers={'token': token}, timeout=30)
        r.raise_for_status()
        return r.content
    except Exception as exc:
        logger.error('Media download failed from %s: %s', url, exc)
        return None


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

    # Text body
    text = (
        msg_obj.get('body') or msg_obj.get('text') or
        msg_obj.get('caption') or msg_obj.get('message') or ''
    )

    # Media URL
    file_url = (
        msg_obj.get('mediaUrl') or msg_obj.get('fileURL') or
        msg_obj.get('url') or ''
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
            logger.info('WPP msg for unknown group %s — storing without grupo link', chat_jid)
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

    media_minio_key = ''
    if file_url and msg_type in _MEDIA_TYPES and instance:
        ext = os.path.splitext(file_url.split('?')[0])[1] or ''
        filename = f'{msg_type}{ext}'
        content = _fetch_media(file_url, instance.token)
        if content:
            key = _minio_key(is_group, chat_jid, ts, msg_id, filename)
            ct = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            if _upload_to_minio(content, key, ct):
                media_minio_key = key
                logger.info('WPP media saved: %s', key)

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
        media_minio_key=media_minio_key,
        timestamp=ts,
    )
    logger.info('WPP message SAVED: msg_id=%s chat=%s type=%s', msg_id, chat_jid, tipo)
