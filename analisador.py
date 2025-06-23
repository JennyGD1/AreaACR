import json
import logging

logger = logging.getLogger(__name__)

class AnalisadorDescontos:

    def __init__(self, config_path='config.json'):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                # Carrega apenas a seção de regras de análise do config
                self.config = json.load(f).get('regras_analise', {})
            
            # Carrega as regras para dentro da classe para fácil acesso
            self.rubricas_unicas = self.config.get('rubricas_unicas', [])
            self.valores_referencia = self.config.get('valores_referencia', {})
            
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Erro ao carregar ou processar o config.json para análise: {e}")
            self.rubricas_unicas = []
            self.valores_referencia = {}

    def determinar_quantidade_pessoas(self, rubrica, valor):
        """
        Estima a quantidade de pessoas com base no valor de uma rubrica.
        Esta é a tradução da lógica do JavaScript.
        """
        try:
            valor_num = float(valor)
        except (ValueError, TypeError):
            return "N/A" # Retorna N/A se o valor não for numérico

        if rubrica in self.rubricas_unicas:
            return 1
        
        valores_ref = self.valores_referencia.get(str(rubrica))
        if not valores_ref:
            return 1

        # Lógica especial para '7034' (Dependentes) onde se busca múltiplos exatos
        if rubrica == "7034":
            for ref in valores_ref:
                # Usa uma pequena tolerância para comparações de float
                if abs(valor_num - ref) < 0.01:
                    return 1
                if ref > 0:
                    multiplicador = valor_num / ref
                    if abs(multiplicador - round(multiplicador)) < 0.01:
                        return int(round(multiplicador))
            return "X" # Indica valor não padrão

        # Lógica padrão: encontra o valor de referência mais próximo e calcula
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

    def analisar_resultados(self, resultados_por_ano):
        """
        Recebe os dados já extraídos e adiciona a camada de análise.
        """
        analise_completa = {}
        
        for ano, dados_ano in resultados_por_ano.items():
            analise_completa[ano] = dados_ano.copy()
            analise_completa[ano]['analise_descontos'] = {}

            # A estrutura agora é um dicionário, então usamos .items()
            todos_os_meses = dados_ano.get('detalhes_mensais', {})
            
            for mes, detalhe_mensal in todos_os_meses.items():
                valores = detalhe_mensal.get('valores', {})
                
                for rubrica, valor in valores.items():
                    if valor > 0:
                        if rubrica not in analise_completa[ano]['analise_descontos']:
                            analise_completa[ano]['analise_descontos'][rubrica] = {}
                        
                        quantidade = self.determinar_quantidade_pessoas(rubrica, valor)
                        
                        analise_completa[ano]['analise_descontos'][rubrica][mes] = {
                            'valor': valor,
                            'pessoas': quantidade
                        }

        return analise_completa
