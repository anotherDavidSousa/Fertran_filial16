"""
Comando: python manage.py sync_googlesheets

Limpa toda a aba configurada (exceto o cabeçalho) e reconstrói com os cavalos
que entram na lista (com carreta acoplada ou bi-truck, não desagregados),
na mesma ordem da tela de cavalos.
"""
from django.core.management.base import BaseCommand
from django.db.models import Q, Case, When, Value, IntegerField, F, CharField

from core.models import Cavalo
from core.google_sheets import _get_worksheet, _get_cavalo_row_data


class Command(BaseCommand):
    help = 'Limpa a aba do Google Sheets e reconstrói com todos os cavalos (com carreta ou bi-truck), na ordem da lista.'

    def handle(self, *args, **options):
        worksheet = _get_worksheet()
        if not worksheet:
            self.stderr.write(
                self.style.ERROR(
                    'Google Sheets não está habilitado ou credenciais/planilha não configuradas. '
                    'Verifique GOOGLE_SHEETS_ENABLED, GOOGLE_SHEETS_CREDENTIALS_PATH e GOOGLE_SHEETS_SPREADSHEET_ID no .env'
                )
            )
            return

        self.stdout.write('Limpando dados da aba...')
        try:
            row_count = worksheet.row_count
            if row_count > 1:
                worksheet.delete_rows(2, row_count)
            self.stdout.write(self.style.SUCCESS('Linhas antigas removidas.'))
        except Exception as e:
            try:
                worksheet.batch_clear(['A2:N1000'])
                self.stdout.write(self.style.SUCCESS('Conteúdo A2:M1000 limpo.'))
            except Exception as e2:
                self.stderr.write(self.style.ERROR(f'Erro ao limpar: {e} / {e2}'))
                return

        headers = [
            'Cavalo', 'Carreta', 'Motorista', 'Cavalo_MG', 'Carreta_MG', 'CPF', 'Tipo', 'Fluxo',
            'Classificação', 'Codigo_parceiro', 'Tipo Parceiro', 'Parceiro', 'Situação'
        ]
        try:
            worksheet.update('A1:M1', [headers], value_input_option='RAW')
        except Exception as e:
            self.stderr.write(self.style.WARNING(f'Aviso ao escrever cabeçalho: {e}'))

        qs = Cavalo.objects.select_related('motorista', 'carreta', 'proprietario').filter(
            Q(carreta__isnull=False) | Q(tipo='bi_truck')
        ).exclude(situacao='desagregado').annotate(
            ordem_classificacao=Case(
                When(classificacao='agregado', then=Value(0)),
                When(classificacao='frota', then=Value(1)),
                When(classificacao='terceiro', then=Value(2)),
                default=Value(0),
                output_field=IntegerField(),
            ),
            ordem_situacao=Case(
                When(situacao='ativo', then=Value(0)),
                When(situacao='parado', then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            ),
            ordem_fluxo=Case(
                When(fluxo='escoria', then=Value(0)),
                When(fluxo='minerio', then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            ),
            ordem_tipo=Case(
                When(tipo='toco', then=Value(0)),
                When(tipo='trucado', then=Value(1)),
                When(tipo='bi_truck', then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            ),
            motorista_nome_ordem=Case(
                When(motorista__isnull=False, then=F('motorista__nome')),
                default=Value(''),
                output_field=CharField(),
            ),
        ).order_by(
            'ordem_classificacao', 'ordem_situacao', 'ordem_fluxo', 'ordem_tipo', 'motorista_nome_ordem'
        )

        cavalos = list(qs)
        if not cavalos:
            self.stdout.write(self.style.WARNING('Nenhum cavalo para enviar (lista vazia).'))
            return

        rows = []
        for cavalo in cavalos:
            row_data = _get_cavalo_row_data(cavalo)
            rows.append([
                row_data.get('A', ''),
                row_data.get('B', ''),
                row_data.get('C', ''),
                row_data.get('D', ''),
                row_data.get('E', ''),
                row_data.get('F', ''),
                row_data.get('G', ''),
                row_data.get('H', ''),
                row_data.get('I', ''),
                row_data.get('J', ''),
                row_data.get('K', ''),
                row_data.get('L', ''),
                row_data.get('M', ''),
                row_data.get('N', ''),
            ])

        try:
            end_row = 1 + len(rows)
            worksheet.update(f'A2:N{end_row}', rows, value_input_option='RAW')
            self.stdout.write(self.style.SUCCESS(f'Sincronização concluída: {len(rows)} cavalo(s) enviado(s) para a planilha.'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Erro ao atualizar planilha: {e}'))
