import re
from typing import Dict, List, Any
from collections import defaultdict
import fitz  # PyMuPDF
import logging

logger = logging.getLogger(__name__)

class ProcessadorContracheque:
    def __init__(self, rubricas=None):
        self.meses = {
            "Janeiro": "01", "Fevereiro": "02", "Março": "03", "Abril": "04",
            "Maio": "05", "Junho": "06", "Julho": "07", "Agosto": "08",
            "Setembro": "09", "Outubro": "10", "Novembro": "11", "Dezembro": "12"
        }

    def _extrair_secao(self, texto: str, secao: str) -> List[Dict[str, Any]]:
        """Extrai uma seção específica (VANTAGENS/DESCONTOS)"""
        padrao_secao = re.compile(
            rf'{secao}.*?(?P<conteudo>.*?)(?=DESCONTOS|TOTAL|\Z)',
            re.DOTALL | re.IGNORECASE
        )
        match = padrao_secao.search(texto)
        if not match:
            return []
        
        conteudo = match.group('conteudo')
        padrao_rubrica = re.compile(
            r'(?P<codigo>\d\.\d{2}[ªº]|\d{4})\s+'
            r'(?P<descricao>[A-Za-zÀ-ú\s\-]+?)\s+'
            r'(?:\d+\.\d+\s+\d{2}\.\d{4}\s+)?'
            r'(?P<valor>[\d\.,]+)'
        )
        
        itens = []
        for match in padrao_rubrica.finditer(conteudo):
            try:
                valor = float(match.group('valor').replace('.', '').replace(',', '.'))
                itens.append({
                    'codigo': match.group('codigo'),
                    'descricao': match.group('descricao').strip(),
                    'valor': valor
                })
            except ValueError:
                logger.warning(f"Valor inválido encontrado: {match.group('valor')}")
                continue
        
        return itens

    def _extrair_texto_pdf(self, file_bytes: bytes) -> str:
        """Extrai texto de um arquivo PDF"""
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            return "\n".join(page.get_text() for page in doc)
        except Exception as e:
            logger.error(f"Falha na extração do PDF: {str(e)}")
            raise

    def processar_contracheque(self, file_bytes: bytes) -> Dict[str, Any]:
        """Processa um contracheque da Bahia"""
        try:
            texto = self._extrair_texto_pdf(file_bytes)
            
            if "GOVERNO DO ESTADO DA BAHIA" not in texto:
                raise ValueError("Documento não é um contracheque da Bahia")
            
            # Extrai período (ex: "Janeiro/2021")
            periodo_match = re.search(r'AVISO DE CRÉDITO\s+(\w+/\d{4})', texto)
            periodo = periodo_match.group(1) if periodo_match else "Desconhecido"
            
            # Processa seções
            vantagens = self._extrair_secao(texto, "VANTAGENS")
            descontos = self._extrair_secao(texto, "DESCONTOS")
            
            # Calcula totais
            total_proventos = sum(item['valor'] for item in vantagens)
            total_descontos = sum(item['valor'] for item in descontos)
            
            return {
                "periodo": periodo,
                "proventos": vantagens,
                "descontos": descontos,
                "total_proventos": total_proventos,
                "total_descontos": total_descontos,
                "liquido": total_proventos - total_descontos
            }

        except Exception as e:
            logger.error(f"Erro no processamento: {str(e)}")
            return {
                "erro": str(e),
                "texto_extraido": texto[:1000] + "..." if 'texto' in locals() else None
            }
