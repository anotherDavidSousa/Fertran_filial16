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

    def _get(self, path, params=None):
        try:
            r = requests.get(
                f'{self.base_url}{path}', params=params,
                headers=self.headers, timeout=15,
            )
            r.raise_for_status()
            return True, r.json()
        except requests.RequestException as exc:
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
        """Fetch profile/group picture URL for a JID. Returns (ok, url_str | error_str)."""
        # Try group endpoint first, then contact endpoint
        if jid.endswith('@g.us'):
            ok, resp = self._get('/group/picture', {'id': jid})
        else:
            ok, resp = self._get('/contact/picture', {'number': jid})
        if not ok:
            return False, resp
        if isinstance(resp, dict):
            url = resp.get('url') or resp.get('eurl') or resp.get('profilePicture') or ''
            return bool(url), url
        return False, ''

    def list_groups(self):
        """List all groups. Returns (ok, list | error_str)."""
        return self._get('/group/list')

    def instance_status(self):
        """Check connection status. Returns (ok, dict | error_str)."""
        return self._get('/instance/status')
