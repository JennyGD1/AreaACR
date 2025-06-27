import json
import logging
from processador_contracheque import ProcessadorContracheque

logger = logging.getLogger(__name__)

class AnalisadorDescontos:
    def __init__(self):
        self.processador = ProcessadorContracheque()
        self.rubricas_detalhadas = self.processador.rubricas_detalhadas
        
        # Configurações padrão
        self.rubricas_unicas = ['7033', '7035']  # Titular e Cônjuge são únicos
        self.valores_referencia = {
            '7034': [150.00],  # Dependente
            '7038': [100.00],   # Agregado Jovem
            '7039': [200.00],   # Agregado Maior
            '7040': [50.00]     # Coparticipação
        }

    def determinar_quantidade_pessoas(self, rubrica, valor):
        """
        Estima a quantidade de pessoas com base no valor de uma rubrica.
        """
        try:
            valor_num = float(valor)
        except (ValueError, TypeError):
            return "N/A"

        if rubrica in self.rubricas_unicas:
            return 1
        
        valores_ref = self.valores_referencia.get(rubrica)
        if not valores_ref:
            return 1

        if rubrica == "7034":  # Lógica especial para dependentes
            for ref in valores_ref:
                if abs(valor_num - ref) < 0.01:
                    return 1
                if ref > 0:
                    multiplicador = valor_num / ref
                    if abs(multiplicador - round(multiplicador)) < 0.01:
                        return int(round(multiplicador))
            return "X"

        menor_diferenca = float('inf')
        valor_ref_proximo = valores_ref[0]
        for ref in valores_ref:
            diferenca = abs(valor_num - ref)
            if diferenca < menor_diferenca:
                menor_diferenca = diferenca
                valor_ref_proximo = ref
        
        if valor_ref_proximo > 0:
            quantidade = round(valor_num / valor_ref_proximo)
            return int(quantidade if quantidade > 0 else 1)
        
        return 1

    def analisar_resultados(self, resultados):
        """
        Recebe os dados já extraídos e adiciona a camada de análise.
        """
        if not resultados or 'dados_mensais' not in resultados:
            return resultados

        analise_completa = resultados.copy()
        analise_completa['analise_descontos'] = {}

        for mes_ano, dados_mes in resultados['dados_mensais'].items():
            if 'rubricas_detalhadas' not in dados_mes:
                continue
                
            for rubrica, valor in dados_mes['rubricas_detalhadas'].items():
                if valor > 0:
                    if rubrica not in analise_completa['analise_descontos']:
                        analise_completa['analise_descontos'][rubrica] = {
                            'descricao': self.rubricas_detalhadas[rubrica]['descricao'],
                            'valores': {}
                        }
                    
                    quantidade = self.determinar_quantidade_pessoas(rubrica, valor)
                    
                    analise_completa['analise_descontos'][rubrica]['valores'][mes_ano] = {
                        'valor': valor,
                        'pessoas': quantidade
                    }

        return analise_completa
