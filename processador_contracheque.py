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
        # Carrega rubricas
        # rubricas_path = Path(__file__).parent.parent / 'rubricas.json' # Comentado, pois 'rubricas' já vem de load_rubricas no app.py
        self.rubricas = rubricas if rubricas is not None else self._carregar_rubricas_default()
        
        # Dados auxiliares
        self.meses = {
            "Janeiro": "01", "Fevereiro": "02", "Março": "03", "Abril": "04",
            "Maio": "05", "Junho": "06", "Julho": "07", "Agosto": "08",
            "Setembro": "09", "Outubro": "10", "Novembro": "11", "Dezembro": "12"
        }
        
        self.meses_anos = self._gerar_meses_anos()
        self._processar_rubricas_internas() # Renomeado para evitar conflito com 'processar' de fora

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

    def _processar_rubricas_internas(self): # Renomeado
        """Prepara as estruturas de dados das rubricas"""
        self.rubricas_completas = {
            **self.rubricas.get('proventos', {}), 
            **self.rubricas.get('descontos', {})
        }
        self.codigos_proventos = list(self.rubricas.get('proventos', {}).keys())
        self.rubricas_detalhadas_map = self.rubricas.get('descontos', {}) # Renomeado para evitar confusão

    def converter_data_para_numerico(self, data_texto: str) -> str:
        """Converte data no formato 'Mês/Ano' para 'MM/AAAA'"""
        try:
            mes, ano = data_texto.split('/')
            return f"{self.meses.get(mes, '00')}/{ano}"
        except (ValueError, AttributeError):
            return "00/0000"

    def extrair_valor(self, valor_str: str) -> float: # Recebe string, não linha
        """Extrai valor monetário de uma string formatada (já limpa)"""
        try:
            valor = valor_str.replace('.', '').replace(',', '.')
            return float(valor)
        except (ValueError, AttributeError):
            return 0.0

    def _extrair_texto_pdf_interno(self, file_bytes): # Renomeado
        """Extrai texto do PDF usando PyMuPDF, garantindo processamento de múltiplas páginas"""
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            texto = ""
            for page in doc:
                texto += page.get_text("text", flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE)
                texto += "\n--- PAGE BREAK ---\n"
            return texto
        except Exception as e:
            raise Exception(f"Erro ao extrair texto do PDF: {str(e)}")

    def _extrair_secoes_por_mes_ano(self, texto): # Renomeado
        """Extrai seções do texto por mês/ano"""
        sections = defaultdict(str)
        current_section = None
        
        month_year_pattern = re.compile(r'^(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\/\d{4}$')
        
        lines = texto.split('\n')
        
        for i, linha in enumerate(lines):
            linha = linha.strip()
            if not linha:
                continue
                
            if month_year_pattern.match(linha):
                current_section = linha
            elif current_section:
                sections[current_section] += linha + '\n'
        
        return sections

    def _identificar_meses_em_secoes(self, sections): # Renomeado
        """Identifica os meses presentes no texto"""
        meses_validos = []
        for cabecalho in sections.keys():
            partes = cabecalho.split('/')
            if len(partes) == 2 and partes[0] in self.meses and partes[1].isdigit():
                meses_validos.append(cabecalho)
        return list(set(meses_validos))

    # Método central para processar um único contracheque (agora integrado e corrigido)
    def processar_contracheque(self, filepath):
        """Processa um arquivo PDF de contracheque e retorna dados estruturados"""
        try:
            with open(filepath, 'rb') as f:
                file_bytes = f.read()
            
            texto = self._extrair_texto_pdf_interno(file_bytes)
            tabela_identificada = self._identificar_tabela(texto)
            sections = self._extrair_secoes_por_mes_ano(texto)
            meses_encontrados = self._identificar_meses_em_secoes(sections)
            
            if not meses_encontrados:
                raise ValueError("Nenhum mês/ano válido encontrado no documento")
            
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
                "dados_mensais": {},
                "tabela": tabela_identificada # Adiciona informação da tabela aqui
            }
            
            for mes_ano in meses_para_processar:
                data = sections.get(mes_ano, "")
                if data:
                    results["dados_mensais"][mes_ano] = self._processar_mes_conteudo(data, mes_ano)
            
            return results
            
        except Exception as e:
            logger.error(f"Erro ao processar contracheque: {str(e)}")
            raise Exception(f"Erro ao processar contracheque: {str(e)}")

    def _identificar_tabela(self, texto):
        """Identifica a qual tabela (A, B ou C) pertence o contracheque"""
        padrao_tabela_a = re.compile(r'Tabela\s*A', re.IGNORECASE)
        padrao_tabela_b = re.compile(r'Tabela\s*B', re.IGNORECASE)
        padrao_tabela_c = re.compile(r'Tabela\s*C', re.IGNORECASE)
        
        if padrao_tabela_a.search(texto):
            return 'A'
        elif padrao_tabela_b.search(texto):
            return 'B'
        elif padrao_tabela_c.search(texto):
            return 'C'
        else:
            if re.search(r'Lei n[ºo]\s*13\.450,\s*de\s*26\s*de\s*Outubro\s*de\s*2015', texto, re.IGNORECASE):
                return '2015'
            return 'Desconhecida'

    def _processar_mes_conteudo(self, data_texto, mes_ano): # Método original 'processar_mes' renomeado
        """Processa os dados de um mês específico"""
        lines = [line.strip() for line in data_texto.split('\n') if line.strip()]
        
        resultados_mes = {
            "total_proventos": 0.0,
            "rubricas": defaultdict(float), # Armazena proventos
            "rubricas_detalhadas": defaultdict(float), # Armazena descontos
            "descricoes": {} # Descrições serão preenchidas na camada de análise/apresentação
        }

        # NOVA REGEX FINALISTA (Tentativa 3) - Mantida
        padrao_rubrica = re.compile(
            r'^(?P<codigo>[A-Za-z0-9\/]+)\s+.*' +  # Captura o código (flexível), seguido de espaço e QUALQUER COISA (guloso)
            r'(?P<valor>\d{1,3}(?:\.\d{3})*,\d{2})$' # Captura o ÚLTIMO valor monetário antes do final da linha
        )

        for line in lines:
            match = padrao_rubrica.match(line)
            if match:
                rubrica_codigo = match.group('codigo').strip()
                valor_str = match.group('valor')
                valor = self.extrair_valor(valor_str) # Usa o método extrair_valor da classe

                logger.debug(f"DEBUG: Mês/Ano: {mes_ano}, Linha: '{line}'")
                logger.debug(f"DEBUG: Rubrica encontrada: '{rubrica_codigo}', Valor: {valor}")

                if rubrica_codigo in self.codigos_proventos:
                    resultados_mes["total_proventos"] += valor
                    resultados_mes["rubricas"][rubrica_codigo] += valor
                elif rubrica_codigo in self.rubricas_detalhadas_map: # Usa o nome renomeado
                    resultados_mes["rubricas_detalhadas"][rubrica_codigo] += valor
                else:
                    logger.debug(f"DEBUG: Mês/Ano: {mes_ano}, Rubrica '{rubrica_codigo}' encontrada mas NÃO CLASSIFICADA: '{line}'")
            else:
                logger.debug(f"DEBUG: Mês/Ano: {mes_ano}, Linha NÃO CORRESPONDE ao padrão: '{line}'")
        
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
            descricao = self._gerar_descricoes_internas().get(cod, cod) # Usa método interno
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

    def _gerar_descricoes_internas(self): # Renomeado para evitar conflito com Analisador
        """Gera dicionário com descrições de todas as rubricas"""
        return {
            **{cod: info.get('descricao', '') 
               for cod, info in self.rubricas.get('proventos', {}).items()},
            **{cod: info.get('descricao', '') 
               for cod, info in self.rubricas.get('descontos', {}).items()}
        }
