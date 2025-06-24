# processador_contracheque.py (VERSÃO FINAL COM LEITURA DE PROVENTOS)

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
        # Esta função continua igual
        texto_upper = texto.upper()
        for tipo, config in self.config.get('padroes_contracheque', {}).items():
            for identificador in config.get('identificadores', []):
                if identificador.upper() in texto_upper:
                    return tipo
        return "desconhecido"

    def _extrair_valor_de_linha(self, linha):
        # Esta função foi aprimorada para buscar o formato com vírgula primeiro
        padrao_virgula = r'(\d{1,3}(?:\.\d{3})*,\d{2}\b)'
        matches = re.findall(padrao_virgula, linha)
        
        if not matches:
            padrao_geral = r'(\d{1,3}(?:[\.\s]?\d{3})*(?:[.,]\d{1,2}))'
            matches = re.findall(padrao_geral, linha)

        if not matches:
            return 0.0

        valor_str = matches[-1].replace(' ', '')
        valor_limpo = valor_str.replace('.', '').replace(',', '.') if ',' in valor_str else valor_str
        
        try:
            return float(valor_limpo)
        except (ValueError, TypeError):
            return 0.0

    def extrair_dados(self, texto, tipo):
        """
        Função aprimorada para extrair tanto proventos quanto descontos.
        Retorna um dicionário contendo ambos.
        """
        if tipo == "desconhecido":
            return {}

        campos_desconto_config = self._get_campos_config(tipo)
        mapa_codigo_para_nome = {v: k for k, v in campos_desconto_config.items()}
        
        dados = {'proventos': {}, 'descontos': {}}
        linhas = texto.split('\n')
        secao_atual = 'proventos'  # Começa lendo a seção de VANTAGENS

        for i, linha in enumerate(linhas):
            linha_strip = linha.strip()
            
            # Muda para a seção de descontos ao encontrar o cabeçalho
            if "TOTAL DE VANTAGENS" in linha or "DESCONTOS" in linha_strip.upper():
                secao_atual = 'descontos'
                continue

            codigo_match = re.match(r'^\/?\s*([A-Z0-9]{4})\b', linha_strip)
            if codigo_match:
                codigo = codigo_match.group(1)
                
                valor = self._extrair_valor_de_linha(linha_strip)
                if valor == 0.0 and i + 2 < len(linhas): # Procura até 2 linhas abaixo
                    valor = self._extrair_valor_de_linha(linhas[i+1]) or self._extrair_valor_de_linha(linhas[i+2])
                
                if valor > 0:
                    if secao_atual == 'descontos':
                        nome_interno = mapa_codigo_para_nome.get(codigo)
                        if nome_interno:
                            dados['descontos'][nome_interno] = valor
                    else: # Seção é 'proventos'
                        dados['proventos'][codigo] = valor
        
        logger.info(f"Dados extraídos: Proventos={len(dados['proventos'])}, Descontos={len(dados['descontos'])}")
        return dados
    
    def _get_campos_config(self, tipo):
        config = self.config['padroes_contracheque'].get(tipo, {})
        if 'herda' in config:
            base_config = self._get_campos_config(config['herda'])
            base_config.update(config.get('campos', {}))
            return base_config
        return config.get('campos', {})
