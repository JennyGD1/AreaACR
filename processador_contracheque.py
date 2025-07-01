import json
import re
from pathlib import Path
from typing import Dict, List
from collections import defaultdict
import fitz  # PyMuPDF
import logging

logger = logging.getLogger(__name__)

class ProcessadorContracheque:
    def __init__(self, rubricas=None):
        """Inicializa o processador com as rubricas fornecidas ou carrega do arquivo padrão"""
        # Carrega rubricas
        self.rubricas = self._carregar_rubricas(rubricas)
        
        # Dados auxiliares
        self.meses = {
            "Janeiro": "01", "Fevereiro": "02", "Março": "03", "Abril": "04",
            "Maio": "05", "Junho": "06", "Julho": "07", "Agosto": "08",
            "Setembro": "09", "Outubro": "10", "Novembro": "11", "Dezembro": "12"
        }
        
        self.meses_anos = self._gerar_meses_anos()
        self._processar_rubricas()

    def _carregar_rubricas(self, rubricas) -> Dict:
        """Carrega as rubricas do parâmetro ou do arquivo padrão"""
        if rubricas is not None:
            return rubricas
        
        try:
            # Caminho corrigido para rubricas.json
            rubricas_path = Path(__file__).parent.parent / 'rubricas.json'
            with open(rubricas_path, 'r', encoding='utf-8') as f:
                return json.load(f).get('rubricas', {"proventos": {}, "descontos": {}})
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Erro ao carregar rubricas: {str(e)}")
            return {"proventos": {}, "descontos": {}}

    def _gerar_meses_anos(self) -> List[str]:
        """Gera a lista de meses/anos (2019-2025)"""
        return [
            f"{mes}/{ano}" 
            for ano in range(2019, 2026) 
            for mes in self.meses.keys()
        ]

    def _processar_rubricas(self):
        """Prepara as estruturas de dados das rubricas"""
        self.rubricas_completas = {
            **self.rubricas.get('proventos', {}), 
            **self.rubricas.get('descontos', {})
        }
        self.codigos_proventos = list(self.rubricas.get('proventos', {}).keys())
        self.rubricas_detalhadas = self.rubricas.get('descontos', {})

    def converter_data_para_numerico(self, data_texto: str) -> str:
        """Converte data no formato 'Mês/Ano' para 'MM/AAAA'"""
        try:
            mes, ano = data_texto.split('/')
            return f"{self.meses.get(mes, '00')}/{ano}"
        except (ValueError, AttributeError):
            return "00/0000"

    def extrair_valor(self, linha: str) -> float:
        """Extrai valor monetário de uma string"""
        padrao = r'(\d{1,3}(?:\.\d{3})*,\d{2})'
        match = re.search(padrao, linha)
        if match:
            try:
                valor = match.group(1).replace('.', '').replace(',', '.')
                return float(valor)
            except (ValueError, AttributeError):
                return 0.0
        return 0.0

    def processar_pdf(self, file_bytes):
        """Processa o conteúdo PDF e retorna os resultados formatados"""
        try:
            if not hasattr(self, 'rubricas_completas'):
                raise ValueError("Rubricas não foram carregadas corretamente")
            
            texto = self._extrair_texto_pdf(file_bytes)
            sections = self._extrair_secoes(texto)
            meses_encontrados = self._identificar_meses(sections)
            
            if not meses_encontrados:
                raise ValueError("Nenhum mês/ano válido encontrado no documento")
            
            # Ordena os meses encontrados
            meses_encontrados.sort(key=lambda x: (
                int(x.split('/')[1]) * 100 + int(self.meses[x.split('/')[0]])
            ))
            
            primeiro_mes = meses_encontrados[0]
            ultimo_mes = meses_encontrados[-1]
            
            index_primeiro = self.meses_anos.index(primeiro_mes)
            index_ultimo = self.meses_anos.index(ultimo_mes)
            meses_para_processar = self.meses_anos[index_primeiro:index_ultimo + 1]
            
            results = {
                "primeiro_mes": primeiro_mes,
                "ultimo_mes": ultimo_mes,
                "meses_para_processar": meses_para_processar,
                "dados_mensais": {}
            }
            
            for mes_ano in meses_para_processar:
                data = sections.get(mes_ano, "")
                if data:
                    results["dados_mensais"][mes_ano] = self.processar_mes(data, mes_ano)
            
            return results
            
        except Exception as e:
            raise Exception(f"Erro ao processar PDF: {str(e)}")

    def processar_contracheque(self, filepath):
        """Processa um arquivo PDF de contracheque e retorna dados estruturados"""
        try:
            with open(filepath, 'rb') as f:
                file_bytes = f.read()
            
            # Extrai texto do PDF
            texto = self._extrair_texto_pdf(file_bytes)
            
            # Identifica a tabela (A, B ou C) - nova funcionalidade
            tabela = self._identificar_tabela(texto)
            
            # Processa os dados normalmente
            results = self.processar_pdf(file_bytes)
            results['tabela'] = tabela
            
            return results
            
        except Exception as e:
            raise Exception(f"Erro ao processar contracheque: {str(e)}")

    def _identificar_tabela(self, texto):
        """Identifica a qual tabela pertence o contracheque com base no conteúdo"""
        # Verifica se é da Bahia
        if "GOVERNO DO ESTADO DA BAHIA" in texto:
            if "Lei nº 13.450" in texto:
                return "BAHIA_2015"
            else:
                return "BAHIA"
        
        # Padrões originais para outras tabelas
        padrao_tabela_a = re.compile(r'Tabela\s*A', re.IGNORECASE)
        padrao_tabela_b = re.compile(r'Tabela\s*B', re.IGNORECASE)
        padrao_tabela_c = re.compile(r'Tabela\s*C', re.IGNORECASE)
        
        if padrao_tabela_a.search(texto):
            return 'A'
        elif padrao_tabela_b.search(texto):
            return 'B'
        elif padrao_tabela_c.search(texto):
            return 'C'
        
        return 'Desconhecida'

    def gerar_totais(self, resultados):
        """Gera totais mensais e anuais organizados por tabela"""
        totais = {
            'mensais': defaultdict(lambda: defaultdict(float)),
            'anuais': defaultdict(lambda: defaultdict(float)),
            'geral': defaultdict(float)
        }
        
        if not resultados or 'dados_mensais' not in resultados:
            return totais
        
        tabela = resultados.get('tabela', 'Desconhecida')
        
        for mes_ano, dados in resultados['dados_mensais'].items():
            ano = mes_ano.split('/')[1]
            
            # Processa proventos
            for rubrica, valor in dados.get('rubricas', {}).items():
                totais['mensais'][mes_ano][rubrica] += valor
                totais['anuais'][ano][rubrica] += valor
                totais['geral'][rubrica] += valor
            
            # Processa descontos
            for rubrica, valor in dados.get('rubricas_detalhadas', {}).items():
                totais['mensais'][mes_ano][rubrica] += valor
                totais['anuais'][ano][rubrica] += valor
                totais['geral'][rubrica] += valor
        
        return {
            'tabela': tabela,
            'totais': totais,
            'descricoes': self._gerar_descricoes()
        }

    def _gerar_descricoes(self):
        """Gera dicionário com descrições de todas as rubricas"""
        return {
            **{cod: info.get('descricao', '') 
               for cod, info in self.rubricas.get('proventos', {}).items()},
            **{cod: info.get('descricao', '') 
               for cod, info in self.rubricas.get('descontos', {}).items()}
        }

    def _extrair_secoes(self, texto):
        """Extrai seções do texto por mês/ano"""
        sections = defaultdict(str)
        current_section = None
        
        # Padrão para identificar "Mês/Ano" (ex: Janeiro/2023)
        month_year_pattern = re.compile(
            r'^(?:AVISO DE CRÉDITO\s+)?'
            r'(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)'
            r'\s*/\s*(\d{4})$'
        )
        
        lines = texto.split('\n')
        
        for linha in lines:
            linha = linha.strip()
            if not linha:
                continue
                
            # Verifica se é um cabeçalho de mês/ano
            match = month_year_pattern.match(linha)
            if match:
                mes = match.group(1)
                ano = match.group(2)
                current_section = f"{mes}/{ano}"
            elif current_section:
                sections[current_section] += linha + '\n'
        
        return sections

    def _identificar_meses(self, sections):
        """Identifica os meses presentes no texto"""
        meses_validos = []
        for cabecalho in sections.keys():
            partes = cabecalho.split('/')
            if len(partes) == 2 and partes[0] in self.meses and partes[1].isdigit():
                meses_validos.append(cabecalho)
        return list(set(meses_validos))

    def _extrair_texto_pdf(self, file_bytes):
        """Extrai texto do PDF usando PyMuPDF, garantindo processamento de múltiplas páginas"""
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            texto = ""
            for page in doc:
                # Extrai texto com layout preservado e flags adicionais
                texto += page.get_text("text", flags=
                    fitz.TEXT_PRESERVE_LIGATURES | 
                    fitz.TEXT_PRESERVE_WHITESPACE |
                    fitz.TEXT_MEDIABOX_CLIP |
                    fitz.TEXT_DEHYPHENATE)
                texto += "\n--- PAGE BREAK ---\n"
            return texto
        except Exception as e:
            raise Exception(f"Erro ao extrair texto do PDF: {str(e)}")

    def processar_mes(self, data_texto, mes_ano):
        """Processa os dados de um mês específico para contracheques da Bahia"""
        lines = [line.strip() for line in data_texto.split('\n') if line.strip()]
        
        resultados_mes = {
            "total_proventos": 0.0,
            "rubricas": defaultdict(float),
            "rubricas_detalhadas": defaultdict(float),
            "descricoes": {}
        }
    
        # Padrão para rubricas de proventos e descontos
        padrao_rubrica = re.compile(
            r'^(?P<codigo>\d{1,4}[A-Za-z]?)\s+'  # Código (ex: 003P, 0J40)
            r'(?P<descricao>.+?)\s+'  # Descrição
            r'(?:[A-Z]{2}\s+)?'  # Opcional: sigla de estado (ex: BA)
            r'(?P<valor>\d{1,3}(?:\.\d{3})*,\d{2})'  # Valor (1.185,54)
        )
    
        # Padrão para totais
        padrao_total = re.compile(
            r'TOTAL\s+DE\s+(?P<tipo>PROVENTOS|DESCONTOS)\s+(?P<valor>\d{1,3}(?:\.\d{3})*,\d{2})'
        )
    
        for line in lines:
            # Processa rubricas
            match_rubrica = padrao_rubrica.search(line)
            if match_rubrica:
                codigo = match_rubrica.group('codigo')
                descricao = match_rubrica.group('descricao')
                valor = float(match_rubrica.group('valor').replace('.', '').replace(',', '.'))
                
                # Classifica como provento ou desconto
                if 'VANTAGENS' in line or 'PROVENTOS' in line:
                    resultados_mes["rubricas"][codigo] = valor
                    resultados_mes["descricoes"][codigo] = descricao
                    resultados_mes["total_proventos"] += valor
                elif 'DESCONTOS' in line:
                    resultados_mes["rubricas_detalhadas"][codigo] = valor
                    resultados_mes["descricoes"][codigo] = descricao
    
            # Processa totais
            match_total = padrao_total.search(line)
            if match_total:
                tipo = match_total.group('tipo').lower()
                valor = float(match_total.group('valor').replace('.', '').replace(',', '.'))
                if tipo == 'proventos':
                    resultados_mes["total_proventos"] = valor
    
        return resultados_mes
        
    def gerar_tabela_geral(self, resultados):
        """Gera tabela consolidada mantendo todas as rubricas que apareceram em algum mês"""
        tabela = {
            "colunas": ["MÊS/ANO"],
            "dados": []
        }
    
        if not resultados or "meses_para_processar" not in resultados:
            return tabela
    
        # Identifica TODAS as rubricas que aparecem em pelo menos um mês
        todas_rubricas = set()
        for dados_mes in resultados["dados_mensais"].values():
            todas_rubricas.update(dados_mes.get("rubricas", {}).keys())
            todas_rubricas.update(dados_mes.get("rubricas_detalhadas", {}).keys())
    
        # Ordena as rubricas
        rubricas_ordenadas = sorted(list(todas_rubricas))
    
        # Adiciona colunas para cada rubrica
        for cod in rubricas_ordenadas:
            descricao = ""
            # Tenta encontrar a descrição em algum mês
            for dados_mes in resultados["dados_mensais"].values():
                if cod in dados_mes.get("descricoes", {}):
                    descricao = dados_mes["descricoes"][cod]
                    break
            tabela["colunas"].append(f"{descricao} ({cod})")
    
        # Adiciona colunas de totais
        tabela["colunas"].append("TOTAL PROVENTOS")
        tabela["colunas"].append("TOTAL DESCONTOS")
        tabela["colunas"].append("TOTAL LÍQUIDO")
    
        # Preenche os dados para cada mês
        for mes_ano in resultados["meses_para_processar"]:
            dados_mes = resultados["dados_mensais"].get(mes_ano, {})
            linha_dados = {
                "mes_ano": self.converter_data_para_numerico(mes_ano),
                "valores": []
            }
    
            total_proventos = dados_mes.get("total_proventos", 0.0)
            total_descontos = 0.0
    
            # Preenche valores para cada rubrica (mesmo que zero)
            for cod in rubricas_ordenadas:
                # Verifica se é provento ou desconto
                if cod in self.rubricas.get('proventos', {}):
                    valor = dados_mes.get("rubricas", {}).get(cod, 0.0)
                    linha_dados["valores"].append(valor)
                else:
                    valor = dados_mes.get("rubricas_detalhadas", {}).get(cod, 0.0)
                    linha_dados["valores"].append(valor)
                    total_descontos += valor
    
            linha_dados["valores"].append(total_proventos)
            linha_dados["valores"].append(total_descontos)
            linha_dados["valores"].append(total_proventos - total_descontos)
            
            tabela["dados"].append(linha_dados)
            
        return tabela
