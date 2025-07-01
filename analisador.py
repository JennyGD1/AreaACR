# analisador.py
import json
import logging
from typing import Dict, Any, Optional
from processador_contracheque import ProcessadorContracheque

logger = logging.getLogger(__name__)

class AnalisadorPlanserv:
    def __init__(self, processador=None):
        self.processador = processador 
        if self.processador is None:
            self.processador = ProcessadorContracheque() 
        
        self.rubricas_de_origem = self.processador.rubricas 
        
        # ### LÓGICA DE ANÁLISE CORRIGIDA ###
        # Aqui definimos explicitamente quais rubricas queremos analisar,
        # com base no seu objetivo.
        self.rubricas_planserv_para_analise = {
            # Base de cálculo: todos os proventos encontrados.
            'proventos_base': list(self.rubricas_de_origem.get('proventos', {}).keys()),
            
            # Descontos a serem somados: apenas os do Planserv e a Contribuição SPSM.
            # Baseado no seu pedido de R$ 1.548,80 de descontos.
            'descontos_planserv': ['7033', '7035', '7038', '7039', '7P44']
        }


    def analisar_resultados(self, resultados: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analisa os dados processados e retorna totais e detalhes do Planserv.
        """
        totais = {
            'proventos_base': {'total': 0.0, 'detalhes': []},
            'descontos_planserv': {'total': 0.0, 'detalhes': []}
        }

        if not resultados or 'dados_mensais' not in resultados:
            return {
                'proventos': {'total': 0.0, 'detalhes': []},
                'descontos': {'total': 0.0, 'detalhes': []},
                'tabela': resultados.get('tabela', 'Desconhecida')
            }

        # Dicionários para acumular valores totais de cada rubrica
        proventos_acumulados = defaultdict(float)
        descontos_acumulados = defaultdict(float)

        # Processa cada mês para acumular os valores
        for mes_ano, dados_mes in resultados['dados_mensais'].items():
            # Acumula proventos que formam a base do Planserv
            if isinstance(dados_mes.get('rubricas'), dict):
                for codigo, valor in dados_mes['rubricas'].items():
                    if codigo in self.rubricas_planserv_para_analise['proventos_base']:
                        proventos_acumulados[codigo] += valor
            
            # Acumula descontos específicos do Planserv
            if isinstance(dados_mes.get('rubricas_detalhadas'), dict):
                for codigo, valor in dados_mes['rubricas_detalhadas'].items():
                    if codigo in self.rubricas_planserv_para_analise['descontos_planserv']:
                        descontos_acumulados[codigo] += valor

        # Monta a lista de detalhes dos proventos
        for codigo, valor_total in proventos_acumulados.items():
            totais['proventos_base']['detalhes'].append({
                'codigo': codigo,
                'descricao': self.rubricas_de_origem.get('proventos', {}).get(codigo, {}).get('descricao', 'Desconhecido'),
                'valor': valor_total
            })
            totais['proventos_base']['total'] += valor_total
        
        # Monta a lista de detalhes dos descontos
        for codigo, valor_total in descontos_acumulados.items():
            totais['descontos_planserv']['detalhes'].append({
                'codigo': codigo,
                'descricao': self.rubricas_de_origem.get('descontos', {}).get(codigo, {}).get('descricao', 'Desconhecido'),
                'valor': valor_total
            })
            totais['descontos_planserv']['total'] += valor_total

        return {
            'proventos': {
                'total': round(totais['proventos_base']['total'], 2),
                'detalhes': sorted([d for d in totais['proventos_base']['detalhes'] if d['valor'] > 0], key=lambda x: x['codigo'])
            },
            'descontos': {
                'total': round(totais['descontos_planserv']['total'], 2),
                'detalhes': sorted([d for d in totais['descontos_planserv']['detalhes'] if d['valor'] > 0], key=lambda x: x['codigo'])
            },
            'tabela': resultados.get('tabela', 'Desconhecida')
        }
