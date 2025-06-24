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
        texto_upper = texto.upper()
        for tipo, config in self.config.get('padroes_contracheque', {}).items():
            for identificador in config.get('identificadores', []):
                if identificador.upper() in texto_upper:
                    return tipo
        return "desconhecido"

    def _extrair_valor_de_linha(self, linha):
        # Padrão Robusto para encontrar o último número na linha que parece dinheiro
        padrao_valor = r'(\d{1,3}(?:[\s\.]?\d{3})*(?:[.,]\d{2}))'
        matches = re.findall(padrao_valor, linha)
        
        if not matches:
            return 0.0

        valor_str = matches[-1].replace(' ', '')
        
        # Lógica inteligente para limpar o número (lida com "." e "," de forma segura)
        if ',' in valor_str and '.' in valor_str:
            valor_limpo = valor_str.replace('.', '').replace(',', '.')
        else:
            valor_limpo = valor_str.replace(',', '.')
        
        try:
            return float(valor_limpo)
        except (ValueError, TypeError):
            logger.warning(f"Não foi possível converter a string de valor '{valor_str}' para float.")
            return 0.0

    def extrair_dados(self, texto, tipo):
        """
        Função aprimorada para extrair tanto proventos quanto descontos.
        Retorna um dicionário contendo ambos.
        """
        if tipo == "desconhecido":
            return {'proventos': {}, 'descontos': {}}

        campos_desconto_config = self._get_campos_config(tipo)
        mapa_codigo_para_nome = {v: k for k, v in campos_desconto_config.items()}
        
        dados = {'proventos': {}, 'descontos': {}}
        linhas = texto.split('\n')
        secao_atual = 'proventos'

        for i, linha in enumerate(linhas):
            linha_strip = linha.strip()
            
            if "DESCONTOS" in linha_strip.upper():
                secao_atual = 'descontos'
                continue

            codigo_match = re.match(r'^\/?\s*([A-Z0-9]{4})\b', linha_strip)
            if codigo_match:
                codigo = codigo_match.group(1)
                
                valor = self._extrair_valor_de_linha(linha_strip)
                
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
        return self.config.get('padroes_contracheque', {}).get(tipo, {}).get('campos', {})

