from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from fila.models import ApiKey


class Command(BaseCommand):
    help = 'Gera uma API Key para um usuário (integração n8n / X-Api-Key).'

    def add_arguments(self, parser):
        parser.add_argument('--usuario', required=True, help='Username do usuário Django')
        parser.add_argument('--descricao', default='', help='Descrição (ex.: n8n produção)')

    def handle(self, *args, **options):
        username = options['usuario']
        descricao = options['descricao'] or ''
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f'Usuário "{username}" não encontrado.') from exc

        key = ApiKey.gerar_para_usuario(user, descricao=descricao)
        self.stdout.write(self.style.SUCCESS('API Key gerada com sucesso!'))
        self.stdout.write(f'   Token: {key.token}')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('Guarde o token — em edições futuras no admin ele não é mostrado em claro.'))
