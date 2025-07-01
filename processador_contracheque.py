import re
from typing import Dict, List, Any
from collections import defaultdict
import fitz  # PyMuPDF
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ProcessadorContracheque:
    def __init__(self, rubricas=None):
        self.rubricas = rubricas or {"proventos": {}, "descontos": {}}
        self.meses = {
            "Janeiro": "01", "Fevereiro": "02", "Março": "03",
            "Abril": "04", "Maio": "05", "Junho": "06",
            "Julho": "07", "Agosto": "08", "Setembro": "09",
            "Outubro": "10", "Novembro": "11", "Dezembro": "12"
        }

    def _extrair_secao(self, texto: str, secao: str) -> List[Dict[str, Any]]:
        padrao = re.compile(
            rf'{secao}.*?(?P<conteudo>.*?)(?=DESCONTOS|TOTAL|\Z)',
            re.DOTALL | re.IGNORECASE
        )
        match = padrao.search(texto)
        if not match:
            return []
        
        conteudo = match.group('conteudo')
        padrao_rubrica = re.compile(
            r'(?P<codigo>\d\.\d{2}[ªº]|\d{4})\s+'
            r'(?P<descricao>[A-Za-zÀ-ú\s\-]+?)\s+'
            r'(?:\d+\.\d+\s+\d{2}\.\d{4}\s+)?'
            r'(?P<valor>[\d\.,]+)'
        )
        
        return [{
            'codigo': m.group('codigo'),
            'descricao': m.group('descricao').strip(),
            'valor': float(m.group('valor').replace('.', '').replace(',', '.'))
        } for m in padrao_rubrica.finditer(conteudo)]

    def processar(self, file_bytes: bytes) -> Dict[str, Any]:
        try:
            texto = fitz.open(stream=file_bytes, filetype="pdf").get_text()
            
            if "GOVERNO DO ESTADO DA BAHIA" not in texto:
                raise ValueError("Documento não é um contracheque da Bahia")
            
            periodo = re.search(r'AVISO DE CRÉDITO\s+(\w+/\d{4})', texto)
            vantagens = self._extrair_secao(texto, "VANTAGENS")
            descontos = self._extrair_secao(texto, "DESCONTOS")
            
            # Converte para o formato esperado pelo AnalisadorPlanserv
            mes_ano = periodo.group(1) if periodo else "Desconhecido/0000"
            dados_mensais = {
                mes_ano: {
                    "total_proventos": sum(v['valor'] for v in vantagens),
                    "rubricas": {v['codigo']: v['valor'] for v in vantagens},
                    "rubricas_detalhadas": {d['codigo']: d['valor'] for d in descontos},
                    "descricoes": {**{v['codigo']: v['descricao'] for v in vantagens},
                                  **{d['codigo']: d['descricao'] for d in descontos}}
                }
            }
            
            return {
                "periodo": mes_ano,
                "dados_mensais": dados_mensais,
                "tabela": self._identificar_tabela(texto),
                "proventos": vantagens,
                "descontos": descontos
            }
            
        except Exception as e:
            logger.error(f"Erro: {str(e)}")
            return {"erro": str(e)}

    def _identificar_tabela(self, texto: str) -> str:
        if "GOVERNO DO ESTADO DA BAHIA" in texto:
            return "BAHIA"
        return "DESCONHECIDA"

    def gerar_tabela_geral(self, resultados: Dict[str, Any]) -> Dict[str, Any]:
        """Gera tabela no formato esperado pelo front-end"""
        if not resultados or "dados_mensais" not in resultados:
            return {"colunas": [], "dados": []}
        
        # Implementação simplificada - adapte conforme necessário
        return {
            "colunas": ["MÊS/ANO", "PROVENTOS", "DESCONTOS", "LÍQUIDO"],
            "dados": [{
                "mes_ano": list(resultados["dados_mensais"].keys())[0],
                "valores": [
                    resultados["dados_mensais"][list(resultados["dados_mensais"].keys())[0]]["total_proventos"],
                    sum(resultados["dados_mensais"][list(resultados["dados_mensais"].keys())[0]["rubricas_detalhadas"].values()),
                    resultados["dados_mensais"][list(resultados["dados_mensais"].keys())[0]]["total_proventos"] - 
                    sum(resultados["dados_mensais"][list(resultados["dados_mensais"].keys())[0]["rubricas_detalhadas"].values())
                ]
            }]
        }

    def gerar_totais(self, resultados: Dict[str, Any]) -> Dict[str, Any]:
        """Gera totais no formato esperado pelo front-end"""
        if not resultados or "dados_mensais" not in resultados:
            return {
                'mensais': defaultdict(lambda: defaultdict(float)),
                'anuais': defaultdict(lambda: defaultdict(float)),
                'geral': defaultdict(float)
            }
        
        # Implementação simplificada - adapte conforme necessário
        return {
            'mensais': defaultdict(lambda: defaultdict(float)),
            'anuais': defaultdict(lambda: defaultdict(float)),
            'geral': defaultdict(float)
        }

    def processar_contracheque(self, filepath: str) -> Dict[str, Any]:
        """Método compatível com a chamada em app.py"""
        with open(filepath, 'rb') as f:
            return self.processar(f.read())
