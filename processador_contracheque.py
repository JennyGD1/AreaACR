# processador_contracheque.py (VERSÃO FINAL E APRIMORADA)

import json
import re
import logging

logger = logging.getLogger(__name__)

class ProcessadorContracheque:

    def __init__(self, config_path='config.json'):
        try:
            # Garante que o arquivo seja lido com a codificação correta
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            logger.error(f"Arquivo de configuração {config_path} não encontrado")
            self.config = {"padroes_contracheque": {}}
        except json.JSONDecodeError:
            logger.error(f"Erro ao decodificar o arquivo de configuração {config_path}")
            self.config = {"padroes_contracheque": {}}
    
    def identificar_tipo(self, texto):
        texto_upper = texto.upper()
        for tipo, config in self.config.get('padroes_contracheque', {}).items():
            for identificador in config.get('identificadores', []):
                if identificador.upper() in texto_upper:
                    return tipo
        return "desconhecido"

    def _extrair_valor_de_linha(self, linha):
        # Esta função foi aprimorada para lidar com formatos de número inconsistentes (ex: 1.234,56 e 1,234.56)
        padrao_valor = r'(\d{1,3}(?:[\s\.]?\d{3})*(?:[.,]\d{1,2})|\d+[.,]\d{1,2})'
        matches = re.findall(padrao_valor, linha)
        
        if not matches:
            return 0.0

        # Estamos interessados no último valor encontrado na linha
        valor_str = matches[-1]
        
        # Remove espaços
        valor_str = valor_str.replace(' ', '')
        
        # Lógica para identificar o separador decimal e de milhar
        last_dot = valor_str.rfind('.')
        last_comma = valor_str.rfind(',')
        
        # Heurística: se a vírgula aparece depois do último ponto, ela é o decimal (padrão BR/EU)
        if last_comma > last_dot:
            separador_milhar = '.'
            separador_decimal = ','
        # Senão, o ponto é o decimal (padrão US ou casos simples sem milhar)
        else:
            separador_milhar = ','
            separador_decimal = '.'

        # Limpa a string removendo o separador de milhar
        valor_limpo = valor_str.replace(separador_milhar, '')
        
        # Padroniza o separador decimal para o ponto que o Python entende
        valor_limpo = valor_limpo.replace(separador_decimal, '.')
        
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
        
        # Itera por cada linha do PDF
        for i, linha in enumerate(linhas):
            campo_alvo = None
            
            # Para cada linha, verifica se algum dos nossos padrões (código ou texto) está presente
            for campo_nome, padroes in campos_config.items():
                if not isinstance(padroes, list):
                    padroes = [padroes]
                
                for padrao in padroes:
                    if re.search(str(padrao), linha, re.IGNORECASE):
                        campo_alvo = campo_nome
                        break 
                if campo_alvo:
                    break
            
            # Se um campo foi identificado na linha, agora procuramos o valor
            if campo_alvo:
                valor_encontrado = self._extrair_valor_de_linha(linha)
                
                # Se não encontrou valor na mesma linha, procura nas 3 próximas
                if valor_encontrado == 0.0:
                    for offset in range(1, 4):
                        if i + offset < len(linhas):
                            valor_prox_linha = self._extrair_valor_de_linha(linhas[i + offset])
                            if valor_prox_linha > 0:
                                valor_encontrado = valor_prox_linha
                                logger.debug(f"Campo '{campo_alvo}': Padrão na linha {i}, valor {valor_encontrado} encontrado na linha +{offset}.")
                                break
                else:
                     logger.debug(f"Campo '{campo_alvo}': Valor {valor_encontrado} encontrado na mesma linha.")

                if valor_encontrado > 0:
                    dados[campo_alvo] = dados.get(campo_alvo, 0.0) + valor_encontrado

        logger.info(f"Dados extraídos para o tipo '{tipo}': {dados}")
        return dados
    
    def _get_campos_config(self, tipo):
        config = self.config['padroes_contracheque'].get(tipo, {})
        if 'herda' in config:
            base_config = self._get_campos_config(config['herda'])
            base_config.update(config.get('campos', {}))
            return base_config
        return config.get('campos', {})
