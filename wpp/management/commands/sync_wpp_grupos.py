"""Management command: sync WhatsApp groups from all active UAZAPI instances."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from wpp.adapter import UazapiAdapter
from wpp.models import GrupoConfig, WppInstance


class Command(BaseCommand):
    help = 'Sincroniza grupos do WhatsApp via UAZAPI'

    def handle(self, *args, **options):
        instances = WppInstance.objects.filter(ativo=True)
        if not instances.exists():
            self.stderr.write('Nenhuma instância ativa encontrada.')
            return

        for instance in instances:
            self.stdout.write(f'Sincronizando instância: {instance.nome}')
            adapter = UazapiAdapter(instance)
            ok, groups = adapter.list_groups()
            if not ok:
                self.stderr.write(f'  Erro ao listar grupos: {groups}')
                continue

            if not isinstance(groups, list):
                groups = groups.get('groups') or groups.get('data') or []

            count = 0
            for g in groups:
                jid = g.get('id') or g.get('jid') or ''
                nome = g.get('name') or g.get('subject') or ''
                if not jid:
                    continue
                obj, created = GrupoConfig.objects.get_or_create(
                    jid=jid,
                    defaults={'instance': instance, 'nome': nome},
                )
                if not created and nome and obj.nome != nome:
                    obj.nome = nome
                    obj.save(update_fields=['nome', 'placa_cavalo'])
                obj.sincronizado_em = timezone.now()
                obj.save(update_fields=['sincronizado_em'])
                count += 1
                action = 'criado' if created else 'atualizado'
                self.stdout.write(f'  [{action}] {nome or jid}')

            self.stdout.write(
                self.style.SUCCESS(f'  {count} grupo(s) sincronizado(s) para {instance.nome}.')
            )
