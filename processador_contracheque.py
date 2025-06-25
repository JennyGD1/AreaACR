# processador_contracheque.py (VERSÃO CORRIGIDA)

import json
import re
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

class ProcessadorContracheque:
    def __init__(self, config_path='config.json'):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self.codigos_proventos = set(self.config.get('codigos_proventos', []))
            self.rubricas_detalhadas = self.config.get('rubricas_detalhadas', {})
        except Exception as e:
            logger.error(f"Erro ao carregar config: {str(e)}")
            self.config = {}
            self.codigos_proventos = set()
            self.rubricas_detalhadas = {}

    def _extrair_valor(self, linha):
        padrao = r'(\d{1,3}(?:\.\d{3})*,\d{2})'
        match = re.search(padrao, linha)
        if match:
            valor = match.group(1).replace('.', '').replace(',', '.')
            try:
                return float(valor)
            except ValueError:
                return 0.0
        return 0.0

    def processar_texto(self, texto):
        resultados = defaultdict(dict)
        linhas = texto.split('\n')
        
        # Encontrar todos os períodos no texto
        periodos = re.findall(r'(\d{2})\.(\d{4})', texto)
        if not periodos:
            return {}
            
        # Pegar o período mais recente
        periodo_recente = sorted(periodos, key=lambda x: (int(x[1]), int(x[0]))[-1]
        periodo_str = f"{periodo_recente[0]}.{periodo_recente[1]}"
        
        # Filtrar linhas apenas do período recente
        linhas_periodo = [linha for linha in linhas if periodo_str in linha]
        
        # Processar rubricas
        for linha in linhas_periodo:
            codigo_match = re.match(r'^(\d{4}|[A-Z]\d{3})', linha.strip())
            if codigo_match:
                codigo = codigo_match.group(1)
                valor = self._extrair_valor(linha)
                if valor > 0:
                    resultados[codigo] = valor
        
        return dict(resultados)
