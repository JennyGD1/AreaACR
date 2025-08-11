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
            valor_limpo = re.sub(r'[^\d,]', '', valor_str)
            valor = valor_limpo.replace('.', '').replace(',', '.')
            return float(valor)
        except (ValueError, AttributeError):
            return 0.0

    def _extrair_secoes_por_mes_ano(self, doc):
        sections = defaultdict(list)
        month_year_pattern = re.compile(r'(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\s*/\s*(\d{4})', re.IGNORECASE)
        
        for page_num, page in enumerate(doc):
            texto_pagina = page.get_text("text", sort=True)
            match = month_year_pattern.search(texto_pagina)
            if match:
                mes = match.group(1).capitalize()
                ano = match.group(2)
                mes_ano_chave = f"{mes}/{ano}"
                sections[mes_ano_chave].append(texto_pagina)
        
        if not sections:
            raise ValueError("Não foi possível encontrar nenhuma seção de Mês/Ano no documento.")
        
        return sections

    def processar_contracheque(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                file_bytes = f.read()

            doc = fitz.open(stream=file_bytes, filetype="pdf")
            secoes = self._extrair_secoes_por_mes_ano(doc)
            
            resultados_finais = { "dados_mensais": {} }

            for mes_ano, textos_pagina in secoes.items():
                dados_mensais_agregados = {"rubricas": defaultdict(float), "rubricas_detalhadas": defaultdict(float)}
                for texto_secao in textos_pagina:
                    dados_pagina = self._processar_mes_conteudo(texto_secao, mes_ano)
                    for cod, val in dados_pagina["rubricas"].items():
                        dados_mensais_agregados["rubricas"][cod] += val
                    for cod, val in dados_pagina["rubricas_detalhadas"].items():
                        dados_mensais_agregados["rubricas_detalhadas"][cod] += val
                
                total_proventos_calculado = sum(
                    valor for codigo, valor in dados_mensais_agregados["rubricas"].items()
                    if not self.rubricas.get('proventos', {}).get(codigo, {}).get('ignorar_na_soma', False)
                )
                dados_mensais_agregados["total_proventos"] = total_proventos_calculado
                logger.debug(f"TOTAIS FINAIS PARA {mes_ano}: Proventos (soma)={total_proventos_calculado:.2f}, Descontos={sum(dados_mensais_agregados['rubricas_detalhadas'].values()):.2f}")
                
                resultados_finais["dados_mensais"][mes_ano] = dados_mensais_agregados

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

        tabela_match = re.search(r'(VANTAGENS|Descrição)(.*?)TOTAL DE VANTAGENS', texto_secao, re.DOTALL | re.IGNORECASE)
        if not tabela_match: return resultados_mes
        
        bloco_tabela = tabela_match.group(2)

        padrao_codigo = re.compile(r'\b([0-9A-Z/]{3,5})\b')
        padrao_valor = re.compile(r'\b(\d{1,3}(?:[.,]\d{3})*,\d{2})\b')

        for linha in bloco_tabela.strip().split('\n'):
            codigos_na_linha = [m.group(1) for m in padrao_codigo.finditer(linha)]
            valores_na_linha = [m.group(1) for m in padrao_valor.finditer(linha)]

            if len(codigos_na_linha) == 1 and len(valores_na_linha) == 1:
                codigo = codigos_na_linha[0]
                valor = self.extrair_valor(valores_na_linha[0])
                if codigo in self.codigos_proventos:
                    resultados_mes["rubricas"][codigo] = valor
                elif codigo in self.codigos_descontos:
                    resultados_mes["rubricas_detalhadas"][codigo] = valor
            
            elif len(codigos_na_linha) >= 2 and len(valores_na_linha) >= 2:
                # Provento (1º par)
                if codigos_na_linha[0] in self.codigos_proventos:
                    resultados_mes["rubricas"][codigos_na_linha[0]] = self.extrair_valor(valores_na_linha[0])
                
                # Desconto (2º par)
                if codigos_na_linha[1] in self.codigos_descontos:
                    resultados_mes["rubricas_detalhadas"][codigos_na_linha[1]] = self.extrair_valor(valores_na_linha[1])
        
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
