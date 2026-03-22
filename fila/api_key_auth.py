"""Autenticação REST por header X-Api-Key (integração n8n / sistemas externos)."""
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ApiKeyAuthentication(BaseAuthentication):
    HEADER = 'HTTP_X_API_KEY'

    def authenticate(self, request):
        token = request.META.get(self.HEADER)
        if not token:
            return None
        from .models import ApiKey

        try:
            api_key = ApiKey.objects.select_related('user').get(token=token, ativo=True)
        except ApiKey.DoesNotExist:
            raise AuthenticationFailed('API Key inválida ou inativa.')
        ApiKey.objects.filter(pk=api_key.pk).update(ultimo_uso=timezone.now())
        return (api_key.user, api_key)

    def authenticate_header(self, request):
        return 'X-Api-Key'
