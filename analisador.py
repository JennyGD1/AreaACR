import json
import logging
from typing import Dict, Any, Optional
from processador_contracheque import ProcessadorContracheque

logger = logging.getLogger(__name__)

class AnalisadorPlanserv:
    def __init__(self, processador=None):
        self.processador = processador if processador else ProcessadorContracheque()
        self._carregar_rubricas_planserv()

    def _carregar_rubricas_planserv(self):
        """Carrega as rubricas específicas do Planserv"""
        self.rubricas_planserv = {
            'proventos': ['003P', '00P7', '04P6', '0J40', '0P42', '1J06'],
            'descontos': ['7033', '7035', '7038', '7039', '7034']
        }
        
        self.descricoes_planserv = {
            '7033': 'Assistência a Saúde (Titular)',
            '7035': 'Planserv / Cônjuge',
            '7038': 'Planserv Agregado Jovem',
            '7039': 'Planserv Agregado Maior',
            '7034': 'Contribuição Planserv'
        }

    def analisar_resultados(self, resultados):
        """Analisa especificamente os dados do Planserv"""
        if not resultados or 'dados_mensais' not in resultados:
            return {'erro': 'Nenhum dado válido encontrado'}

        totais = {
            'proventos': {'total': 0.0, 'detalhes': []},
            'descontos': {'total': 0.0, 'detalhes': []}
        }

        for mes_ano, dados_mes in resultados['dados_mensais'].items():
            # Proventos do Planserv
            for codigo in self.rubricas_planserv['proventos']:
                if codigo in dados_mes['rubricas']:
                    valor = dados_mes['rubricas'][codigo]
                    totais['proventos']['total'] += valor
                    totais['proventos']['detalhes'].append({
                        'codigo': codigo,
                        'descricao': dados_mes['descricoes'].get(codigo, ''),
                        'valor': valor
                    })

            # Descontos do Planserv
            for codigo in self.rubricas_planserv['descontos']:
                if codigo in dados_mes['rubricas_detalhadas']:
                    valor = dados_mes['rubricas_detalhadas'][codigo]
                    totais['descontos']['total'] += valor
                    totais['descontos']['detalhes'].append({
                        'codigo': codigo,
                        'descricao': self.descricoes_planserv.get(codigo, ''),
                        'valor': valor
                    })

        return totais

    def calcular_totais(self, resultados: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calcula totais de proventos e descontos Planserv com tratamento robusto
        
        Args:
            resultados: Dicionário com os dados processados do contracheque
            
        Returns:
            Dicionário com totais de proventos e descontos formatados
        """
        totais = {
            'proventos': {'total': 0.0, 'rubricas': {}},
            'descontos': {'total': 0.0, 'rubricas': {}}
        }

        if not resultados or not isinstance(resultados.get('dados_mensais'), dict):
            return totais

        try:
            # Inicializa rubricas
            for cod in self.rubricas_planserv['proventos']:
                totais['proventos']['rubricas'][cod] = 0.0
            for cod in self.rubricas_planserv['descontos']:
                totais['descontos']['rubricas'][cod] = 0.0

            # Processa cada mês
            for dados_mes in resultados['dados_mensais'].values():
                self._processar_mes(dados_mes, totais)
                
        except Exception as e:
            logger.error(f"Erro ao calcular totais: {str(e)}")
            
        return totais

    def _processar_mes(self, dados_mes: Dict[str, Any], totais: Dict[str, Any]):
        """Processa os dados de um mês específico"""
        # Processa proventos
        if isinstance(dados_mes.get('rubricas'), dict):
            for cod, valor in dados_mes['rubricas'].items():
                if cod in self.rubricas_planserv['proventos'] and isinstance(valor, (int, float)):
                    totais['proventos']['rubricas'][cod] += valor
                    totais['proventos']['total'] += valor
        
        # Processa descontos
        if isinstance(dados_mes.get('rubricas_detalhadas'), dict):
            for cod, valor in dados_mes['rubricas_detalhadas'].items():
                if cod in self.rubricas_planserv['descontos'] and isinstance(valor, (int, float)):
                    totais['descontos']['rubricas'][cod] += valor
                    totais['descontos']['total'] += valor

    def analisar_resultados(self, resultados: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analisa os resultados e retorna um relatório consolidado do Planserv
        
        Args:
            resultados: Dicionário com os dados processados do contracheque
            
        Returns:
            Dicionário formatado com totais e detalhes para o front-end
        """
        if not resultados or not isinstance(resultados.get('dados_mensais'), dict):
            return {'erro': 'Nenhum dado válido encontrado', 'tabela': resultados.get('tabela', 'Desconhecida')}

        try:
            totais = self.calcular_totais(resultados)
            
            return {
                'proventos': self._formatar_detalhes(totais['proventos'], 'proventos'),
                'descontos': self._formatar_detalhes(totais['descontos'], 'descontos'),
                'tabela': resultados.get('tabela', 'Desconhecida')
            }
        except Exception as e:
            logger.error(f"Erro na análise: {str(e)}")
            return {'erro': str(e), 'tabela': resultados.get('tabela', 'Desconhecida')}

    def _formatar_detalhes(self, dados: Dict[str, Any], tipo: str) -> Dict[str, Any]:
        """Formata os detalhes para exibição"""
        detalhes = []
        
        for cod, valor in dados.get('rubricas', {}).items():
            if valor > 0:
                descricao = self.rubricas_de_origem.get(tipo, {}).get(cod, {}).get('descricao', 'Desconhecido')
                detalhes.append({
                    'codigo': cod,
                    'descricao': descricao,
                    'valor': round(valor, 2)
                })
        
        return {
            'total': round(dados.get('total', 0), 2),
            'detalhes': sorted(detalhes, key=lambda x: x['valor'], reverse=True)
        }
