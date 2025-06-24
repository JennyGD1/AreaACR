import json
import re
import logging

logger = logging.getLogger(__name__)

class ProcessadorContracheque:

    def __init__(self, config_path='config.json'):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            # Carrega a lista de códigos de proventos e a converte para um set para busca rápida
            self.codigos_proventos = set(self.config.get('codigos_proventos', []))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Erro ao carregar ou processar o config.json: {e}")
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
        # Padrão Robusto para encontrar o último número na linha que parece dinheiro
        padrao_valor = r'(\d{1,3}(?:[\s\.]?\d{3})*(?:[.,]\d{2}))'
        matches = re.findall(padrao_valor, linha)
        
        if not matches:
            return 0.0

        valor_str = matches[-1].replace(' ', '')
        
        # Lógica inteligente para limpar o número
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
        Função aprimorada para extrair tanto proventos quanto descontos,
        e calcular o total de proventos com base na lista do config.json.
        """
        if tipo == "desconhecido":
            return {'proventos': {}, 'descontos': {}, 'total_proventos': 0.0}

        campos_desconto_config = self._get_campos_config(tipo)
        mapa_codigo_para_nome = {v: k for k, v in campos_desconto_config.items()}
        
        dados = {'proventos': {}, 'descontos': {}, 'total_proventos': 0.0}
        linhas = texto.split('\n')
        
        # Identifica o início das seções de proventos e descontos para maior precisão
        indice_descontos = -1
        for i, linha in enumerate(linhas):
            if "DESCONTOS" in linha.upper():
                indice_descontos = i
                break
        
        # Processa Proventos
        linhas_proventos = linhas[:indice_descontos] if indice_descontos != -1 else linhas
        total_proventos_calculado = 0.0
        for linha in linhas_proventos:
            linha_strip = linha.strip()
            # *** MUDANÇA AQUI: Regex simplificada para pegar os 4 primeiros caracteres não-espaço ***
            codigo_match = re.match(r'^(\S{4})', linha_strip)
            if codigo_match:
                codigo = codigo_match.group(1)
                
                # Adiciona o provento ao dicionário de proventos (para cálculo de contribuição, se necessário)
                valor = self._extrair_valor_de_linha(linha_strip)
                if valor > 0:
                    dados['proventos'][codigo] = valor
                
                # Se o código estiver na lista de proventos, soma ao total
                if codigo in self.codigos_proventos:
                    total_proventos_calculado += valor
        
        dados['total_proventos'] = total_proventos_calculado

        # Processa Descontos
        if indice_descontos != -1:
            linhas_descontos = linhas[indice_descontos:]
            for linha in linhas_descontos:
                linha_strip = linha.strip()
                # *** MUDANÇA AQUI: Regex simplificada também para descontos ***
                codigo_match = re.match(r'^(\S{4})', linha_strip)
                if codigo_match:
                    codigo = codigo_match.group(1)
                    nome_interno = mapa_codigo_para_nome.get(codigo)
                    if nome_interno:
                        valor = self._extrair_valor_de_linha(linha_strip)
                        if valor > 0:
                            dados['descontos'][nome_interno] = dados['descontos'].get(nome_interno, 0) + valor
        
        logger.info(f"Dados extraídos: Total Proventos={dados['total_proventos']:.2f}, Descontos={len(dados['descontos'])}")
        return dados
    
    def _get_campos_config(self, tipo):
        return self.config.get('padroes_contracheque', {}).get(tipo, {}).get('campos', {})
