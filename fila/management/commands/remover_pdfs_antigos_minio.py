"""
Comando: python manage.py remover_pdfs_antigos_minio

Remove do MinIO os PDFs de OST e CT-e cujo registro foi criado há mais de 90 dias.
Limpa o campo pdf_storage_key no banco após remover o arquivo.
Use --dry-run para apenas listar o que seria removido (sem apagar).
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.utils import timezone

from fila.models import OST, CTe


class Command(BaseCommand):
    help = 'Remove do MinIO PDFs de OST e CT-e com mais de 90 dias (e limpa pdf_storage_key no banco).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dias',
            type=int,
            default=90,
            help='Remover PDFs com mais de N dias (padrão: 90).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Apenas listar o que seria removido, sem apagar.',
        )

    def handle(self, *args, **options):
        dias = options['dias']
        dry_run = options['dry_run']
        cutoff = timezone.now() - timedelta(days=dias)

        if dry_run:
            self.stdout.write(self.style.WARNING(f'Modo dry-run: nada será removido (cutoff: {cutoff.date()})'))

        removidos_ost = 0
        removidos_cte = 0
        erros = 0

        # OSTs
        qs_ost = OST.objects.filter(pdf_storage_key__gt='', criado_em__lt=cutoff)
        for ost in qs_ost:
            key = ost.pdf_storage_key
            if dry_run:
                self.stdout.write(f'  [OST {ost.pk}] {key}')
                removidos_ost += 1
                continue
            try:
                if default_storage.exists(key):
                    default_storage.delete(key)
                ost.pdf_storage_key = ''
                ost.save(update_fields=['pdf_storage_key'])
                removidos_ost += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Erro OST pk={ost.pk} {key}: {e}'))
                erros += 1

        # CT-es
        qs_cte = CTe.objects.filter(pdf_storage_key__gt='', criado_em__lt=cutoff)
        for cte in qs_cte:
            key = cte.pdf_storage_key
            if dry_run:
                self.stdout.write(f'  [CT-e {cte.pk}] {key}')
                removidos_cte += 1
                continue
            try:
                if default_storage.exists(key):
                    default_storage.delete(key)
                cte.pdf_storage_key = ''
                cte.save(update_fields=['pdf_storage_key'])
                removidos_cte += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Erro CT-e pk={cte.pk} {key}: {e}'))
                erros += 1

        total = removidos_ost + removidos_cte
        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f'Dry-run: {removidos_ost} OST(s) e {removidos_cte} CT-e(s) seriam processados (total {total}).'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Removidos: {removidos_ost} PDF(s) OST, {removidos_cte} PDF(s) CT-e (total {total}).'
            ))
        if erros:
            self.stderr.write(self.style.ERROR(f'Erros: {erros}'))
