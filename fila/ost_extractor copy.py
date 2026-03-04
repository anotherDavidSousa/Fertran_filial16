"""
Extrator de dados de PDFs de Ordem de Serviço de Transporte (OST).
Estrutura consistente, múltiplas páginas, cada página = 1 documento.
Sem prints; aceita caminho de arquivo ou file-like (upload).
"""
import re
import pdfplumber
from typing import Dict, List, Optional, Iterator, Tuple


class ExtratorOST:
    """
    Extrator de dados de Ordem de Serviço de Transporte.
    Aceita arquivo_pdf como str (path) ou file-like (ex.: BytesIO do upload).
    """

    PRODUTOS_CONHECIDOS = [
        'MINERIO DE FERRO SINTER FEED BT',
        'MINERIO DE FERRO SINTER FEED',
        'MINERIO FERRO SINTER FEED BT',
        'MINERIO DE FERRO-ROM TEOR DE FERRO 51%',
        'BARITA',
        'CONCENTRADO',
        'SINTER FEED',
        'AREIA A 2',
        'GESSO',
        'MP ATHOS 03 32 08 + 0,1 B+ 0,2 ZN',
        'SUPERFOSFATO TRIPLO (TSP) - GRANULADO',
        'PELLET FEED',
    ]

    def __init__(self, arquivo_pdf):
        """
        arquivo_pdf: caminho (str) ou file-like (BytesIO, UploadedFile, etc.)
        """
        self.arquivo_pdf = arquivo_pdf
        self.dados_extraidos = []

    def tentar_match_produto_conhecido(self, linha: str) -> Optional[str]:
        linha_upper = linha.upper().strip()
        for produto in self.PRODUTOS_CONHECIDOS:
            if linha_upper.startswith(produto.upper()):
                return produto
        for produto in self.PRODUTOS_CONHECIDOS:
            produto_upper = produto.upper()
            trecho_linha = linha_upper[:len(produto_upper)]
            matches = sum(1 for a, b in zip(trecho_linha, produto_upper) if a == b)
            similaridade = matches / len(produto_upper) if produto_upper else 0
            if similaridade >= 0.90:
                return produto
        return None

    def extrair_campo(self, texto: str, padrao: str, grupo: int = 1) -> Optional[str]:
        match = re.search(padrao, texto, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(grupo).strip()
        return None

    def extrair_peso_por_coordenada(self, pagina, y_linha: float) -> Optional[str]:
        palavras = pagina.extract_words()
        x_peso = None
        for p in palavras:
            if p['text'] == 'PESO.KG':
                x_peso = (p['x0'] + p['x1']) / 2
                break
        if x_peso is None:
            return None
        melhor = None
        menor_distancia = 30
        for p in palavras:
            if abs(p['top'] - y_linha) > 5:
                continue
            x_centro = (p['x0'] + p['x1']) / 2
            distancia = abs(x_centro - x_peso)
            if distancia < menor_distancia and re.match(r'^\d[\d.]+$', p['text']):
                melhor = p['text']
                menor_distancia = distancia
        return melhor

    def processar_pagina(self, texto: str, numero_pagina: int, pagina=None) -> List[Dict]:
        numero_ost = self.extrair_campo(
            texto,
            r'ORDEM DE SERVIÇO DE TRANSPORTE - Nº\.: (.+?)(?=\n)'
        )
        data_averbacao = self.extrair_campo(
            texto,
            r'Data/hora da averbação:\s*(\d{2}/\d{2}/\d{4})'
        )
        hora_averbacao = self.extrair_campo(
            texto,
            r'Data/hora da averbação:\s*\d{2}/\d{2}/\d{4}\s+(\d{2}:\d{2}:\d{2})'
        )
        remetente = self.extrair_campo(
            texto,
            r'Remetente\s*:\s*(.+?)(?=\s+C[oó]digo)'
        )
        destinatario = self.extrair_campo(
            texto,
            r'Destinat[aá]rio\s*:\s*(.+?)(?=\s+Codigo)'
        )
        terminal_entrega = self.extrair_campo(
            texto,
            r'Terminal Entrega\s*:\s*(.+?)(?=PRODUTO|Tomador|Motorista|\n\n)'
        )
        motorista = self.extrair_campo(
            texto,
            r'Motorista\s*:\s*(.+?)(?=\s+CPF:)'
        )
        placa_1 = None
        placa_2 = None
        linha_placas = self.extrair_campo(texto, r'Placa:\s*(.+?)(?=\n|ANTT)')
        if linha_placas:
            placas = re.findall(r'[A-Z0-9]{7}', linha_placas, re.IGNORECASE)
            placa_1 = placas[0] if len(placas) > 0 else None
            placa_2 = placas[1] if len(placas) > 1 else None
        proprietario = self.extrair_campo(
            texto,
            r'Proprietário\s*:\s*(.+?)(?=\s+CNPJ/CPF:)'
        )
        total_frete = self.extrair_campo(texto, r'Total Frete:\s*([\d.,]+)')
        pedagio = self.extrair_campo(texto, r'Pedágio:\s*([\d.,]+)')
        valor_tarifa = self.extrair_campo(texto, r'Valor Tarifa:\s*([\d.,]+)')
        bloco_produtos = self.extrair_campo(
            texto,
            r'COMPOSIÇÃO DE CARGA\s*\n.*?PRODUTO.*?(?:CHAVE\s+NF|NF)\s*\n(.+?)(?=\nTotal:)',
        )
        linha_total = self.extrair_campo(texto, r'Total:\s*(.+?)(?=\n|$)')
        produtos_lista = []
        nomes_produtos = []
        if bloco_produtos:
            linhas = bloco_produtos.strip().split('\n')
            for linha in linhas:
                linha = linha.strip()
                if not linha or linha.startswith('Total'):
                    continue
                linha_limpa = re.sub(r'([A-Z])(\d)', r'\1 \2', linha)
                linha_limpa = re.sub(r'(\d)([A-Z])(\d)', r'\1\3', linha_limpa)
                linha_limpa = re.sub(r'\s+', ' ', linha_limpa)
                linha_limpa = re.sub(r'\d+\.?\d*%\d*', '', linha_limpa)
                produto = self.tentar_match_produto_conhecido(linha_limpa)
                if not produto:
                    produto_match = re.match(r'^(.+?)\s+(?=\d{2,}[.,]\d)', linha_limpa)
                    produto = produto_match.group(1).strip() if produto_match else None
                if produto:
                    nomes_produtos.append(produto)
                numeros = re.findall(r'[\d.,/]+', linha_limpa)
                peso = None
                if pagina is not None:
                    palavras_pagina = pagina.extract_words()
                    y_linha = None
                    for p in palavras_pagina:
                        if produto and p['text'] in (produto or '').split()[:2]:
                            y_linha = p['top']
                            break
                    if y_linha:
                        peso = self.extrair_peso_por_coordenada(pagina, y_linha)
                if not peso:
                    peso = numeros[1] if len(numeros) > 1 else None
                nf_ticket = None
                for num in numeros[2:]:
                    if ',' in num or '.' in num:
                        continue
                    if len(num) >= 4 and '/' not in num:
                        nf_ticket = num
                        break
                data_nf = None
                data_match = re.search(r'\d{2}/\d{2}/\d{4}', linha_limpa)
                if data_match:
                    data_nf = data_match.group()
                chave_nf = None
                chave_match = re.search(r'\d{30,}', linha_limpa)
                if chave_match:
                    chave_nf = chave_match.group()
                produtos_lista.append({
                    'produto': produto,
                    'peso': peso,
                    'nf_ticket': nf_ticket,
                    'data_nf': data_nf,
                    'chave_nf': chave_nf
                })
        if len(produtos_lista) > 1 and linha_total:
            numeros_total = re.findall(r'[\d.,]+', linha_total)
            peso_total = numeros_total[2] if len(numeros_total) > 2 else None
            nf_tickets = [p['nf_ticket'] for p in produtos_lista if p['nf_ticket']]
            nf_tickets_concatenados = ' + '.join(nf_tickets) if nf_tickets else None
            datas_nf = [p['data_nf'] for p in produtos_lista if p['data_nf']]
            datas_nf_concatenadas = ' + '.join(datas_nf) if datas_nf else None
            produtos_lista = [{
                'produto': None,
                'peso': peso_total,
                'nf_ticket': nf_tickets_concatenados,
                'data_nf': datas_nf_concatenadas,
                'chave_nf': None
            }]
        if not produtos_lista:
            produtos_lista.append({
                'produto': None,
                'peso': None,
                'nf_ticket': None,
                'data_nf': None,
                'chave_nf': None
            })
        registros = []
        for prod_info in produtos_lista:
            dados = {
                'numero_ost': numero_ost,
                'data_averbacao': data_averbacao,
                'hora_averbacao': hora_averbacao,
                'remetente': remetente,
                'destinatario': destinatario,
                'terminal_entrega': terminal_entrega,
                'motorista': motorista,
                'placa_1': placa_1,
                'placa_2': placa_2,
                'proprietario': proprietario,
                'total_frete': total_frete,
                'pedagio': pedagio,
                'valor_tarifa': valor_tarifa,
                'produto': prod_info['produto'],
                'peso': prod_info['peso'],
                'nf_ticket': prod_info['nf_ticket'],
                'data_nf': prod_info['data_nf'],
                'chave_nf': prod_info['chave_nf'],
            }
            registros.append(dados)
        return registros

    def processar_pdf(self) -> List[Dict]:
        """Processa todas as páginas do PDF. Retorna lista de dicionários."""
        with pdfplumber.open(self.arquivo_pdf) as pdf:
            for i, pagina in enumerate(pdf.pages, start=1):
                texto = pagina.extract_text()
                if not texto:
                    continue
                registros = self.processar_pagina(texto, i, pagina)
                self.dados_extraidos.extend(registros)
        return self.dados_extraidos

    def processar_pdf_por_pagina(self) -> Iterator[Tuple[int, List[Dict]]]:
        """
        Processa o PDF página a página. Gera (índice_página_0based, lista_de_registros).
        Útil para demembrar o PDF e enviar cada página ao MinIO.
        """
        with pdfplumber.open(self.arquivo_pdf) as pdf:
            for idx, pagina in enumerate(pdf.pages):
                texto = pagina.extract_text()
                if not texto:
                    yield idx, []
                    continue
                registros = self.processar_pagina(texto, idx + 1, pagina)
                yield idx, registros
