"""
Extrator de dados de PDFs de Conhecimento de Transporte Eletrônico (CT-e).
Estrutura consistente: múltiplas páginas, cada página = 1 CT-e.
Aceita caminho (str) ou file-like (BytesIO). Sem output para XLS/CSV.
Uso: processar_pdf_por_pagina() para integrar com demembramento e MinIO.
"""
import re
import pdfplumber
from typing import Dict, List, Optional, Iterator, Tuple, Union


class ExtratorCTe:
    """
    Extrator de dados de CT-e.
    arquivo_pdf: caminho (str) ou file-like (BytesIO).
    """

    def __init__(self, arquivo_pdf: Union[str, bytes]):
        self.arquivo_pdf = arquivo_pdf
        self.dados_extraidos: List[Dict] = []

    def extrair_valor_total_por_coordenada(self, pagina) -> Optional[str]:
        palavras = pagina.extract_words()
        palavra_entrega = None
        for p in palavras:
            if p['text'].upper() == 'ENTREGA':
                palavra_entrega = p
                break
        if not palavra_entrega:
            return None
        y_referencia = palavra_entrega['top']
        valores_na_linha = []
        for p in palavras:
            if abs(p['top'] - y_referencia) <= 5 and p['x0'] > palavra_entrega['x1']:
                if 'INFORMA' in p['text'].upper():
                    break
                if re.match(r'^\d[\d.]*,\d{2}$', p['text']):
                    valores_na_linha.append(p['text'])
        if len(valores_na_linha) >= 2:
            return valores_na_linha[1]
        if len(valores_na_linha) == 1 and valores_na_linha[0] != '0,00':
            return valores_na_linha[0]
        return None

    def extrair_motorista_por_coordenada(self, pagina) -> Optional[str]:
        palavras = pagina.extract_words()
        palavra_nome = None
        for p in palavras:
            if 'NOME:' in p['text'].upper():
                palavra_nome = p
                break
        if not palavra_nome:
            return None
        y_referencia = palavra_nome['top']
        partes_nome = []
        texto_palavra = palavra_nome['text']
        if 'NOME:' in texto_palavra.upper():
            parte_inicial = texto_palavra.split(':', 1)[1].strip()
            if parte_inicial:
                partes_nome.append(parte_inicial)
        for p in palavras:
            if abs(p['top'] - y_referencia) <= 3 and p['x0'] > palavra_nome['x1']:
                if p['text'].upper() in ['CM', 'SR1', 'CPF:', 'RG:', 'CPF', 'RG']:
                    break
                if not p['text'].replace('.', '').replace('-', '').isdigit():
                    partes_nome.append(p['text'])
        if partes_nome:
            return ' '.join(partes_nome).strip()
        return None

    def extrair_campo(self, texto: str, padrao: str, grupo: int = 1) -> Optional[str]:
        match = re.search(padrao, texto, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(grupo).strip()
        return None

    def processar_pagina(self, texto: str, numero_pagina: int, pagina=None) -> Optional[Dict]:
        """
        Processa uma página e extrai todos os campos do CT-e.
        Retorna um dicionário ou None (ex.: filtrado DIV-0000).
        """
        numero_cte = self.extrair_campo(texto, r'Nro\.\s*Documento\s*(\d+)')
        filial = self.extrair_campo(texto, r'(?:MODELO|57)\s+(\d+)\s+\d+')
        serie = self.extrair_campo(texto, r'Serie[^\d]+?(\d+)')
        if not serie:
            serie = self.extrair_campo(texto, r'ASSINATURA/CARIMBO\s+(\d+)')

        data_emissao = self.extrair_campo(texto, r'(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}')
        hora_emissao = self.extrair_campo(texto, r'\d{2}/\d{2}/\d{4}\s+(\d{2}:\d{2})')
        if not data_emissao:
            data_emissao = self.extrair_campo(texto, r'DATA E HORA DE EMISSÃO[^\d]*(\d{2}/\d{2}/\d{4})')
        if not hora_emissao:
            hora_emissao = self.extrair_campo(texto, r'DATA E HORA DE EMISSÃO[^\d]*\d{2}/\d{2}/\d{4}\s+(\d{2}:\d{2})')

        match_linha = re.search(
            r'REMETENTE\s+(.+?)\s+DESTINAT[AÁ]RIO\s+(.+?)$', texto, re.MULTILINE
        )
        if match_linha:
            remetente = ' '.join(match_linha.group(1).split()).strip()
            destinatario = ' '.join(match_linha.group(2).split()).strip()
        else:
            remetente = destinatario = None

        municipio_remetente = self.extrair_campo(
            texto, r'REMETENTE.*?MUNICÍPIO\s+([A-Z\s]+?-\s*[A-Z]{2})\s+CEP'
        )
        municipio_destinatario = self.extrair_campo(
            texto, r'DESTINATÁRIO.*?MUNICÍPIO\s+([A-Z\s]+?-\s*[A-Z]{2})\s+CEP'
        )

        produto_predominante = self.extrair_campo(
            texto,
            r'PRODUTO PREDOMINANTE[^\n]+\n([A-Z0-9\s\-().,%/<>_]+?)\s+\d+[.,]\d+',
        )
        if produto_predominante:
            produto_predominante = ' '.join(produto_predominante.split()).strip()

        vlr_tarifa = self.extrair_campo(texto, r'QTD\.[^\n]+\n([\d.,]+)')
        peso_bruto = self.extrair_campo(texto, r'QTD\.[^\n]+\n[\d.,]+\s+([\d.]+,\d+)')
        frete_peso = self.extrair_campo(texto, r'FRETE PESO\s+([\d.,]+)')
        pedagio = self.extrair_campo(texto, r'PEDÁGIO\s+([\d.,]+)')

        valor_total = None
        if pagina:
            valor_total = self.extrair_valor_total_por_coordenada(pagina)
        if not valor_total:
            valor_total = self.extrair_campo(
                texto, r'(?:FRETE PESO|FRETE VALOR)[^\n]+?([\d.]+,\d+)\s*$'
            )
        if not valor_total:
            valor_total = self.extrair_campo(
                texto, r'VALOR TOTAL DA PRESTAÇÃO DO SERVIÇO[^\n]+?([\d.]+,\d+)'
            )
        if not valor_total:
            valor_total = self.extrair_campo(texto, r'VALOR A RECEBER[^\n]+?([\d.]+,\d+)')

        serie_nf = None
        nota_fiscal = None
        match_nfe = re.search(r'NFe\s+[\d.\-/]+\s+(\d+)\s*/\s*(\d+)', texto, re.IGNORECASE)
        if match_nfe:
            serie_nf = match_nfe.group(1)
            nota_fiscal = match_nfe.group(2)

        chave_nfe = self.extrair_campo(
            texto, r'NFe\s+[\d.\-/]+\s+\d+\s*/\s*\d+\s+(\d{44})'
        )
        if not chave_nfe:
            chave_nfe = self.extrair_campo(texto, r'CHAVE DE ACESSO NF-E[^\d]*(\d{44})')

        dt = self.extrair_campo(texto, r'DT:\s*([^\s\n]+)')
        if dt and dt.strip() in ('', '-', '0'):
            dt = None

        cnpj_proprietario = self.extrair_campo(
            texto, r'CNPJ/CPF PROPRIETÁRIO:\s*([\d.\-/]+)'
        )

        placa_cavalo = self.extrair_campo(texto, r'CM\s+([A-Z]{3}-?\d[A-Z0-9]\d{2})')
        placa_carreta = self.extrair_campo(texto, r'SR1\s+([A-Z]{3}-?\d[A-Z0-9]\d{2})')

        motorista = None
        if pagina:
            motorista = self.extrair_motorista_por_coordenada(pagina)
        if not motorista:
            motorista = self.extrair_campo(
                texto, r'NOME:\s*([A-Z][A-Z\s]+?)(?=\s*(?:CPF|RG|\d{3}\.\d{3}|$))'
            )
            if motorista:
                motorista = motorista.strip()

        if placa_cavalo and 'DIV-0000' in placa_cavalo.upper():
            return None

        return {
            'filial': filial,
            'serie': serie,
            'numero_cte': numero_cte,
            'data_emissao': data_emissao,
            'hora_emissao': hora_emissao,
            'remetente': remetente,
            'municipio_remetente': municipio_remetente,
            'destinatario': destinatario,
            'municipio_destinatario': municipio_destinatario,
            'produto_predominante': produto_predominante,
            'vlr_tarifa': vlr_tarifa,
            'peso_bruto': peso_bruto,
            'frete_peso': frete_peso,
            'pedagio': pedagio,
            'valor_total': valor_total,
            'serie_nf': serie_nf,
            'nota_fiscal': nota_fiscal,
            'chave_nfe': chave_nfe,
            'dt': dt,
            'cnpj_proprietario': cnpj_proprietario,
            'placa_cavalo': placa_cavalo,
            'placa_carreta': placa_carreta,
            'motorista': motorista,
        }

    def processar_pdf(self) -> List[Dict]:
        """Processa todas as páginas. Retorna lista de dicionários (um por página)."""
        with pdfplumber.open(self.arquivo_pdf) as pdf:
            for i, pagina in enumerate(pdf.pages, start=1):
                texto = pagina.extract_text()
                if not texto:
                    continue
                dados = self.processar_pagina(texto, i, pagina)
                if dados is not None:
                    self.dados_extraidos.append(dados)
        return self.dados_extraidos

    def processar_pdf_por_pagina(self) -> Iterator[Tuple[int, List[Dict]]]:
        """
        Processa o PDF página a página. Gera (índice_página_0based, lista_de_registros).
        Cada página gera no máximo um registro (um CT-e). Lista tem 0 ou 1 elemento.
        """
        with pdfplumber.open(self.arquivo_pdf) as pdf:
            for idx, pagina in enumerate(pdf.pages):
                texto = pagina.extract_text()
                if not texto:
                    yield idx, []
                    continue
                dados = self.processar_pagina(texto, idx + 1, pagina)
                if dados is not None:
                    yield idx, [dados]
                else:
                    yield idx, []
