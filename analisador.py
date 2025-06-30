import json
import logging
from processador_contracheque import ProcessadorContracheque

logger = logging.getLogger(__name__)

class AnalisadorPlanserv: # Renomeado de AnalisadorDescontos para AnalisadorPlanserv
    def __init__(self):
        self.processador = ProcessadorContracheque()
        # As rubricas_detalhadas já vêm do processador, mas precisamos das rubricas de proventos também
        self.rubricas_completas = self.processador.rubricas_completas
        self.rubricas_de_origem = self.processador.rubricas # Dicionário completo de rubricas por tipo

        # Rubricas específicas do Planserv que queremos somar, carregadas dinamicamente
        # Considera que as rubricas do Planserv no JSON estão sob os tipos 'proventos' e 'descontos'
        # E que o campo 'deve incidir PLANSERV' no PDF indica quais rubricas somar.
        # Para a soma, vamos considerar as rubricas com "SIM" e "INATIVOS" do PDF.
        # As rubricas de proventos são todas as que não estão marcadas como desconto no JSON.
        
        # Vamos coletar todas as rubricas que devem incidir no Planserv (SIM ou INATIVOS)
        # e que estejam marcadas como 'Vantagens' no seu PDF (que correspondem a 'proventos' no JSON)
        # e também as rubricas de 'descontos' (que no PDF são marcadas como 'desconto' e 'SIM' ou 'INATIVOS').

        self.rubricas_planserv = {
            'proventos': [],
            'descontos': []
        }

        # Carrega as rubricas de proventos que são especificamente para o cálculo do Planserv
        # Baseado no PDF, as rubricas com 'deve incidir PLANSERV' como 'SIM' ou 'INATIVOS'
        # e que são do tipo 'Vantagens' no PDF são consideradas proventos para a base de cálculo.
        # No seu rubricas.json, todas as entradas em 'proventos' são consideradas vantagens.

        # Coleta as rubricas de desconto do Planserv diretamente do JSON
        # No seu rubricas.json, os descontos do Planserv são as rubricas dentro de "descontos"
        self.rubricas_planserv['descontos'] = list(self.rubricas_de_origem.get('descontos', {}).keys())

        # No PDF, as rubricas que incidem no Planserv estão nas últimas duas tabelas.
        # Pelo que vi, você quer somar proventos (vencimentos, etc.) E descontos do Planserv.
        # O processador já separa rubricas em 'rubricas' (proventos) e 'rubricas_detalhadas' (descontos).
        # A lógica de soma já parece estar correta em `calcular_totais` se `self.rubricas_planserv`
        # for preenchida com os códigos das rubricas do Planserv.

        # Para as rubricas de proventos do Planserv, usaremos o que já está na seção 'proventos' do JSON
        # que são consideradas as "Vantagens" que compõem a base de cálculo.
        self.rubricas_planserv['proventos'] = list(self.rubricas_de_origem.get('proventos', {}).keys())
        
        # Filtrar as rubricas do Planserv baseadas na coluna "deve incidir PLANSERV" do PDF
        # Essa parte exigiria uma lógica de extração mais robusta do PDF para mapear essa coluna.
        # Por simplicidade e dado o `rubricas.json` atual, assumimos que:
        # - Todos os itens em `rubricas['proventos']` são "Vantagens" que podem compor a base.
        # - Todos os itens em `rubricas['descontos']` são "Descontos" do Planserv.
        # O código atual de `calcular_totais` já faz essa diferenciação.
        # Portanto, `self.rubricas_planserv` deve listar *todas* as rubricas que você quer somar
        # especificamente para o Planserv.
        # Se você quiser SOMAR apenas as que incidem no Planserv, como na Tabela da página 17 do PDF,
        # precisaríamos de uma forma de carregar essa informação ou incluí-la no `rubricas.json`.
        
        # Como o objetivo é "somar proventos e descontos", e o Processador já os separa,
        # vamos garantir que `calcular_totais` itere sobre essas listas.
        # A `self.rubricas_planserv` será usada para filtrar quais rubricas *dentro* do resultado
        # devem ser somadas.

        # Para a função `calcular_totais` funcionar como esperado, `self.rubricas_planserv`
        # precisa conter as rubricas que *realmente* representam proventos e descontos do Planserv.
        # Se `rubricas.json` já contém isso, basta usá-las.
        # Vamos assumir que todas as rubricas em `rubricas.json` são relevantes para essa soma.

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

        # Inicializa as rubricas com zero para todos os proventos e descontos conhecidos
        for cod in self.rubricas_de_origem['proventos'].keys():
            totais['proventos']['rubricas'][cod] = 0.0
        for cod in self.rubricas_de_origem['descontos'].keys():
            totais['descontos']['rubricas'][cod] = 0.0

        # Soma os valores por mês
        for mes_ano, dados_mes in resultados['dados_mensais'].items():
            # Proventos
            if 'rubricas' in dados_mes: # 'rubricas' no processador armazena proventos
                for cod, valor in dados_mes['rubricas'].items():
                    # Verifica se a rubrica é um provento conhecido no rubricas.json
                    if cod in self.rubricas_de_origem['proventos']:
                        totais['proventos']['rubricas'][cod] += valor
                        totais['proventos']['total'] += valor
            
            # Descontos
            if 'rubricas_detalhadas' in dados_mes: # 'rubricas_detalhadas' no processador armazena descontos
                for cod, valor in dados_mes['rubricas_detalhadas'].items():
                    # Verifica se a rubrica é um desconto conhecido no rubricas.json
                    if cod in self.rubricas_de_origem['descontos']:
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
