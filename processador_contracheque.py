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
    """Processa os dados de um mês específico"""
    lines = [line.strip() for line in data_texto.split('\n') if line.strip()]
    
    resultados_mes = {
        "total_proventos": 0.0,
        "rubricas": defaultdict(float),
        "rubricas_detalhadas": defaultdict(float),
        "descricoes": {}
    }

    # Padrão para o formato da Bahia
    padrao_rubrica = re.compile(
        r'^(?P<codigo>\d{1,4}[A-Za-z]?)\s+'  # Código
        r'.*?'  # Descrição
        r'(?P<valor>\d{1,3}(?:\.\d{3})*,\d{2})'  # Valor
    )

    for line in lines:
        match = padrao_rubrica.search(line)
        if match:
            codigo = match.group('codigo')
            valor = self.extrair_valor(match.group('valor'))
            
            # Classifica como provento ou desconto
            if codigo in self.codigos_proventos:
                resultados_mes["rubricas"][codigo] += valor
                resultados_mes["total_proventos"] += valor
            elif codigo in self.rubricas_detalhadas:
                resultados_mes["rubricas_detalhadas"][codigo] += valor
    
    return resultados_mes
        
    def gerar_tabela_geral(self, resultados):
        """Gera uma tabela consolidada com os resultados"""
        tabela = {
            "colunas": ["MÊS/ANO"],
            "dados": []
        }
        
        if not resultados or "meses_para_processar" not in resultados:
            return tabela
        
        all_rubricas_found = set()
        for mes_ano, dados_mes in resultados["dados_mensais"].items():
            all_rubricas_found.update(dados_mes.get("rubricas", {}).keys())
            all_rubricas_found.update(dados_mes.get("rubricas_detalhadas", {}).keys())
        
        sorted_rubricas = sorted(list(all_rubricas_found))

        for cod in sorted_rubricas:
            descricao = self._gerar_descricoes().get(cod, cod)
            tabela["colunas"].append(f"{descricao} ({cod})")
        
        tabela["colunas"].append("TOTAL PROVENTOS")
        tabela["colunas"].append("TOTAL DESCONTOS")
        tabela["colunas"].append("TOTAL LÍQUIDO")

        for mes_ano in resultados["meses_para_processar"]:
            dados_mes = resultados["dados_mensais"].get(mes_ano, {})
            linha_dados = {
                "mes_ano": self.converter_data_para_numerico(mes_ano),
                "valores": []
            }
            
            total_proventos_mes = 0.0
            total_descontos_mes = 0.0

            for cod in sorted_rubricas:
                valor_provento = dados_mes.get("rubricas", {}).get(cod, 0.0)
                valor_desconto = dados_mes.get("rubricas_detalhadas", {}).get(cod, 0.0)
                
                if cod in self.rubricas.get('proventos', {}):
                    linha_dados["valores"].append(valor_provento)
                    total_proventos_mes += valor_provento
                elif cod in self.rubricas.get('descontos', {}):
                    linha_dados["valores"].append(valor_desconto)
                    total_descontos_mes += valor_desconto
                else:
                    linha_dados["valores"].append(0.0)

            linha_dados["valores"].append(total_proventos_mes)
            linha_dados["valores"].append(total_descontos_mes)
            linha_dados["valores"].append(total_proventos_mes - total_descontos_mes)
            
            tabela["dados"].append(linha_dados)
            
        return tabela
