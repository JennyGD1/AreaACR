import json
import logging
from processador_contracheque import ProcessadorContracheque

logger = logging.getLogger(__name__)

class AnalisadorPlanserv:
    def __init__(self):
        self.processador = ProcessadorContracheque()
        self.rubricas_detalhadas = self.processador.rubricas_detalhadas
        
        # Rubricas específicas do Planserv que queremos somar
        self.rubricas_planserv = {
            'proventos': ['7001', '7002', '7003'],  # Exemplo - ajuste conforme suas rubricas
            'descontos': ['7033', '7034', '7035', '7038', '7039', '7040']  # Exemplo
        }

    def calcular_totais(self, resultados):
        """
        Calcula totais de proventos e descontos Planserv
        Retorna: {
            'proventos': {'total': X, 'rubricas': {'cod1': valor1, ...}},
            'descontos': {'total': Y, 'rubricas': {'cod1': valor1, ...}}
        }
        """
        totais = {
            'proventos': {'total': 0.0, 'rubricas': {}},
            'descontos': {'total': 0.0, 'rubricas': {}}
        }

        if not resultados or 'dados_mensais' not in resultados:
            return totais

        # Inicializa as rubricas com zero
        for cod in self.rubricas_planserv['proventos']:
            totais['proventos']['rubricas'][cod] = 0.0
        for cod in self.rubricas_planserv['descontos']:
            totais['descontos']['rubricas'][cod] = 0.0

        # Soma os valores por mês
        for mes_ano, dados_mes in resultados['dados_mensais'].items():
            # Proventos
            if 'rubricas' in dados_mes:
                for cod, valor in dados_mes['rubricas'].items():
                    if cod in self.rubricas_planserv['proventos']:
                        totais['proventos']['rubricas'][cod] += valor
                        totais['proventos']['total'] += valor
            
            # Descontos
            if 'rubricas_detalhadas' in dados_mes:
                for cod, valor in dados_mes['rubricas_detalhadas'].items():
                    if cod in self.rubricas_planserv['descontos']:
                        totais['descontos']['rubricas'][cod] += valor
                        totais['descontos']['total'] += valor

        return totais

    def analisar_resultados(self, resultados):
        """
        Versão simplificada que retorna apenas os totais
        """
        if not resultados or 'dados_mensais' not in resultados:
            return {'erro': 'Nenhum dado válido encontrado'}

        # Calcula totais
        totais = self.calcular_totais(resultados)
        
        # Adiciona descrições para melhor legibilidade
        resultado_final = {
            'proventos': {
                'total': totais['proventos']['total'],
                'detalhes': []
            },
            'descontos': {
                'total': totais['descontos']['total'],
                'detalhes': []
            },
            'tabela': resultados.get('tabela', 'Desconhecida')
        }

        # Preenche detalhes com descrições
        for cod, valor in totais['proventos']['rubricas'].items():
            if valor > 0:
                resultado_final['proventos']['detalhes'].append({
                    'codigo': cod,
                    'descricao': self.processador.rubricas['proventos'].get(cod, {}).get('descricao', 'Desconhecido'),
                    'valor': valor
                })

        for cod, valor in totais['descontos']['rubricas'].items():
            if valor > 0:
                resultado_final['descontos']['detalhes'].append({
                    'codigo': cod,
                    'descricao': self.rubricas_detalhadas.get(cod, {}).get('descricao', 'Desconhecido'),
                    'valor': valor
                })

        return resultado_final
