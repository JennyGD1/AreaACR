import json
import re
import logging

logger = logging.getLogger(__name__)

class ProcessadorContracheque:

    def __init__(self, config_path='config.json'):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Erro ao carregar ou processar o config.json: {e}")
            self.config = {"padroes_contracheque": {}}
    
    def identificar_tipo(self, texto):
        texto_upper = texto.upper()
        for tipo, config in self.config.get('padroes_contracheque', {}).items():
            for identificador in config.get('identificadores', []):
                if identificador.upper() in texto_upper:
                    return tipo
        return "desconhecido"

    def _extrair_valor_de_linha(self, linha):
        """
        Função ajustada para extrair valores monetários com precisão.
        Busca exclusivamente por números no formato brasileiro (ex: 1.234,56),
        ignorando outros formatos para evitar confusão com matrículas.
        """
        # Padrão único e restrito: Procura por números com vírgula e duas casas decimais.
        padrao_monetario_br = r'(\d{1,3}(?:\.\d{3})*,\d{2}\b)'
        matches = re.findall(padrao_monetario_br, linha)

        if not matches:
            return 0.0

        # Pega o último valor encontrado na linha.
        valor_str = matches[-1]
        
        # Limpeza para converter para o formato float do Python:
        # 1. Remove os pontos de milhar.
        # 2. Troca a vírgula decimal por um ponto.
        valor_limpo = valor_str.replace('.', '').replace(',', '.')
        
        try:
            return float(valor_limpo)
        except (ValueError, TypeError):
            logger.warning(f"Não foi possível converter a string de valor '{valor_str}' para float.")
            return 0.0

    def extrair_dados(self, texto, tipo):
        if tipo == "desconhecido":
            return {}

        campos_config = self._get_campos_config(tipo)
        dados = {}
        linhas = texto.split('\n')
        
        for i, linha in enumerate(linhas):
            linha_strip = linha.strip()
            if not linha_strip:
                continue

            for campo_nome, padroes in campos_config.items():
                if not isinstance(padroes, list):
                    padroes = [padroes]
                
                for padrao in padroes:
                    if re.search(re.escape(str(padrao)), linha, re.IGNORECASE):
                        
                        valor_encontrado = self._extrair_valor_de_linha(linha_strip)
                        
                        if valor_encontrado == 0.0:
                            for offset in range(1, 4):
                                if i + offset < len(linhas):
                                    valor_prox_linha = self._extrair_valor_de_linha(linhas[i + offset])
                                    if valor_prox_linha > 0:
                                        valor_encontrado = valor_prox_linha
                                        logger.debug(f"Campo '{campo_nome}': Padrão '{padrao}' na linha {i}, valor {valor_encontrado} encontrado na linha +{offset}.")
                                        break
                        else:
                             logger.debug(f"Campo '{campo_nome}': Padrão '{padrao}', valor {valor_encontrado} encontrado na mesma linha.")

                        if valor_encontrado > 0:
                            dados[campo_nome] = dados.get(campo_nome, 0.0) + valor_encontrado
                            break 
            
        logger.info(f"Dados extraídos para o tipo '{tipo}': {dados}")
        return dados
    
    def _get_campos_config(self, tipo):
        config = self.config['padroes_contracheque'].get(tipo, {})
        if 'herda' in config:
            base_config = self._get_campos_config(config['herda'])
            base_config.update(config.get('campos', {}))
            return base_config
        return config.get('campos', {})
