# processador_contracheque.py
import json
import re
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict
import fitz # PyMuPDF
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ProcessadorContracheque:
    def __init__(self, rubricas=None):
        """Inicializa o processador com as rubricas fornecidas ou carrega do arquivo padrão"""
        self.rubricas = rubricas if rubricas is not None else self._carregar_rubricas_default()
        
        # Dados auxiliares
        self.meses = {
            "Janeiro": "01", "Fevereiro": "02", "Março": "03", "Abril": "04",
            "Maio": "05", "Junho": "06", "Julho": "07", "Agosto": "08",
            "Setembro": "09", "Outubro": "10", "Novembro": "11", "Dezembro": "12"
        }
        
        self.meses_anos = self._gerar_meses_anos()
        self._processar_rubricas_internas()

    def _carregar_rubricas_default(self) -> Dict:
        """Carrega as rubricas do arquivo padrão se não forem fornecidas."""
        try:
            rubricas_path = Path(__file__).parent.parent / 'rubricas.json'
            with open(rubricas_path, 'r', encoding='utf-8') as f:
                return json.load(f).get('rubricas', {"proventos": {}, "descontos": {}})
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Erro ao carregar rubricas padrão: {str(e)}")
            return {"proventos": {}, "descontos": {}}

    def _gerar_meses_anos(self) -> List[str]:
        """Gera a lista de meses/anos (2019-2025)"""
        return [
            f"{mes}/{ano}" 
            for ano in range(2019, 2026) 
            for mes in self.meses.keys()
        ]

    def _processar_rubricas_internas(self):
        """Prepara as estruturas de dados das rubricas"""
        self.rubricas_completas = {
            **self.rubricas.get('proventos', {}), 
            **self.rubricas.get('descontos', {})
        }
        self.codigos_proventos = list(self.rubricas.get('proventos', {}).keys())
        self.codigos_descontos = list(self.rubricas.get('descontos', {}).keys())

    def converter_data_para_numerico(self, data_texto: str) -> str:
        """Converte data no formato 'Mês/Ano' para 'MM/AAAA'"""
        try:
            mes, ano = data_texto.split('/')
            return f"{self.meses.get(mes, '00')}/{ano}"
        except (ValueError, AttributeError):
            return "00/0000"

    def extrair_valor(self, valor_str: str) -> float:
        """Extrai valor monetário de uma string formatada"""
        try:
            # Limpa a string de qualquer caractere não numérico, exceto vírgula e ponto
            valor_limpo = re.sub(r'[^\d,\.]', '', valor_str)
            # Converte para o formato float padrão (ex: "1.185,54" -> 1185.54)
            valor = valor_limpo.replace('.', '').replace(',', '.')
            return float(valor)
        except (ValueError, AttributeError):
            return 0.0

    def _extrair_texto_pdf_interno(self, file_bytes):
        """Extrai texto do PDF usando PyMuPDF"""
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            texto = ""
            for page in doc:
                texto += page.get_text("text", flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE)
                texto += "\n--- PAGE BREAK ---\n"
            return texto
        except Exception as e:
            raise Exception(f"Erro ao extrair texto do PDF: {str(e)}")

    def _extrair_secoes_por_mes_ano(self, texto):
        """Divide o texto em seções, uma para cada mês/ano encontrado."""
        sections = defaultdict(str)
        current_section = None
        # Padrão para encontrar "Mês/Ano" (ex: "Janeiro/2021")
        month_year_pattern = re.compile(r'^(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\/\d{4}$')
        
        for linha in texto.split('\n'):
            linha_strip = linha.strip()
            if month_year_pattern.match(linha_strip):
                current_section = linha_strip
            elif current_section:
                sections[current_section] += linha + '\n'
        
        return sections

    def _identificar_meses_em_secoes(self, sections):
        """Identifica os meses válidos presentes nas seções extraídas"""
        return list(sections.keys())

    def processar_contracheque(self, filepath):
        """Método principal que orquestra o processamento de um arquivo PDF."""
        try:
            with open(filepath, 'rb') as f:
                file_bytes = f.read()
            
            texto = self._extrair_texto_pdf_interno(file_bytes)
            tabela_identificada = self._identificar_tabela(texto)
            sections = self._extrair_secoes_por_mes_ano(texto)
            meses_encontrados = self._identificar_meses_em_secoes(sections)
            
            if not meses_encontrados:
                raise ValueError("Nenhum mês/ano válido encontrado no documento")
            
            # Ordena os meses para garantir a sequência cronológica
            meses_encontrados.sort(key=lambda x: (int(x.split('/')[1]), int(self.meses[x.split('/')[0]])))
            
            primeiro_mes = meses_encontrados[0]
            ultimo_mes = meses_encontrados[-1]
            
            index_primeiro = self.meses_anos.index(primeiro_mes)
            index_ultimo = self.meses_anos.index(ultimo_mes)
            meses_para_processar = self.meses_anos[index_primeiro:index_ultimo + 1]
            
            results = {
                "primeiro_mes": primeiro_mes,
                "ultimo_mes": ultimo_mes,
                "meses_para_processar": meses_para_processar,
                "dados_mensais": {},
                "tabela": tabela_identificada
            }
            
            for mes_ano in meses_para_processar:
                data = sections.get(mes_ano)
                if data:
                    results["dados_mensais"][mes_ano] = self._processar_mes_conteudo(data, mes_ano)
            
            return results
            
        except Exception as e:
            logger.error(f"Erro ao processar contracheque: {str(e)}")
            raise

    def _identificar_tabela(self, texto):
        """Identifica a qual tabela (A, B, C ou 2015) pertence o contracheque."""
        if re.search(r'Lei n[ºo]\s*13\.450,\s*de\s*26\s*de\s*Outubro\s*de\s*2015', texto, re.IGNORECASE):
            return '2015'
        # Adicione outras lógicas de identificação de tabela se necessário
        return 'Desconhecida'

    def _processar_mes_conteudo(self, data_texto, mes_ano):
        """
        ### LÓGICA DE EXTRAÇÃO CORRIGIDA ###
        Processa o conteúdo de texto de um mês específico para extrair proventos e descontos.
        """
        resultados_mes = {
            "total_proventos": 0.0,
            "rubricas": defaultdict(float),
            "rubricas_detalhadas": defaultdict(float),
            "descricoes": {}
        }

        # Regex para encontrar qualquer valor monetário (ex: 1.234,56 ou 123,45)
        padrao_valor = re.compile(r'\d{1,3}(?:\.\d{3})*,\d{2}')
        
        # Concatena todos os códigos de proventos e descontos para busca
        todos_codigos = self.codigos_proventos + self.codigos_descontos

        # Itera por cada linha do texto do mês
        for line in data_texto.split('\n'):
            linha_limpa = line.strip()
            if not linha_limpa:
                continue

            # Verifica se a linha começa com algum dos códigos conhecidos
            for codigo in todos_codigos:
                if linha_limpa.startswith(codigo):
                    # Se encontrou um código, busca o último valor monetário na mesma linha
                    valores_encontrados = padrao_valor.findall(linha_limpa)
                    if valores_encontrados:
                        valor_str = valores_encontrados[-1] # Pega o último valor encontrado
                        valor = self.extrair_valor(valor_str)
                        
                        logger.debug(f"DEBUG: Mês/Ano: {mes_ano}, Código: '{codigo}', Valor: {valor}, Linha: '{linha_limpa}'")
                        
                        # Classifica como provento ou desconto
                        if codigo in self.codigos_proventos:
                            resultados_mes["rubricas"][codigo] += valor
                        elif codigo in self.codigos_descontos:
                             resultados_mes["rubricas_detalhadas"][codigo] += valor
                        
                        # Para de procurar outros códigos na mesma linha
                        break 
            
        # Calcula o total de proventos
        resultados_mes["total_proventos"] = sum(resultados_mes["rubricas"].values())
        
        # Log para os totais do mês para verificação
        total_descontos = sum(resultados_mes["rubricas_detalhadas"].values())
        logger.debug(f"TOTAIS PARA {mes_ano}: Proventos={resultados_mes['total_proventos']:.2f}, Descontos={total_descontos:.2f}")

        return resultados_mes

    # O método gerar_tabela_geral não precisa de alterações.
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
            descricao = self._gerar_descricoes_internas().get(cod, cod)
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

    def _gerar_descricoes_internas(self):
        """Gera dicionário com descrições de todas as rubricas"""
        return {
            **{cod: info.get('descricao', '') 
               for cod, info in self.rubricas.get('proventos', {}).items()},
            **{cod: info.get('descricao', '') 
               for cod, info in self.rubricas.get('descontos', {}).items()}
        }
