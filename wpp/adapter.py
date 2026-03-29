"""
Adapter for all UAZAPI HTTP API calls.
All network communication with the WhatsApp backend is isolated here.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class UazapiAdapter:
    """Wraps UAZAPI REST endpoints for a single WppInstance."""

    def __init__(self, instance):
        base = getattr(settings, 'UAZAPI_BASE_URL', '').rstrip('/')
        self.base_url = base
        self.headers = {
            'token': instance.token,
            'Content-Type': 'application/json',
        }

    def _post(self, path, data):
        try:
            r = requests.post(
                f'{self.base_url}{path}', json=data,
                headers=self.headers, timeout=15,
            )
            r.raise_for_status()
            return True, r.json()
        except requests.RequestException as exc:
            logger.error('UAZAPI POST %s failed: %s', path, exc)
            return False, str(exc)

    def _get(self, path, params=None, silent=False):
        try:
            r = requests.get(
                f'{self.base_url}{path}', params=params,
                headers=self.headers, timeout=15,
            )
            r.raise_for_status()
            return True, r.json()
        except requests.RequestException as exc:
            if not silent:
                logger.error('UAZAPI GET %s failed: %s', path, exc)
            return False, str(exc)

    def send_text(self, number, text):
        """Send a plain text message. Returns (ok, response_dict | error_str)."""
        return self._post('/send/text', {'number': number, 'text': text})

    def download_media(self, message_id):
        """Download media by message ID. Returns (ok, response_dict | error_str).
        UAZAPI response typically contains {base64, mimetype, filename} or {url}.
        """
        return self._post('/message/download', {'id': message_id})

    def get_picture(self, jid):
        """Fetch profile/group picture URL for a JID. Returns (ok, url_str | error_str).

        Tries multiple UAZAPI endpoint variants until one works.
        """
        candidates = []
        if jid.endswith('@g.us'):
            candidates = [
                ('GET', '/group/photo', {'id': jid}),
                ('GET', '/group/picture', {'id': jid}),
                ('POST', '/group/photo', {'groupId': jid}),
            ]
        else:
            phone = jid.split('@')[0]
            candidates = [
                ('GET', '/contact/photo', {'number': phone}),
                ('GET', '/contact/photo', {'number': jid}),
                ('GET', '/contact/picture', {'number': phone}),
                ('POST', '/contact/photo', {'number': phone}),
            ]

        for method, path, params in candidates:
            try:
                if method == 'GET':
                    ok, resp = self._get(path, params, silent=True)
                else:
                    ok, resp = self._post(path, params)
                if ok and isinstance(resp, dict):
                    url = (resp.get('url') or resp.get('eurl') or
                           resp.get('profilePicture') or resp.get('photo') or
                           resp.get('imgUrl') or '')
                    if url:
                        logger.info('UAZAPI get_picture %s %s → url=%r', method, path, url[:80])
                        return True, url
                elif ok and isinstance(resp, str) and resp.startswith('http'):
                    logger.info('UAZAPI get_picture %s %s → str url', method, path)
                    return True, resp
            except Exception:
                pass
        return False, ''

    def list_groups(self):
        """List all groups. Returns (ok, list | error_str)."""
        return self._get('/group/list')

    def instance_status(self):
        """Check connection status. Returns (ok, dict | error_str)."""
        return self._get('/instance/status')
