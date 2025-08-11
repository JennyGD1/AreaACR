import re
from typing import Dict, List, DefaultDict
from collections import defaultdict
import fitz
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
        self._processar_rubricas_internas()

    def _carregar_rubricas_default(self) -> Dict:
        try:
            rubricas_path = Path(__file__).parent.parent / 'rubricas.json'
            with open(rubricas_path, 'r', encoding='utf-8') as f:
                dados = json.load(f)
                return dados.get('rubricas', {"proventos": {}, "descontos": {}})
        except Exception as e:
            logger.error(f"Erro ao carregar rubricas: {str(e)}")
            return {"proventos": {}, "descontos": {}}

    def _processar_rubricas_internas(self):
        self.codigos_proventos = list(self.rubricas.get('proventos', {}).keys())
        self.codigos_descontos = list(self.rubricas.get('descontos', {}).keys())

    def extrair_valor(self, valor_str: str) -> float:
        """Converte formatos como '1.809,50' para 1809.50 e '250,90' para 250.90"""
        try:
            valor_limpo = re.sub(r'[^\d,]', '', valor_str)
            
            if ',' in valor_limpo:
                partes = valor_limpo.split(',')
                inteiro = partes[0].replace('.', '')
                decimal = partes[1][:2].ljust(2, '0')
                return float(f"{inteiro}.{decimal}")
            return float(valor_limpo) / 100
        except Exception as e:
            logger.warning(f"Valor inválido '{valor_str}': {str(e)}")
            return 0.0

    def _processar_pagina(self, texto: str) -> Dict[str, DefaultDict[str, float]]:
        resultados = {
            "proventos": defaultdict(float),
            "descontos": defaultdict(float)
        }

        # Padrão melhorado para capturar valores com/sem separadores de milhar
        padrao = re.compile(
            r'([A-Z0-9/]+)\s+(.*?)\s+(\d{1,3}(?:[.,\s]\d{3})*[.,]\d{2})',
            re.MULTILINE
        )

        # Processa VANTAGENS
        if (bloco := self._extrair_bloco(texto, 'VANTAGENS', 'TOTAL')):
            for cod, desc, valor in padrao.findall(bloco):
                if cod in self.codigos_proventos:
                    resultados["proventos"][cod] += self.extrair_valor(valor)
                    logger.debug(f"Provento: {cod} = {valor} -> {resultados['proventos'][cod]}")

        # Processa DESCONTOS
        if (bloco := self._extrair_bloco(texto, 'DESCONTOS', 'TOTAL')):
            for cod, desc, valor in padrao.findall(bloco):
                if cod in self.codigos_descontos:
                    resultados["descontos"][cod] += self.extrair_valor(valor)

        return resultados

    def _extrair_bloco(self, texto: str, inicio: str, fim: str) -> str:
        """Extrai texto entre os marcadores"""
        padrao = re.compile(rf'{re.escape(inicio)}(.*?){re.escape(fim)}', re.DOTALL)
        match = padrao.search(texto)
        return match.group(1).strip() if match else ""

    def processar_contracheque(self, filepath: str) -> Dict[str, Any]:
        try:
            doc = fitz.open(filepath)
            texto_completo = "\n".join(page.get_text("text", sort=True) for page in doc)
            
            dados = self._processar_pagina(texto_completo)
            
            return {
                "proventos": dict(dados["proventos"]),
                "descontos": dict(dados["descontos"]),
                "total_proventos": sum(dados["proventos"].values()),
                "total_descontos": sum(dados["descontos"].values())
            }
        except Exception as e:
            logger.error(f"Erro ao processar {filepath}: {str(e)}")
            raise

    def converter_data_para_numerico(self, data_texto: str) -> str:
        try:
            mes, ano = data_texto.split('/')
            return f"{self.meses.get(mes, '00')}/{ano}"
        except (ValueError, AttributeError):
            return "00/0000"
        
    def gerar_tabela_proventos_resumida(self, resultados: Dict[str, Any]) -> Dict[str, Any]:
        tabela = {
            "colunas": ["Mês/Ano", "Total de Proventos"],
            "dados": []
        }
        
        for mes_ano in resultados.get("meses_para_processar", []):
            dados_mes = resultados.get("dados_mensais", {}).get(mes_ano, {})
            total_proventos = dados_mes.get("total_proventos", 0.0)
            tabela["dados"].append({
                "mes_ano": self.converter_data_para_numerico(mes_ano),
                "total": total_proventos
            })
        
        return tabela

    def gerar_tabela_descontos_detalhada(self, resultados: Dict[str, Any]) -> Dict[str, Any]:
        descontos_de_origem = self.rubricas.get('descontos', {})
        
        codigos_encontrados = set(
            cod for dados_mes in resultados.get("dados_mensais", {}).values()
            for cod in dados_mes.get("rubricas_detalhadas", {}).keys()
        )
        
        codigos_para_exibir = sorted([
            cod for cod in codigos_encontrados
            if descontos_de_origem.get(cod, {}).get("tipo") == "planserv"
        ])
        
        descricoes = {
            cod: descontos_de_origem.get(cod, {}).get('descricao', cod) 
            for cod in codigos_para_exibir
        }
        
        tabela = {
            "colunas": ["Mês/Ano"] + [descricoes.get(cod, cod) for cod in codigos_para_exibir],
            "dados": []
        }
        
        for mes_ano in resultados.get("meses_para_processar", []):
            linha = {
                "mes_ano": self.converter_data_para_numerico(mes_ano),
                "valores": []
            }
            
            rubricas_detalhadas_mes = resultados.get("dados_mensais", {}).get(mes_ano, {}).get("rubricas_detalhadas", {})
            
            for cod in codigos_para_exibir:
                linha["valores"].append(rubricas_detalhadas_mes.get(cod, 0.0))
            
            tabela["dados"].append(linha)
        
        return tabela
