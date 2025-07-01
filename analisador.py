import json
import logging
from typing import Dict, Any, Optional
from processador_contracheque import ProcessadorContracheque # Importa a classe ProcessadorContracheque

logger = logging.getLogger(__name__)

class AnalisadorPlanserv:
    def __init__(self, processador=None):
        # O analisador DEVE receber o processador já inicializado com as rubricas.
        self.processador = processador 
        if self.processador is None:
            # Se por algum motivo o processador não for passado (o que não deve acontecer no fluxo do app.py),
            # ele inicializa um, mas o ideal é que seja o mesmo que o app.py usa.
            self.processador = ProcessadorContracheque() 
        
        # As rubricas de proventos e descontos vêm do ProcessadorContracheque, que as carrega do rubricas.json
        self.rubricas_de_origem = self.processador.rubricas 
        
        # As rubricas do Planserv são as rubricas de DESCONTO que são do Planserv no rubricas.json.
        # As rubricas de PROVENTOS Planserv são aquelas que compõem a "base de cálculo" do Planserv.
        # Assumimos que todas as rubricas em 'proventos' no rubricas.json são parte da base de cálculo.
        self.rubricas_planserv_para_analise = {
            'proventos_base': list(self.rubricas_de_origem.get('proventos', {}).keys()),
            'descontos_planserv': [
                cod for cod, info in self.rubricas_de_origem.get('descontos', {}).items() 
                if 'planserv' in info.get('descricao', '').lower() # Exemplo: filtra por palavra "planserv" na descrição
                # Ou adicione aqui os códigos fixos que você sabe que são do Planserv:
                # if cod in ['7033', '7034', '7035', '7038', '7039']
            ]
        }
        # Se você quer APENAS os códigos que você listou anteriormente, use:
        # self.rubricas_planserv_para_analise['proventos_base'] = ['003P', '00P7', '04P6', '0J40', '0P42', '1J06']
        # self.rubricas_planserv_para_analise['descontos_planserv'] = ['7033', '7035', '7038', '7039', '7034']


    def analisar_resultados(self, resultados: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analisa os dados processados e retorna totais e detalhes do Planserv.
        
        Args:
            resultados: Dicionário com os dados processados do contracheque (consolidados de múltiplos meses).
            
        Returns:
            Dicionário formatado com totais e detalhes para o front-end.
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

        # Processa cada mês dentro dos dados consolidados
        for mes_ano, dados_mes in resultados['dados_mensais'].items():
            # Soma proventos que formam a base do Planserv
            if isinstance(dados_mes.get('rubricas'), dict):
                for codigo, valor in dados_mes['rubricas'].items():
                    if codigo in self.rubricas_planserv_para_analise['proventos_base'] and isinstance(valor, (int, float)):
                        # Verifica se a rubrica já foi detalhada para evitar duplicidade em resultados de múltiplos meses
                        # ou apenas acumula se a intenção é a soma total
                        if not any(d['codigo'] == codigo for d in totais['proventos_base']['detalhes']):
                            detalhes_existentes = {d['codigo']: d for d in totais['proventos_base']['detalhes']}
                            detalhes_existentes[codigo] = {
                                'codigo': codigo,
                                'descricao': self.rubricas_de_origem.get('proventos', {}).get(codigo, {}).get('descricao', 'Desconhecido'),
                                'valor': detalhes_existentes.get(codigo, {'valor': 0.0})['valor'] + valor
                            }
                            totais['proventos_base']['detalhes'] = list(detalhes_existentes.values())
                        else:
                            # Se já existe, atualiza o valor
                            for item in totais['proventos_base']['detalhes']:
                                if item['codigo'] == codigo:
                                    item['valor'] += valor
                                    break
                        totais['proventos_base']['total'] += valor
            
            # Soma descontos específicos do Planserv
            if isinstance(dados_mes.get('rubricas_detalhadas'), dict):
                for codigo, valor in dados_mes['rubricas_detalhadas'].items():
                    if codigo in self.rubricas_planserv_para_analise['descontos_planserv'] and isinstance(valor, (int, float)):
                        if not any(d['codigo'] == codigo for d in totais['descontos_planserv']['detalhes']):
                            detalhes_existentes = {d['codigo']: d for d in totais['descontos_planserv']['detalhes']}
                            detalhes_existentes[codigo] = {
                                'codigo': codigo,
                                'descricao': self.rubricas_de_origem.get('descontos', {}).get(codigo, {}).get('descricao', 'Desconhecido'),
                                'valor': detalhes_existentes.get(codigo, {'valor': 0.0})['valor'] + valor
                            }
                            totais['descontos_planserv']['detalhes'] = list(detalhes_existentes.values())
                        else:
                             for item in totais['descontos_planserv']['detalhes']:
                                if item['codigo'] == codigo:
                                    item['valor'] += valor
                                    break
                        totais['descontos_planserv']['total'] += valor

        return {
            'proventos': {
                'total': round(totais['proventos_base']['total'], 2),
                'detalhes': sorted([d for d in totais['proventos_base']['detalhes'] if d['valor'] > 0], key=lambda x: x['valor'], reverse=True)
            },
            'descontos': {
                'total': round(totais['descontos_planserv']['total'], 2),
                'detalhes': sorted([d for d in totais['descontos_planserv']['detalhes'] if d['valor'] > 0], key=lambda x: x['valor'], reverse=True)
            },
            'tabela': resultados.get('tabela', 'Desconhecida')
        }
