import json
import re
from pathlib import Path
from typing import Dict, Any
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

    def _gerar_meses_anos(self) -> list[str]:
        return [f"{mes}/{ano}" for ano in range(2019, 2026) for mes in self.meses.keys()]

    def _processar_rubricas_internas(self):
        self.codigos_proventos = list(self.rubricas.get('proventos', {}).keys())
        self.codigos_descontos = list(self.rubricas.get('descontos', {}).keys())

    def extrair_valor(self, valor_str: str) -> float:
        try:
            valor_limpo = re.sub(r'[^\d,\.]', '', valor_str)
            valor = valor_limpo.replace('.', '').replace(',', '.')
            return float(valor)
        except (ValueError, AttributeError):
            return 0.0

    def processar_contracheque(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                file_bytes = f.read()

            doc = fitz.open(stream=file_bytes, filetype="pdf")
            texto_completo = ""
            for page in doc:
                texto_completo += page.get_text("text", sort=True) + "\n"

            month_year_pattern = r'(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\s*/\s*\d{4}'
            month_year_match = re.search(month_year_pattern, texto_completo, re.IGNORECASE)
            if not month_year_match:
                raise ValueError("Não foi possível encontrar o Mês/Ano no documento.")

            mes_ano_str = month_year_match.group(0)
            partes = re.split(r'\s*/\s*', mes_ano_str)
            mes_ano = f"{partes[0].capitalize()}/{partes[1]}"

            dados_mes = self._processar_mes_conteudo(texto_completo, mes_ano)

            return {
                "primeiro_mes": mes_ano, "ultimo_mes": mes_ano, "meses_para_processar": [mes_ano],
                "dados_mensais": {mes_ano: dados_mes}
            }
        except Exception as e:
            logger.error(f"Erro ao processar contracheque: {str(e)}")
            raise

    def _processar_mes_conteudo(self, texto_completo, mes_ano):
        resultados_mes = {"rubricas": defaultdict(float), "rubricas_detalhadas": defaultdict(float)}

        bloco_vantagens_match = re.search(r'VANTAGENS(.*?)TOTAL DE VANTAGENS', texto_completo, re.DOTALL | re.IGNORECASE)
        texto_vantagens = bloco_vantagens_match.group(1) if bloco_vantagens_match else ""
        
        bloco_descontos_match = re.search(r'DESCONTOS(.*?)TOTAL DE DESCONTOS', texto_completo, re.DOTALL | re.IGNORECASE)
        texto_descontos = bloco_descontos_match.group(1) if bloco_descontos_match else ""

        padrao_valor = re.compile(r'\d{1,3}(?:[.,]\d{3})*,\d{2}')

        # --- LÓGICA FINAL E CONSISTENTE ---
        # Função auxiliar que será usada para AMBOS os blocos de texto
        def associar_codigos_e_valores(bloco_texto, lista_de_codigos):
            pares = {}
            texto_processado = bloco_texto
            for codigo in lista_de_codigos:
                # Procura pelo código no bloco
                match_codigo = re.search(re.escape(codigo), texto_processado)
                if match_codigo:
                    # A partir da posição do código, procura pelo primeiro valor
                    area_de_busca = texto_processado[match_codigo.start():]
                    match_valor = padrao_valor.search(area_de_busca)
                    if match_valor:
                        valor = self.extrair_valor(match_valor.group(0))
                        pares[codigo] = valor
                        # Remove o trecho processado para evitar releituras do mesmo valor
                        texto_processado = texto_processado[match_codigo.start() + len(match_valor.group(0)):]
            return pares

        # Executa a mesma lógica para proventos e descontos
        proventos_encontrados = associar_codigos_e_valores(texto_vantagens, self.codigos_proventos)
        descontos_encontrados = associar_codigos_e_valores(texto_descontos, self.codigos_descontos)

        for codigo, valor in proventos_encontrados.items():
            resultados_mes["rubricas"][codigo] = valor
            logger.debug(f"DEBUG: Provento Identificado - Mês/Ano: {mes_ano}, Código: '{codigo}', Valor: {valor}")

        for codigo, valor in descontos_encontrados.items():
            resultados_mes["rubricas_detalhadas"][codigo] = valor
            logger.debug(f"DEBUG: Desconto Identificado - Mês/Ano: {mes_ano}, Código: '{codigo}', Valor: {valor}")
        
        # Lógica de soma continua a mesma
        total_proventos_calculado = sum(
            valor for codigo, valor in resultados_mes["rubricas"].items()
            if not self.rubricas.get('proventos', {}).get(codigo, {}).get('ignorar_na_soma', False)
        )
        
        resultados_mes["total_proventos"] = total_proventos_calculado
        logger.debug(f"TOTAIS FINAIS PARA {mes_ano}: Proventos (para soma)={total_proventos_calculado:.2f}, Descontos={sum(resultados_mes['rubricas_detalhadas'].values()):.2f}")
        
        return resultados_mes
    
    # O restante dos métodos para gerar as tabelas não precisa de alteração
    def converter_data_para_numerico(self, data_texto: str) -> str:
        try: mes, ano = data_texto.split('/'); return f"{self.meses.get(mes, '00')}/{ano}"
        except (ValueError, AttributeError): return "00/0000"
        
    def gerar_tabela_proventos_resumida(self, resultados):
        tabela = {"colunas": ["Mês/Ano", "Total de Proventos"], "dados": []}
        for mes_ano in resultados.get("meses_para_processar", []):
            dados_mes = resultados.get("dados_mensais", {}).get(mes_ano, {})
            total_proventos = dados_mes.get("total_proventos", 0.0)
            tabela["dados"].append({"mes_ano": self.converter_data_para_numerico(mes_ano), "total": total_proventos})
        return tabela

    def gerar_tabela_descontos_detalhada(self, resultados):
        descontos_de_origem = self.rubricas.get('descontos', {})
        codigos_encontrados = set(
            cod for dados_mes in resultados.get("dados_mensais", {}).values()
            for cod in dados_mes.get("rubricas_detalhadas", {}).keys()
        )
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
