# processador_contracheque.py (VERSÃO CORRIGIDA E MAIS ROBUSTA)

import json
import re
import logging

logger = logging.getLogger(__name__)

class ProcessadorContracheque:

    def __init__(self, config_path='config.json'):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self.codigos_proventos = set(self.config.get('codigos_proventos', []))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Erro crítico ao carregar config.json: {e}")
            self.config = {"padroes_contracheque": {}}
            self.codigos_proventos = set()
    
    def identificar_tipo(self, texto):
        texto_upper = texto.upper()
        for tipo, config in self.config.get('padroes_contracheque', {}).items():
            for identificador in config.get('identificadores', []):
                if identificador.upper() in texto_upper:
                    return tipo
        return "desconhecido"

    def _extrair_valor_de_linha(self, linha):
        """
        Regex mais estrita para o padrão de moeda brasileira (ex: 1.234,56).
        Isso evita a captura incorreta de outros números, como datas ou códigos.
        """
        padrao_valor = r'(\d{1,3}(?:\.?\d{3})*,\d{2})\b'
        matches = re.findall(padrao_valor, linha)
        
        if not matches:
            return 0.0

        valor_str = matches[-1]
        try:
            valor_limpo = valor_str.replace('.', '').replace(',', '.')
            return float(valor_limpo)
        except (ValueError, TypeError):
            logger.warning(f"Falha na conversão final da string '{valor_str}' para float.")
            return 0.0

    def extrair_dados(self, texto, tipo):
        if tipo == "desconhecido":
            return {'proventos': {}, 'descontos': {}, 'total_proventos': 0.0}

        campos_desconto_config = self._get_campos_config(tipo)
        mapa_codigo_para_nome = {v: k for k, v in campos_desconto_config.items()}
        
        dados = {'proventos': {}, 'descontos': {}, 'total_proventos': 0.0}
        linhas = texto.split('\n')
        
        indice_descontos = -1
        for i, linha in enumerate(linhas):
            if "DESCONTOS" in linha.upper():
                indice_descontos = i
                break
        
        # --- LÓGICA ROBUSTA PARA PROCESSAR LINHAS ---
        def processar_secao(linhas_secao, eh_desconto=False):
            total_secao = 0.0
            dados_secao = {}

            for linha in linhas_secao:
                # 1. A linha DEVE conter um valor monetário válido para ser processada.
                valor = self._extrair_valor_de_linha(linha)
                if valor == 0.0:
                    continue # Pula linhas sem valor (cabeçalhos, linhas vazias, etc.)

                # 2. Se encontrou valor, tenta extrair o código da rubrica.
                linha_strip = linha.strip()
                codigo_match = re.match(r'^(\S+)', linha_strip) # Pega o código no início
                
                if codigo_match:
                    codigo = codigo_match.group(1).strip()
                    
                    if eh_desconto:
                        nome_interno = mapa_codigo_para_nome.get(codigo)
                        if nome_interno:
                            dados_secao[nome_interno] = dados_secao.get(nome_interno, 0) + valor
                    else: # É provento
                        # Guarda o provento individualmente
                        dados_secao[codigo] = valor
                        # Se o código estiver na lista principal, soma ao total
                        if codigo in self.codigos_proventos:
                            total_secao += valor
            
            if eh_desconto:
                return dados_secao
            else:
                return dados_secao, total_secao

        # Processa Proventos
        linhas_proventos = linhas[:indice_descontos] if indice_descontos != -1 else linhas
        dados['proventos'], dados['total_proventos'] = processar_secao(linhas_proventos)

        # Processa Descontos
        if indice_descontos != -1:
            linhas_descontos = linhas[indice_descontos:]
            dados['descontos'] = processar_secao(linhas_descontos, eh_desconto=True)
        
        logger.info(f"Dados extraídos: Total Proventos={dados['total_proventos']:.2f}, Descontos={len(dados['descontos'])}")
        return dados
    
    def _get_campos_config(self, tipo):
        return self.config.get('padroes_contracheque', {}).get(tipo, {}).get('campos', {})
