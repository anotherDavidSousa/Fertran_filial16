"""
Processes incoming UAZAPI webhook payloads.
Media files are downloaded immediately upon receipt and stored permanently in MinIO.
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

_MEDIA_MSG_TYPES = {
    'imageMessage', 'videoMessage', 'documentMessage',
    'audioMessage', 'stickerMessage',
}

_TYPE_MAP = {
    'imageMessage': Mensagem.TYPE_IMAGE,
    'videoMessage': Mensagem.TYPE_VIDEO,
    'documentMessage': Mensagem.TYPE_DOCUMENT,
    'audioMessage': Mensagem.TYPE_AUDIO,
    'stickerMessage': Mensagem.TYPE_STICKER,
    'conversation': Mensagem.TYPE_TEXT,
    'extendedTextMessage': Mensagem.TYPE_TEXT,
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
    date_str = ts.strftime('%Y-%m-%d')
    time_str = ts.strftime('%H-%M-%S')
    safe_name = os.path.basename(filename) or 'media'
    folder = 'grupos' if is_group else 'contatos'
    return f'wpp/{folder}/{jid}/{date_str}/{time_str}_{msg_id}_{safe_name}'


def _extract_data(payload: dict) -> dict:
    """
    Normalise the payload across UAZAPI formats.

    Known shapes:
      Shape A (standard):  { event, instance, data: { messageid, chatid, ... } }
      Shape B (flat):      { event, messageid, chatid, ... }           (data == payload)
      Shape C (nested):    { event, data: { key: { messageid, ... } } }
    """
    data = payload.get('data') or {}

    # Shape A — data is a plain dict with messageid
    if isinstance(data, dict) and (data.get('messageid') or data.get('id') or data.get('chatid')):
        logger.debug('WPP payload shape A')
        return data

    # Shape C — data is a nested dict; look one level deeper
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, dict) and (v.get('messageid') or v.get('id') or v.get('chatid')):
                logger.debug('WPP payload shape C')
                return v

    # Shape B — payload itself is the message
    if payload.get('messageid') or payload.get('chatid'):
        logger.debug('WPP payload shape B (flat)')
        return payload

    # Last resort: return whatever data is
    logger.debug('WPP payload unrecognised shape, keys=%s', list(payload.keys()))
    return data if isinstance(data, dict) else {}


def handle_message(payload: dict):
    """Persist a received UAZAPI message event to the database."""
    data = _extract_data(payload)

    msg_id = (
        data.get('messageid') or data.get('id') or
        data.get('messageId') or data.get('msgId') or ''
    )
    chat_jid = (
        data.get('chatid') or data.get('remoteJid') or
        data.get('chatId') or data.get('from') or ''
    )
    sender_jid = (
        data.get('sender') or data.get('senderJid') or
        data.get('author') or ''
    )
    sender_name = (
        data.get('senderName') or data.get('pushName') or
        data.get('notifyName') or ''
    )
    is_group = bool(
        data.get('isGroup') or data.get('isGroupMsg') or
        (chat_jid.endswith('@g.us') if chat_jid else False)
    )
    from_me = bool(data.get('fromMe') or data.get('self'))
    msg_type = (
        data.get('messageType') or data.get('type') or
        data.get('msgType') or 'conversation'
    )
    text = (
        data.get('text') or data.get('body') or
        data.get('caption') or data.get('message') or ''
    )
    file_url = data.get('fileURL') or data.get('mediaUrl') or data.get('url') or ''
    raw_ts = data.get('messageTimestamp') or data.get('timestamp') or data.get('t') or 0

    logger.info(
        'WPP handle_message: msg_id=%r chat_jid=%r sender=%r is_group=%s from_me=%s type=%s text_preview=%r',
        msg_id, chat_jid, sender_jid, is_group, from_me, msg_type, str(text)[:80],
    )

    if not msg_id or not chat_jid:
        logger.warning('WPP message missing msg_id or chat_jid — skipping. data keys: %s', list(data.keys()))
        return

    if Mensagem.objects.filter(msg_id=msg_id).exists():
        logger.debug('WPP duplicate msg_id=%s — skipping', msg_id)
        return

    try:
        ts = datetime.fromtimestamp(int(raw_ts), tz=dt_tz.utc) if raw_ts else timezone.now()
    except Exception:
        ts = timezone.now()

    tipo = _TYPE_MAP.get(msg_type, Mensagem.TYPE_OTHER)

    grupo = None
    contato = None

    if is_group:
        grupo = GrupoConfig.objects.filter(jid=chat_jid).first()
        if not grupo:
            logger.info('WPP received msg for unknown group %s — storing without grupo link', chat_jid)
    else:
        contato, _ = Contato.objects.get_or_create(
            jid=sender_jid or chat_jid,
            defaults={
                'nome': sender_name,
                'telefone': (sender_jid or chat_jid).split('@')[0],
            },
        )

    # Resolve instance for media download token
    instance = None
    if grupo:
        instance = grupo.instance
    else:
        instance = WppInstance.objects.filter(ativo=True).first()

    media_minio_key = ''
    if file_url and msg_type in _MEDIA_MSG_TYPES and instance:
        ext = os.path.splitext(file_url.split('?')[0])[1] or ''
        filename = f'{msg_type}{ext}'
        content = _fetch_media(file_url, instance.token)
        if content:
            key = _minio_key(is_group, chat_jid, ts, msg_id, filename)
            ct = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            if _upload_to_minio(content, key, ct):
                media_minio_key = key
                logger.info('WPP media saved to MinIO: %s', key)

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
    logger.info('WPP message saved: msg_id=%s chat=%s', msg_id, chat_jid)
