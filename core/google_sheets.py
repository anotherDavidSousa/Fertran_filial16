"""
Módulo para sincronizar dados de Cavalos com Google Sheets

COMO FUNCIONA:
1. Quando um cavalo é salvo ou deletado, um signal é disparado
2. O signal chama a função específica (adicionar/atualizar/deletar) em background
3. A função busca a linha na planilha pela placa e atualiza apenas aquela linha
4. Preserva todas as formatações e colunas extras

CONFIGURAÇÃO NECESSÁRIA (no settings.py ou .env):
- GOOGLE_SHEETS_CREDENTIALS_PATH: caminho para o arquivo JSON da Service Account
- GOOGLE_SHEETS_SPREADSHEET_ID: ID da planilha do Google Sheets
- GOOGLE_SHEETS_WORKSHEET_NAME: nome da aba (padrão: 'Cavalos')
- GOOGLE_SHEETS_ENABLED: True/False para habilitar/desabilitar (padrão: False)
"""

import os
import time
import threading
import logging
from django.conf import settings
from django.db.models import Case, When, Value, IntegerField, F, CharField, Q

logger = logging.getLogger(__name__)


def _get_worksheet():
    try:
        if not getattr(settings, 'GOOGLE_SHEETS_ENABLED', False):
            return None
        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError:
            logger.error("Biblioteca gspread não instalada. Execute: pip install gspread google-auth")
            return None
        credentials_path = getattr(settings, 'GOOGLE_SHEETS_CREDENTIALS_PATH', None)
        spreadsheet_id = getattr(settings, 'GOOGLE_SHEETS_SPREADSHEET_ID', None)
        worksheet_name = getattr(settings, 'GOOGLE_SHEETS_WORKSHEET_NAME', 'Cavalos')
        if not credentials_path or not spreadsheet_id:
            logger.error("Configurações do Google Sheets não encontradas no settings.py")
            return None
        if not os.path.exists(credentials_path):
            logger.error(f"Arquivo de credenciais não encontrado: {credentials_path}")
            return None
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(spreadsheet_id)
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
            try:
                current_cols = worksheet.col_count
                if current_cols < 13:
                    logger.info(f"Expandindo planilha existente de {current_cols} para 13 colunas...")
                    worksheet.resize(rows=worksheet.row_count, cols=13)
            except Exception as e:
                logger.warning(f"Erro ao expandir planilha existente: {str(e)}")
        except gspread.exceptions.WorksheetNotFound:
            logger.info(f"Aba '{worksheet_name}' não encontrada. Criando...")
            worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=13)
            headers = [
                'PLACA', 'CARRETA', 'PLACA MG', 'CARRETA MG', 'MOTORISTA', 'CPF', 'TIPO', 'FLUXO',
                'CLASSIFICAÇÃO', 'CÓDIGO DO PROPRIETÁRIO', 'TIPO DO PROPRIETÁRIO', 'PROPRIETÁRIO', 'SITUAÇÃO'
            ]
            worksheet.update('A1:M1', [headers], value_input_option='RAW')
        return worksheet
    except Exception as e:
        logger.error(f"Erro ao conectar ao Google Sheets: {str(e)}", exc_info=True)
        return None


def _find_row_by_placa(worksheet, placa):
    try:
        placas = worksheet.col_values(1)
        for idx, placa_na_planilha in enumerate(placas[1:], start=2):
            if placa_na_planilha and placa_na_planilha.strip().upper() == placa.strip().upper():
                return idx
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar placa na planilha: {str(e)}")
        return None


def _get_cavalo_row_data(cavalo):
    try:
        motorista_nome = cavalo.motorista.nome if cavalo.motorista else '-'
        motorista_cpf = cavalo.motorista.cpf if cavalo.motorista and cavalo.motorista.cpf else '-'
    except Exception:
        motorista_nome = '-'
        motorista_cpf = '-'
    placa_cavalo = cavalo.placa or '-'
    placa_cavalo_mg = f"{placa_cavalo}MG" if placa_cavalo != '-' else '-'
    if cavalo.tipo == 'bi_truck':
        placa_carreta = 'S/Placa'
        placa_carreta_mg = 'S/Placa'
    else:
        placa_carreta = cavalo.carreta.placa if cavalo.carreta else '-'
        placa_carreta_mg = f"{placa_carreta}MG" if placa_carreta != '-' else '-'
    tipo_proprietario = '-'
    if cavalo.proprietario and cavalo.proprietario.tipo:
        tipo_proprietario = cavalo.proprietario.tipo
    return {
        'A': placa_cavalo,
        'B': placa_carreta,
        'C': placa_cavalo_mg,
        'D': placa_carreta_mg,
        'E': motorista_nome,
        'F': motorista_cpf,
        'G': cavalo.get_tipo_display() if cavalo.tipo else '-',
        'H': cavalo.get_fluxo_display() if cavalo.fluxo else '-',
        'I': cavalo.get_classificacao_display() if cavalo.classificacao else '-',
        'J': cavalo.proprietario.codigo if cavalo.proprietario and cavalo.proprietario.codigo else '-',
        'K': tipo_proprietario,
        'L': cavalo.proprietario.nome_razao_social if cavalo.proprietario else '-',
        'M': cavalo.get_situacao_display() if cavalo.situacao else '-',
    }


def _get_insert_position(worksheet, cavalo):
    try:
        from .models import Cavalo
        try:
            cavalo = Cavalo.objects.select_related('motorista', 'carreta', 'proprietario', 'gestor').get(pk=cavalo.pk)
        except Cavalo.DoesNotExist:
            return 2
        todos_cavalos = Cavalo.objects.select_related('motorista', 'carreta', 'proprietario', 'gestor').filter(
            Q(carreta__isnull=False) | Q(tipo='bi_truck')
        ).exclude(situacao='desagregado').annotate(
            ordem_classificacao=Case(
                When(classificacao='agregado', then=Value(0)),
                When(classificacao='frota', then=Value(1)),
                When(classificacao='terceiro', then=Value(2)),
                default=Value(0),
                output_field=IntegerField()
            ),
            ordem_situacao=Case(
                When(situacao='ativo', then=Value(0)),
                When(situacao='parado', then=Value(1)),
                default=Value(2),
                output_field=IntegerField()
            ),
            ordem_fluxo=Case(
                When(fluxo='escoria', then=Value(0)),
                When(fluxo='minerio', then=Value(1)),
                default=Value(2),
                output_field=IntegerField()
            ),
            ordem_tipo=Case(
                When(tipo='toco', then=Value(0)),
                When(tipo='trucado', then=Value(1)),
                When(tipo='bi_truck', then=Value(2)),
                default=Value(3),
                output_field=IntegerField()
            ),
            motorista_nome_ordem=Case(
                When(motorista__isnull=False, then=F('motorista__nome')),
                default=Value(''),
                output_field=CharField()
            ),
        ).order_by(
            'ordem_classificacao',
            'ordem_situacao',
            'ordem_fluxo',
            'ordem_tipo',
            'motorista_nome_ordem'
        )
        classificacao_ordem = 0 if (cavalo.classificacao == 'agregado' or not cavalo.classificacao) else (1 if cavalo.classificacao == 'frota' else 2)
        tipo_ordem = 0 if cavalo.tipo == 'toco' else (1 if cavalo.tipo == 'trucado' else (2 if cavalo.tipo == 'bi_truck' else 3))
        motorista_nome = ''
        try:
            if cavalo.motorista:
                motorista_nome = getattr(cavalo.motorista, 'nome', '') or ''
        except (AttributeError, Exception):
            motorista_nome = ''
        cavalo_ordem = (
            classificacao_ordem,
            (0 if cavalo.situacao == 'ativo' else 1 if cavalo.situacao == 'parado' else 2),
            (0 if cavalo.fluxo == 'escoria' else 1 if cavalo.fluxo == 'minerio' else 2),
            tipo_ordem,
            motorista_nome
        )
        posicao = 1
        for outro_cavalo in todos_cavalos:
            if outro_cavalo.pk == cavalo.pk:
                break
            outro_classificacao_ordem = 0 if (outro_cavalo.classificacao == 'agregado' or not outro_cavalo.classificacao) else (1 if outro_cavalo.classificacao == 'frota' else 2)
            outro_tipo_ordem = 0 if outro_cavalo.tipo == 'toco' else (1 if outro_cavalo.tipo == 'trucado' else (2 if outro_cavalo.tipo == 'bi_truck' else 3))
            outro_motorista_nome = ''
            try:
                if outro_cavalo.motorista:
                    outro_motorista_nome = getattr(outro_cavalo.motorista, 'nome', '') or ''
            except (AttributeError, Exception):
                outro_motorista_nome = ''
            outro_ordem = (
                outro_classificacao_ordem,
                (0 if outro_cavalo.situacao == 'ativo' else 1 if outro_cavalo.situacao == 'parado' else 2),
                (0 if outro_cavalo.fluxo == 'escoria' else 1 if outro_cavalo.fluxo == 'minerio' else 2),
                outro_tipo_ordem,
                outro_motorista_nome
            )
            if outro_ordem < cavalo_ordem:
                posicao += 1
        return posicao + 1
    except Exception as e:
        logger.error(f"Erro ao calcular posição de inserção: {str(e)}")
        try:
            all_values = worksheet.get_all_values()
            return len([row for row in all_values[1:] if any(cell.strip() for cell in row)]) + 2
        except Exception:
            return 2


def update_cavalo_in_sheets(cavalo_pk):
    try:
        from .models import Cavalo
        try:
            cavalo = Cavalo.objects.select_related('motorista', 'carreta', 'proprietario').get(pk=cavalo_pk)
        except Cavalo.DoesNotExist:
            logger.warning(f"Cavalo com ID {cavalo_pk} não encontrado")
            return False
        deve_exibir = False
        if cavalo.tipo == 'bi_truck':
            deve_exibir = cavalo.situacao != 'desagregado'
        else:
            deve_exibir = cavalo.carreta is not None and cavalo.situacao != 'desagregado'
        if not deve_exibir:
            return delete_cavalo_from_sheets(cavalo.placa)
        worksheet = _get_worksheet()
        if not worksheet:
            return False
        if not cavalo.placa:
            logger.warning(f"Cavalo {cavalo_pk} não tem placa")
            return False
        row_num = _find_row_by_placa(worksheet, cavalo.placa)
        if row_num:
            row_data_dict = _get_cavalo_row_data(cavalo)
            try:
                current_cols = worksheet.col_count
                if current_cols < 13:
                    worksheet.resize(rows=worksheet.row_count, cols=13)
            except Exception:
                pass
            updates = [{'range': f'{col}{row_num}', 'values': [[value]]} for col, value in row_data_dict.items()]
            worksheet.batch_update(updates, value_input_option='RAW')
            logger.info(f"Cavalo {cavalo.placa} atualizado na linha {row_num} do Google Sheets")
            return True
        else:
            return add_cavalo_to_sheets(cavalo_pk)
    except Exception as e:
        logger.error(f"Erro ao atualizar cavalo no Google Sheets: {str(e)}", exc_info=True)
        return False


def add_cavalo_to_sheets(cavalo_pk):
    try:
        from .models import Cavalo
        try:
            cavalo = Cavalo.objects.select_related('motorista', 'carreta', 'proprietario').get(pk=cavalo_pk)
        except Cavalo.DoesNotExist:
            logger.warning(f"Cavalo com ID {cavalo_pk} não encontrado")
            return False
        if cavalo.tipo == 'bi_truck':
            deve_exibir = cavalo.situacao != 'desagregado'
        else:
            deve_exibir = cavalo.carreta is not None and cavalo.situacao != 'desagregado'
        if not deve_exibir:
            return False
        if not cavalo.placa:
            return False
        worksheet = _get_worksheet()
        if not worksheet:
            return False
        if _find_row_by_placa(worksheet, cavalo.placa):
            return update_cavalo_in_sheets(cavalo_pk)
        row_num = _get_insert_position(worksheet, cavalo)
        try:
            current_cols = worksheet.col_count
            if current_cols < 13:
                worksheet.resize(rows=worksheet.row_count, cols=13)
        except Exception:
            pass
        row_data_dict = _get_cavalo_row_data(cavalo)
        row_data_list = [
            row_data_dict.get('A', ''), row_data_dict.get('B', ''), row_data_dict.get('C', ''),
            row_data_dict.get('D', ''), row_data_dict.get('E', ''), row_data_dict.get('F', ''),
            row_data_dict.get('G', ''), row_data_dict.get('H', ''), row_data_dict.get('I', ''),
            row_data_dict.get('J', ''), row_data_dict.get('K', ''), row_data_dict.get('L', ''),
            row_data_dict.get('M', ''),
        ]
        worksheet.insert_row(row_data_list, row_num, value_input_option='RAW')
        logger.info(f"Cavalo {cavalo.placa} adicionado na linha {row_num} do Google Sheets")
        return True
    except Exception as e:
        logger.error(f"Erro ao adicionar cavalo no Google Sheets: {str(e)}", exc_info=True)
        return False


def delete_cavalo_from_sheets(placa):
    try:
        if not placa:
            return False
        worksheet = _get_worksheet()
        if not worksheet:
            return False
        row_num = _find_row_by_placa(worksheet, placa)
        if row_num:
            worksheet.delete_rows(row_num)
            logger.info(f"Cavalo {placa} deletado da linha {row_num} do Google Sheets")
            return True
        return False
    except Exception as e:
        logger.error(f"Erro ao deletar cavalo do Google Sheets: {str(e)}", exc_info=True)
        return False


def update_cavalo_async(cavalo_pk):
    thread = threading.Thread(target=update_cavalo_in_sheets, args=(cavalo_pk,), daemon=True)
    thread.start()


def add_cavalo_async(cavalo_pk):
    thread = threading.Thread(target=add_cavalo_to_sheets, args=(cavalo_pk,), daemon=True)
    thread.start()


def delete_cavalo_async(placa):
    thread = threading.Thread(target=delete_cavalo_from_sheets, args=(placa,), daemon=True)
    thread.start()
