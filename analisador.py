import json
import logging
from processador_contracheque import ProcessadorContracheque

logger = logging.getLogger(__name__)

class AnalisadorPlanserv:
    def __init__(self):
        self.processador = ProcessadorContracheque()
        self.rubricas_completas = self.processador.rubricas_completas
        self.rubricas_de_origem = self.processador.rubricas # Dicionário completo de rubricas por tipo

        # Rubricas específicas do Planserv que queremos somar, carregadas dinamicamente
        self.rubricas_planserv = {
            'proventos': list(self.rubricas_de_origem.get('proventos', {}).keys()), # Todas as rubricas de proventos
            'descontos': list(self.rubricas_de_origem.get('descontos', {}).keys())  # Todas as rubricas de descontos
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

        # Inicializa as rubricas com zero para todos os proventos e descontos conhecidos do Planserv (ou de todas as rubricas se for o caso)
        for cod in self.rubricas_planserv['proventos']:
            totais['proventos']['rubricas'][cod] = 0.0
        for cod in self.rubricas_planserv['descontos']:
            totais['descontos']['rubricas'][cod] = 0.0

        # Soma os valores por mês
        for mes_ano, dados_mes in resultados['dados_mensais'].items():
            # Proventos
            if 'rubricas' in dados_mes: # 'rubricas' no processador armazena proventos
                for cod, valor in dados_mes['rubricas'].items():
                    # Verifica se a rubrica é um provento relevante para o Planserv (baseado em self.rubricas_planserv['proventos'])
                    if cod in self.rubricas_planserv['proventos']:
                        totais['proventos']['rubricas'][cod] += valor
                        totais['proventos']['total'] += valor
            
            # Descontos
            if 'rubricas_detalhadas' in dados_mes: # 'rubricas_detalhadas' no processador armazena descontos
                for cod, valor in dados_mes['rubricas_detalhadas'].items():
                    # Verifica se a rubrica é um desconto relevante para o Planserv (baseado em self.rubricas_planserv['descontos'])
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

        # Preenche detalhes com descrições para proventos
        for cod, valor in totais['proventos']['rubricas'].items():
            if valor > 0:
                # Busca a descrição na estrutura carregada de rubricas de origem
                descricao = self.rubricas_de_origem.get('proventos', {}).get(cod, {}).get('descricao', 'Desconhecido')
                resultado_final['proventos']['detalhes'].append({
                    'codigo': cod,
                    'descricao': descricao,
                    'valor': valor
                })

        # Preenche detalhes com descrições para descontos
        for cod, valor in totais['descontos']['rubricas'].items():
            if valor > 0:
                # Busca a descrição na estrutura carregada de rubricas de origem
                descricao = self.rubricas_de_origem.get('descontos', {}).get(cod, {}).get('descricao', 'Desconhecido')
                resultado_final['descontos']['detalhes'].append({
                    'codigo': cod,
                    'descricao': descricao,
                    'valor': valor
                })

        return resultado_final
