import re
from typing import Dict, List, Any
from collections import defaultdict
import fitz  # PyMuPDF
import logging

logger = logging.getLogger(__name__)

class ProcessadorContracheque:
    def __init__(self, rubricas=None):
        """Inicializa com rubricas opcionais"""
        self.rubricas = rubricas or {"proventos": {}, "descontos": {}}
        self.meses = {
            "Janeiro": "01", "Fevereiro": "02", "Março": "03",
            "Abril": "04", "Maio": "05", "Junho": "06",
            "Julho": "07", "Agosto": "08", "Setembro": "09",
            "Outubro": "10", "Novembro": "11", "Dezembro": "12"
        }

    def _extrair_secao(self, texto: str, secao: str) -> List[Dict[str, Any]]:
        """Extrai seções do contracheque"""
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
        """Processa o arquivo PDF"""
        try:
            texto = fitz.open(stream=file_bytes, filetype="pdf").get_text()
            
            if "GOVERNO DO ESTADO DA BAHIA" not in texto:
                raise ValueError("Documento não é um contracheque da Bahia")
            
            periodo = re.search(r'AVISO DE CRÉDITO\s+(\w+/\d{4})', texto)
            vantagens = self._extrair_secao(texto, "VANTAGENS")
            descontos = self._extrair_secao(texto, "DESCONTOS")
            
            total_prov = sum(v['valor'] for v in vantagens)
            total_desc = sum(d['valor'] for d in descontos)
            
            return {
                "periodo": periodo.group(1) if periodo else "Desconhecido",
                "proventos": vantagens,
                "descontos": descontos,
                "total_proventos": total_prov,
                "total_descontos": total_desc,
                "liquido": total_prov - total_desc
            }
            
        except Exception as e:
            logger.error(f"Erro: {str(e)}")
            return {"erro": str(e)}
