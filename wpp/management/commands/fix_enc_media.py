"""
Management command: re-download WhatsApp media messages that were saved
with the wrong extension (.enc / .bin) due to the UAZAPI fileURL extension
being used instead of the actual MIME type.

Usage:
    python manage.py fix_enc_media [--dry-run] [--limit N]
"""
import base64
import logging
import mimetypes
import os

import boto3
import requests
from botocore.client import Config
from django.conf import settings
from django.core.management.base import BaseCommand

from wpp.adapter import UazapiAdapter
from wpp.models import Mensagem, WppInstance

logger = logging.getLogger(__name__)

_BAD_EXTS = {'.enc', '.bin', '.tmp'}


def _minio_client():
    return boto3.client(
        's3',
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=Config(signature_version='s3v4'),
    )


def _fetch(url, token=''):
    headers = {'token': token} if token else {}
    r = requests.get(url, headers=headers, timeout=60, stream=True)
    r.raise_for_status()
    mime = r.headers.get('content-type', '').split(';')[0].strip()
    return b''.join(r.iter_content(131072)), mime


class Command(BaseCommand):
    help = 'Re-download WhatsApp media saved with .enc/.bin extension and fix MinIO keys.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would be done without making changes')
        parser.add_argument('--limit', type=int, default=200,
                            help='Maximum number of messages to process (default 200)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit   = options['limit']

        instance = WppInstance.objects.filter(ativo=True).first()
        if not instance:
            self.stderr.write('No active WppInstance found.')
            return

        adapter = UazapiAdapter(instance)
        s3 = _minio_client()
        bucket = settings.AWS_STORAGE_BUCKET_NAME

        # Find messages whose MinIO key ends with a bad extension
        bad_msgs = (
            Mensagem.objects
            .exclude(media_minio_key='')
            .filter(media_minio_key__isnull=False)
        )
        candidates = [
            m for m in bad_msgs
            if os.path.splitext(m.media_minio_key)[1].lower() in _BAD_EXTS
        ][:limit]

        self.stdout.write(f'Found {len(candidates)} message(s) with bad extension.')

        fixed = 0
        failed = 0
        for msg in candidates:
            old_key = msg.media_minio_key
            ext_now = os.path.splitext(old_key)[1].lower()
            self.stdout.write(f'  [{msg.pk}] msg_id={msg.msg_id}  key={old_key}')

            if dry_run:
                continue

            content = None
            mime = ''

            # Step 1: UAZAPI download API (decrypts)
            try:
                ok, resp = adapter.download_media(msg.msg_id)
                if ok and isinstance(resp, dict):
                    b64 = resp.get('base64') or resp.get('data') or ''
                    if b64:
                        content = base64.b64decode(b64)
                        mime = resp.get('mimetype') or resp.get('mimeType') or ''
                    elif resp.get('fileURL') or resp.get('url'):
                        dl_url = resp.get('fileURL') or resp.get('url')
                        content, resp_mime = _fetch(dl_url, instance.token)
                        mime = resp.get('mimetype') or resp.get('mimeType') or resp_mime or ''
            except Exception as exc:
                self.stderr.write(f'    UAZAPI error: {exc}')

            if not content:
                self.stderr.write(f'    SKIP — no content retrieved')
                failed += 1
                continue

            # Determine correct extension from MIME
            mime_ext = mimetypes.guess_extension(mime) if mime else ''
            if not mime_ext or mime_ext in _BAD_EXTS:
                self.stderr.write(f'    SKIP — could not determine extension from mime={mime!r}')
                failed += 1
                continue

            # Build new MinIO key (same path, correct extension)
            base_key = os.path.splitext(old_key)[0]
            new_key = base_key + mime_ext
            content_type = mime or mimetypes.guess_type(new_key)[0] or 'application/octet-stream'

            try:
                s3.put_object(
                    Bucket=bucket,
                    Key=new_key,
                    Body=content,
                    ContentType=content_type,
                )
                # Delete old bad key
                try:
                    s3.delete_object(Bucket=bucket, Key=old_key)
                except Exception:
                    pass
                Mensagem.objects.filter(pk=msg.pk).update(media_minio_key=new_key)
                self.stdout.write(self.style.SUCCESS(
                    f'    OK  {old_key} → {new_key}  ({mime})'
                ))
                fixed += 1
            except Exception as exc:
                self.stderr.write(f'    MinIO error: {exc}')
                failed += 1

        self.stdout.write(f'\nDone. Fixed: {fixed}  Failed: {failed}' +
                          (' (DRY RUN)' if dry_run else ''))
