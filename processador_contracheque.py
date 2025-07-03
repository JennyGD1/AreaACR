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
            "JANEIRO": "01", "FEVEREIRO": "02", "MARÇO": "03",
            "ABRIL": "04", "MAIO": "05", "JUNHO": "06",
            "JULHO": "07", "AGOSTO": "08", "SETEMBRO": "09",
            "OUTUBRO": "10", "NOVEMBRO": "11", "DEZEMBRO": "12"
        }

    def _extrair_texto_do_pdf(self, file_bytes: bytes) -> str:
        """Extrai texto de um arquivo PDF usando PyMuPDF."""
        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                texto = ""
                for page in doc:
                    texto += page.get_text()
            return texto
        except Exception as e:
            logger.error(f"Erro ao ler o PDF: {e}")
            raise ValueError("Não foi possível ler o arquivo PDF.")

    def _extrair_periodo(self, texto: str) -> str:
        """Extrai o período (mês/ano) do contracheque."""
        padrao_periodo = re.search(
            r"referente ao mês de\s+(?P<mes>\w+)\s+/\s+(?P<ano>\d{4})",
            texto,
            re.IGNORECASE
        )
        if padrao_periodo:
            mes_nome = padrao_periodo.group("mes").upper()
            ano = padrao_periodo.group("ano")
            mes_num = self.meses.get(mes_nome, "00")
            return f"{mes_num}/{ano}"
        return "Desconhecido/0000"

    def _extrair_rubricas(self, texto: str) -> (List[Dict], List[Dict]):
        """Extrai as rubricas de proventos e descontos."""
        proventos = []
        descontos = []

        # Regex para capturar uma linha de rubrica (código, descrição, valor)
        # É mais flexível com os espaços e captura o valor no final da linha.
        padrao_rubrica = re.compile(
            r"^(?P<codigo>\d{4})\s+(?P<descricao>.+?)\s+(?P<valor>[\d\.,]+)$",
            re.MULTILINE
        )

        # Delimita a área de proventos
        try:
            area_proventos = re.search(
                r"DESCRIÇÃO DOS PROVENTOS(.*?)TOTAIS",
                texto, re.DOTALL | re.IGNORECASE
            ).group(1)
            for match in padrao_rubrica.finditer(area_proventos):
                proventos.append({
                    'codigo': match.group('codigo'),
                    'descricao': match.group('descricao').strip(),
                    'valor': float(match.group('valor').replace('.', '').replace(',', '.'))
                })
        except AttributeError:
            logger.warning("Não foi possível encontrar a seção de proventos.")

        # Delimita a área de descontos
        try:
            area_descontos = re.search(
                r"DESCRIÇÃO DOS DESCONTOS(.*?)LÍQUIDO",
                texto, re.DOTALL | re.IGNORECASE
            ).group(1)
            for match in padrao_rubrica.finditer(area_descontos):
                descontos.append({
                    'codigo': match.group('codigo'),
                    'descricao': match.group('descricao').strip(),
                    'valor': float(match.group('valor').replace('.', '').replace(',', '.'))
                })
        except AttributeError:
            logger.warning("Não foi possível encontrar a seção de descontos.")
            
        return proventos, descontos

    def processar(self, file_bytes: bytes) -> Dict[str, Any]:
        """Processa um arquivo de contracheque em bytes."""
        try:
            texto = self._extrair_texto_do_pdf(file_bytes)
            
            if "GOVERNO DO ESTADO DA BAHIA" not in texto:
                raise ValueError("Documento não parece ser um contracheque do Governo da Bahia.")

            periodo = self._extrair_periodo(texto)
            vantagens, descontos = self._extrair_rubricas(texto)

            if not vantagens and not descontos:
                raise ValueError("Nenhuma rubrica de provento ou desconto foi encontrada. Verifique o formato do PDF.")

            dados_mensais = {
                periodo: {
                    "total_proventos": sum(v['valor'] for v in vantagens),
                    "total_descontos": sum(d['valor'] for d in descontos),
                    "rubricas": {v['codigo']: v['valor'] for v in vantagens},
                    "rubricas_detalhadas": {d['codigo']: d['valor'] for d in descontos},
                    "descricoes": {**{v['codigo']: v['descricao'] for v in vantagens},
                                   **{d['codigo']: d['descricao'] for d in descontos}}
                }
            }

            return {
                "periodo": periodo,
                "dados_mensais": dados_mensais,
                "tabela": self._identificar_tabela(texto),
                "proventos": vantagens,
                "descontos": descontos,
                "erro": None
            }

        except Exception as e:
            logger.error(f"Erro ao processar contracheque: {str(e)}")
            return {"erro": str(e), "dados_mensais": {}}

    def _identificar_tabela(self, texto: str) -> str:
        if "GOVERNO DO ESTADO DA BAHIA" in texto:
            return "BAHIA"
        return "DESCONHECIDA"
    
    # MANTENHA OS MÉTODOS gerar_tabela_geral e gerar_totais como estão no seu código original
    # Eles serão populados com os dados extraídos por este novo processador.

    def gerar_tabela_geral(self, resultados: Dict[str, Any]) -> Dict[str, Any]:
        """Gera tabela no formato esperado pelo front-end"""
        if not resultados or "dados_mensais" not in resultados:
            return {"colunas": [], "dados": []}
        
        colunas = ["MÊS/ANO", "PROVENTOS", "DESCONTOS", "LÍQUIDO"]
        dados_tabela = []

        for mes_ano, dados_mes in resultados.get('dados_mensais', {}).items():
            proventos = dados_mes.get('total_proventos', 0)
            descontos = dados_mes.get('total_descontos', 0)
            liquido = proventos - descontos
            dados_tabela.append({
                "mes_ano": mes_ano,
                "valores": [
                    f"R$ {proventos:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                    f"R$ {descontos:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                    f"R$ {liquido:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                ]
            })
        
        return {"colunas": colunas, "dados": dados_tabela}

    def gerar_totais(self, resultados: Dict[str, Any]) -> Dict[str, Any]:
        """Gera totais no formato esperado pelo front-end"""
        # A sua implementação original está boa, pode mantê-la.
        # Esta é uma implementação básica para garantir que funcione.
        return {
            'mensais': defaultdict(lambda: defaultdict(float)),
            'anuais': defaultdict(lambda: defaultdict(float)),
            'geral': defaultdict(float)
        }

    def processar_contracheque(self, filepath: str) -> Dict[str, Any]:
        """Método compatível com a chamada em app.py, lendo a partir de um caminho de arquivo."""
        try:
            with open(filepath, 'rb') as f:
                file_bytes = f.read()
            return self.processar(file_bytes)
        except FileNotFoundError:
            return {"erro": f"Arquivo não encontrado: {filepath}", "dados_mensais": {}}
        except Exception as e:
            return {"erro": f"Erro ao abrir o arquivo: {e}", "dados_mensais": {}}
