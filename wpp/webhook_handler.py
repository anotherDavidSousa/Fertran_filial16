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


def handle_message(payload: dict):
    """Persist a received UAZAPI message event to the database."""
    data = payload.get('data', {})

    msg_id = data.get('messageid') or data.get('id') or ''
    chat_jid = data.get('chatid') or data.get('remoteJid') or ''
    sender_jid = data.get('sender') or ''
    sender_name = data.get('senderName') or ''
    is_group = bool(data.get('isGroup'))
    from_me = bool(data.get('fromMe'))
    msg_type = data.get('messageType') or 'conversation'
    text = data.get('text') or ''
    file_url = data.get('fileURL') or ''
    raw_ts = data.get('messageTimestamp') or 0

    if not msg_id or not chat_jid:
        return

    if Mensagem.objects.filter(msg_id=msg_id).exists():
        return  # already persisted (duplicate delivery)

    try:
        ts = datetime.fromtimestamp(int(raw_ts), tz=dt_tz.utc) if raw_ts else timezone.now()
    except Exception:
        ts = timezone.now()

    tipo = _TYPE_MAP.get(msg_type, Mensagem.TYPE_OTHER)

    grupo = None
    contato = None

    if is_group:
        grupo = GrupoConfig.objects.filter(jid=chat_jid).first()
    else:
        contato, _ = Contato.objects.get_or_create(
            jid=sender_jid or chat_jid,
            defaults={
                'nome': sender_name,
                'telefone': (sender_jid or chat_jid).split('@')[0],
            },
        )

    # Resolve the instance to get the token for media download
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
