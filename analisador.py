import json
import logging
from typing import Dict, Any, Optional
from processador_contracheque import ProcessadorContracheque

logger = logging.getLogger(__name__)

class AnalisadorPlanserv:
    def __init__(self, processador: Optional[ProcessadorContracheque] = None):
        """Inicializa o analisador com um processador existente ou cria um novo"""
        self.processador = processador if processador else ProcessadorContracheque()
        self._carregar_rubricas()
    
    def _carregar_rubricas(self):
        """Carrega e valida as rubricas do processador"""
        try:
            self.rubricas_completas = self.processador.rubricas_completas
            self.rubricas_de_origem = self.processador.rubricas
            
            if not self.rubricas_de_origem:
                raise ValueError("Rubricas não foram carregadas corretamente")
                
            self.rubricas_planserv = {
                'proventos': list(self.rubricas_de_origem.get('proventos', {}).keys()),
                'descontos': list(self.rubricas_de_origem.get('descontos', {}).keys())
            }
        except Exception as e:
            logger.error(f"Erro ao carregar rubricas: {str(e)}")
            raise

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
