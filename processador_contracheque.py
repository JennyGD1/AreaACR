import json
import re
from pathlib import Path
from typing import Dict, Any, List
from collections import defaultdict
import fitz  # PyMuPDF
import logging

logger = logging.getLogger(__name__)

class ProcessadorContracheque:
    def __init__(self, rubricas=None):
        self.rubricas = rubricas if rubricas is not None else self._carregar_rubricas_default()
        self.meses = {
            "Janeiro": "01", "Fevereiro": "02", "Março": "03", 
            "Abril": "04", "Maio": "05", "Junho": "06", 
            "Julho": "07", "Agosto": "08", "Setembro": "09", 
            "Outubro": "10", "Novembro": "11", "Dezembro": "12"
        }
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

    def extrair_valor(self, valor_str: str) -> float:
        try:
            valor_limpo = valor_str.replace('.', '').replace(',', '.')
            return float(valor_limpo)
        except (ValueError, AttributeError):
            return 0.0

    def _extrair_secoes_por_mes_ano(self, doc) -> Dict[str, List[str]]:
        sections = defaultdict(list)
        month_year_pattern = re.compile(
            r'(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\s*[/\s]*(\d{4})',
            re.IGNORECASE
        )
        for page in doc:
            texto_pagina = page.get_text("text", sort=True)
            match = month_year_pattern.search(texto_pagina)
            if match:
                mes = match.group(1).capitalize()
                ano = match.group(2)
                mes_ano_chave = f"{mes}/{ano}"
                sections[mes_ano_chave].append(texto_pagina)
        return sections

    def _processar_mes_conteudo(self, texto_secao: str, mes_ano: str) -> Dict[str, Any]:
        resultados_mes = {
            "rubricas": defaultdict(float),
            "rubricas_detalhadas": defaultdict(float)
        }

        # Isola o bloco da tabela principal
        tabela_match = re.search(r'(VANTAGENS|Descrição)(.*?)TOTAL DE VANTAGENS', texto_secao, re.DOTALL | re.IGNORECASE)
        if not tabela_match:
            return resultados_mes
        
        bloco_tabela = tabela_match.group(2)
        
        # Padrões para encontrar qualquer coisa que pareça um código ou valor
        padrao_codigo = re.compile(r'\b([0-9A-Z/]{3,5})\b')
        padrao_valor = re.compile(r'\b(\d{1,3}(?:[.,]\d{3})*,\d{2})\b')

        for linha in bloco_tabela.strip().split('\n'):
            codigos_na_linha = [m.group(1) for m in padrao_codigo.finditer(linha)]
            valores_na_linha = [m.group(1) for m in padrao_valor.finditer(linha)]

            # Lógica para linhas que contêm tanto proventos quanto descontos (2 códigos, 2 valores)
            if len(codigos_na_linha) >= 2 and len(valores_na_linha) >= 2:
                cod_prov, cod_desc = codigos_na_linha[0], codigos_na_linha[1]
                val_prov_str, val_desc_str = valores_na_linha[0], valores_na_linha[1]
                
                if cod_prov in self.codigos_proventos:
                    resultados_mes["rubricas"][cod_prov] += self.extrair_valor(val_prov_str)
                if cod_desc in self.codigos_descontos:
                    resultados_mes["rubricas_detalhadas"][cod_desc] += self.extrair_valor(val_desc_str)
            
            # Lógica para linhas que contêm apenas um item (seja provento ou desconto)
            elif len(codigos_na_linha) == 1 and len(valores_na_linha) == 1:
                codigo = codigos_na_linha[0]
                valor = self.extrair_valor(valores_na_linha[0])
                if codigo in self.codigos_proventos:
                    resultados_mes["rubricas"][codigo] += valor
                elif codigo in self.codigos_descontos:
                    resultados_mes["rubricas_detalhadas"][codigo] += valor
        
        return resultados_mes

    def processar_contracheque(self, filepath: str) -> Dict[str, Any]:
        try:
            with open(filepath, 'rb') as f:
                file_bytes = f.read()

            doc = fitz.open(stream=file_bytes, filetype="pdf")
            secoes = self._extrair_secoes_por_mes_ano(doc)
            
            resultados_finais = {"dados_mensais": {}}

            for mes_ano, textos_pagina in secoes.items():
                dados_mensais_agregados = defaultdict(lambda: defaultdict(float))
                for texto_secao in textos_pagina:
                    dados_pagina = self._processar_mes_conteudo(texto_secao, mes_ano)
                    for cod, val in dados_pagina["rubricas"].items():
                        dados_mensais_agregados["rubricas"][cod] += val
                    for cod, val in dados_pagina["rubricas_detalhadas"].items():
                        dados_mensais_agregados["rubricas_detalhadas"][cod] += val

                total_proventos = sum(
                    val for cod, val in dados_mensais_agregados["rubricas"].items()
                    if not self.rubricas.get('proventos', {}).get(cod, {}).get('ignorar_na_soma', False)
                )
                
                dados_mensais_agregados["total_proventos"] = total_proventos
                resultados_finais["dados_mensais"][mes_ano] = dados_mensais_agregados

            meses_processados = sorted(
                resultados_finais['dados_mensais'].keys(),
                key=lambda m: (int(m.split('/')[1]), int(self.meses.get(m.split('/')[0], 0)))
            )
            
            if meses_processados:
                resultados_finais['primeiro_mes'] = meses_processados[0]
                resultados_finais['ultimo_mes'] = meses_processados[-1]
                resultados_finais['meses_para_processar'] = meses_processados
            
            return resultados_finais
        except Exception as e:
            logger.error(f"Erro ao processar contracheque: {str(e)}", exc_info=True)
            raise
            
    def converter_data_para_numerico(self, data_texto: str) -> str:
        try:
            mes, ano = data_texto.split('/')
            return f"{self.meses.get(mes, '00')}/{ano}"
        except (ValueError, AttributeError):
            return "00/0000"

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
