import json
import re
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict
import fitz  # PyMuPDF
import logging

logger = logging.getLogger(__name__)

class ProcessadorContracheque:
    def __init__(self, rubricas=None):
        self.rubricas = rubricas if rubricas is not None else self._carregar_rubricas_default()
        self.meses = {"Janeiro":"01", "Fevereiro":"02", "Março":"03", "Abril":"04", "Maio":"05", "Junho":"06", "Julho":"07", "Agosto":"08", "Setembro":"09", "Outubro":"10", "Novembro":"11", "Dezembro":"12"}
        self.meses_anos = self._gerar_meses_anos()
        self._processar_rubricas_internas()

    def _carregar_rubricas_default(self) -> Dict:
        try:
            rubricas_path = Path(__file__).parent.parent / 'rubricas.json'
            with open(rubricas_path, 'r', encoding='utf-8') as f:
                return json.load(f).get('rubricas', {"proventos": {}, "descontos": {}})
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Erro ao carregar rubricas padrão: {str(e)}")
            return {"proventos": {}, "descontos": {}}

    def _gerar_meses_anos(self) -> List[str]:
        return [f"{mes}/{ano}" for ano in range(2019, 2026) for mes in self.meses.keys()]

    def _processar_rubricas_internas(self):
        self.codigos_proventos = list(self.rubricas.get('proventos', {}).keys())
        self.codigos_descontos = list(self.rubricas.get('descontos', {}).keys())

    def converter_data_para_numerico(self, data_texto: str) -> str:
        try:
            mes, ano = data_texto.split('/')
            return f"{self.meses.get(mes, '00')}/{ano}"
        except (ValueError, AttributeError):
            return "00/0000"

    def extrair_valor(self, valor_str: str) -> float:
        try:
            valor_limpo = re.sub(r'[^\d,\.]', '', valor_str)
            valor = valor_limpo.replace('.', '').replace(',', '.')
            return float(valor)
        except (ValueError, AttributeError):
            return 0.0
    
    # Este método agora lê o texto completo, ideal para achar a data
    def _extrair_texto_completo_pdf(self, file_bytes):
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            texto_completo = ""
            for page in doc:
                texto_completo += page.get_text("text", sort=True) + "\n"
            return texto_completo
        except Exception as e:
            raise Exception(f"Erro ao extrair texto completo do PDF: {str(e)}")

    # Este método lê o PDF em colunas, ideal para achar os valores da tabela
    def _extrair_dados_pdf_por_colunas(self, file_bytes):
        texto_vantagens = ""
        texto_descontos = ""
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page in doc:
                rect_vantagens = fitz.Rect(0, 0, page.rect.width / 2, page.rect.height)
                rect_descontos = fitz.Rect(page.rect.width / 2, 0, page.rect.width, page.rect.height)
                texto_vantagens += page.get_text(clip=rect_vantagens, sort=True) + "\n"
                texto_descontos += page.get_text(clip=rect_descontos, sort=True) + "\n"
            return texto_vantagens, texto_descontos
        except Exception as e:
            raise Exception(f"Erro ao extrair texto das colunas do PDF: {str(e)}")

    def processar_contracheque(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                file_bytes = f.read()

            # --- LÓGICA HÍBRIDA ---
            # 1. Lê o texto completo SÓ para encontrar a data de forma confiável
            texto_completo = self._extrair_texto_completo_pdf(file_bytes)
            month_year_pattern = r'(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\s*/\s*\d{4}'
            month_year_match = re.search(month_year_pattern, texto_completo, re.IGNORECASE)

            if not month_year_match:
                raise ValueError("Não foi possível encontrar o Mês/Ano no documento.")
            
            # Extrai e formata o Mês/Ano encontrado
            mes_ano_str = month_year_match.group(0)
            partes = re.split(r'\s*/\s*', mes_ano_str)
            mes_ano = f"{partes[0].capitalize()}/{partes[1]}"

            # 2. Agora que temos a data, faz a leitura por colunas para extrair os valores sem erros
            texto_vantagens, texto_descontos = self._extrair_dados_pdf_por_colunas(file_bytes)
            dados_mes = self._processar_mes_conteudo(texto_vantagens, texto_descontos, mes_ano)

            return {
                "primeiro_mes": mes_ano, "ultimo_mes": mes_ano, "meses_para_processar": [mes_ano],
                "dados_mensais": {mes_ano: dados_mes}
            }
        except Exception as e:
            logger.error(f"Erro ao processar contracheque: {str(e)}")
            raise

    def _processar_mes_conteudo(self, texto_vantagens, texto_descontos, mes_ano):
        resultados_mes = {"rubricas": defaultdict(float), "rubricas_detalhadas": defaultdict(float)}

        padrao_rubrica = re.compile(r'^(?P<code>\d{4}|[A-Z0-9]{1,4}P|[A-Z]\d{3}|\d[A-Z]\d{2}|/\d{3})\s+.*?(?P<valor>\d{1,3}(?:[.,]\d{3})*,\d{2})\s*$', re.MULTILINE)

        for match in padrao_rubrica.finditer(texto_vantagens):
            codigo = match.group('code')
            valor = self.extrair_valor(match.group('valor'))
            if codigo in self.codigos_proventos:
                resultados_mes["rubricas"][codigo] = valor
                logger.debug(f"DEBUG: Provento Identificado - Mês/Ano: {mes_ano}, Código: '{codigo}', Valor: {valor}")

        for match in padrao_rubrica.finditer(texto_descontos):
            codigo = match.group('code')
            valor = self.extrair_valor(match.group('valor'))
            if codigo in self.codigos_descontos:
                resultados_mes["rubricas_detalhadas"][codigo] = valor
                logger.debug(f"DEBUG: Desconto Identificado - Mês/Ano: {mes_ano}, Código: '{codigo}', Valor: {valor}")

        total_proventos_calculado = 0
        for codigo, valor in resultados_mes["rubricas"].items():
            info_rubrica = self.rubricas.get('proventos', {}).get(codigo, {})
            if not info_rubrica.get('ignorar_na_soma', False):
                total_proventos_calculado += valor
        
        resultados_mes["total_proventos"] = total_proventos_calculado
        logger.debug(f"TOTAIS PARA {mes_ano}: Proventos (para soma)={total_proventos_calculado:.2f}, Descontos={sum(resultados_mes['rubricas_detalhadas'].values()):.2f}")
        
        return resultados_mes

    def gerar_tabela_proventos_resumida(self, resultados):
        tabela = {"colunas": ["Mês/Ano", "Total de Proventos"], "dados": []}
        for mes_ano in resultados.get("meses_para_processar", []):
            dados_mes = resultados.get("dados_mensais", {}).get(mes_ano, {})
            total_proventos = dados_mes.get("total_proventos", 0.0)
            tabela["dados"].append({"mes_ano": self.converter_data_para_numerico(mes_ano), "total": total_proventos})
        return tabela

    def gerar_tabela_descontos_detalhada(self, resultados):
        descontos_de_origem = self.rubricas.get('descontos', {})
        codigos_encontrados = set()
        for dados_mes in resultados.get("dados_mensais", {}).values():
            codigos_encontrados.update(dados_mes.get("rubricas_detalhadas", {}).keys())
        codigos_descontos_relevantes = sorted(list(codigos_encontrados))
        descricoes = {cod: descontos_de_origem.get(cod, {}).get('descricao', cod) for cod in codigos_descontos_relevantes}
        tabela = {"colunas": ["Mês/Ano"] + [descricoes[cod] for cod in codigos_descontos_relevantes], "dados": []}
        for mes_ano in resultados.get("meses_para_processar", []):
            linha = {"mes_ano": self.converter_data_para_numerico(mes_ano), "valores": []}
            rubricas_detalhadas_mes = resultados.get("dados_mensais", {}).get(mes_ano, {}).get("rubricas_detalhadas", {})
            for cod in codigos_descontos_relevantes:
                linha["valores"].append(rubricas_detalhadas_mes.get(cod, 0.0))
            tabela["dados"].append(linha)
        return tabela
