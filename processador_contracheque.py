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
            # Carrega o arquivo JSON completo
            rubricas_path = Path(__file__).parent.parent / 'rubricas.json'
            with open(rubricas_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Erro ao carregar rubricas padrão: {str(e)}")
            return {"rubricas": {"proventos": {}, "descontos": {}}}

    def _gerar_meses_anos(self) -> list[str]:
        return [f"{mes}/{ano}" for ano in range(2019, 2026) for mes in self.meses.keys()]

    def _processar_rubricas_internas(self):
        # Acessa a chave 'rubricas' para obter os proventos e descontos
        config_rubricas = self.rubricas.get('rubricas', {})
        self.codigos_proventos = list(config_rubricas.get('proventos', {}).keys())
        self.codigos_descontos = list(config_rubricas.get('descontos', {}).keys())

    def extrair_valor(self, valor_str: str) -> float:
        try:
            valor_limpo = re.sub(r'[^\d,]', '', valor_str)
            valor = valor_limpo.replace('.', '').replace(',', '.')
            return float(valor)
        except (ValueError, AttributeError):
            return 0.0

    def _extrair_secoes_por_mes_ano(self, doc):
        sections = defaultdict(str)
        month_year_pattern = re.compile(r'(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\s*/\s*(\d{4})', re.IGNORECASE)
        
        texto_completo = ""
        for page in doc:
            texto_completo += page.get_text("text", sort=True) + "\n---PAGE_BREAK---\n"

        # Divide o texto em seções baseadas no padrão de Mês/Ano
        secoes_encontradas = month_year_pattern.finditer(texto_completo)
        pontos_de_corte = [m.start() for m in secoes_encontradas]
        
        if not pontos_de_corte:
            raise ValueError("Não foi possível encontrar nenhuma seção de Mês/Ano no documento.")

        for i, start_pos in enumerate(pontos_de_corte):
            end_pos = pontos_de_corte[i+1] if i+1 < len(pontos_de_corte) else len(texto_completo)
            texto_secao = texto_completo[start_pos:end_pos]
            match = month_year_pattern.search(texto_secao)
            if match:
                mes = match.group(1).capitalize()
                ano = match.group(2)
                sections[f"{mes}/{ano}"] += texto_secao
        
        return sections

    def processar_contracheque(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                file_bytes = f.read()

            doc = fitz.open(stream=file_bytes, filetype="pdf")
            secoes = self._extrair_secoes_por_mes_ano(doc)
            
            resultados_finais = { "dados_mensais": {} }

            for mes_ano, texto_secao in secoes.items():
                resultados_finais["dados_mensais"][mes_ano] = self._processar_mes_conteudo(texto_secao, mes_ano)

            meses_processados = sorted(
                resultados_finais['dados_mensais'].keys(),
                key=lambda m: (int(m.split('/')[1]), int(self.meses.get(m.split('/')[0], 0)))
            )
            
            if not meses_processados:
                raise ValueError("Nenhum dado mensal foi processado.")

            resultados_finais['primeiro_mes'] = meses_processados[0]
            resultados_finais['ultimo_mes'] = meses_processados[-1]
            
            try:
                idx_primeiro = self.meses_anos.index(meses_processados[0])
                idx_ultimo = self.meses_anos.index(meses_processados[-1])
                resultados_finais['meses_para_processar'] = self.meses_anos[idx_primeiro:idx_ultimo + 1]
            except ValueError:
                resultados_finais['meses_para_processar'] = meses_processados

            return resultados_finais
        except Exception as e:
            logger.error(f"Erro ao processar contracheque: {str(e)}")
            raise

    def _processar_mes_conteudo(self, texto_secao, mes_ano):
        resultados_mes = {"rubricas": defaultdict(float), "rubricas_detalhadas": defaultdict(float)}

        bloco_vantagens_match = re.search(r'VANTAGENS(.*?)TOTAL DE VANTAGENS', texto_secao, re.DOTALL | re.IGNORECASE)
        texto_vantagens = bloco_vantagens_match.group(1) if bloco_vantagens_match else ""
        
        bloco_descontos_match = re.search(r'DESCONTOS(.*?)TOTAL DE DESCONTOS', texto_secao, re.DOTALL | re.IGNORECASE)
        texto_descontos = bloco_descontos_match.group(1) if bloco_descontos_match else ""

        padrao_geral = re.compile(r"^\s*([A-Z0-9/]+)\s+.*?\s+([\d.,]+)\s*$", re.MULTILINE)

        for match in padrao_geral.finditer(texto_vantagens):
            codigo, valor_str = match.groups()
            if codigo in self.codigos_proventos:
                resultados_mes["rubricas"][codigo] += self.extrair_valor(valor_str)

        for match in padrao_geral.finditer(texto_descontos):
            codigo, valor_str = match.groups()
            if codigo in self.codigos_descontos:
                resultados_mes["rubricas_detalhadas"][codigo] += self.extrair_valor(valor_str)
        
        total_proventos_calculado = sum(
            valor for codigo, valor in resultados_mes["rubricas"].items()
            if not self.rubricas.get('proventos', {}).get(codigo, {}).get('ignorar_na_soma', False)
        )
        resultados_mes["total_proventos"] = total_proventos_calculado
        logger.debug(f"TOTAIS FINAIS PARA {mes_ano}: Proventos (soma)={total_proventos_calculado:.2f}, Descontos={sum(resultados_mes['rubricas_detalhadas'].values()):.2f}")

        return resultados_mes
    
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
        codigos_para_exibir = sorted([
            cod for cod in codigos_encontrados
            if descontos_de_origem.get(cod, {}).get("tipo") == "planserv"
        ])
        
        descricoes = {cod: descontos_de_origem.get(cod, {}).get('descricao', cod) for cod in codigos_para_exibir}
        tabela = {"colunas": ["Mês/Ano"] + [descricoes.get(cod, cod) for cod in codigos_para_exibir], "dados": []}
        
        for mes_ano in resultados.get("meses_para_processar", []):
            linha = {"mes_ano": self.converter_data_para_numerico(mes_ano), "valores": []}
            rubricas_detalhadas_mes = resultados.get("dados_mensais", {}).get(mes_ano, {}).get("rubricas_detalhadas", {})
            for cod in codigos_para_exibir:
                linha["valores"].append(rubricas_detalhadas_mes.get(cod, 0.0))
            tabela["dados"].append(linha)
        return tabela
