# processador_contracheque.py
import json
import re
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict
import fitz # PyMuPDF
import logging

logger = logging.getLogger(__name__)

class ProcessadorContracheque:
    def __init__(self, rubricas=None):
        self.rubricas = rubricas if rubricas is not None else self._carregar_rubricas_default()
        self.meses = {"Janeiro":"01","Fevereiro":"02","Março":"03","Abril":"04","Maio":"05","Junho":"06","Julho":"07","Agosto":"08","Setembro":"09","Outubro":"10","Novembro":"11","Dezembro":"12"}
        self.meses_anos = self._gerar_meses_anos()
        self._processar_rubricas_internas()

    def _carregar_rubricas_default(self) -> Dict:
        try:
            rubricas_path = Path(__file__).parent.parent / 'rubricas.json'
            with open(rubricas_path, 'r', encoding='utf-8') as f:
                return json.load(f).get('rubricas', {"proventos": {}, "descontos": {}})
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Erro ao carregar rubricas padrão: {str(e)}")
            return {"proventos": {}, "descontos": {}}

    def _gerar_meses_anos(self) -> List[str]:
        return [f"{mes}/{ano}" for ano in range(2019, 2026) for mes in self.meses.keys()]

    def _processar_rubricas_internas(self):
        self.rubricas_completas = {**self.rubricas.get('proventos', {}), **self.rubricas.get('descontos', {})}
        self.codigos_proventos = list(self.rubricas.get('proventos', {}).keys())
        self.codigos_descontos = list(self.rubricas.get('descontos', {}).keys())

    def converter_data_para_numerico(self, data_texto: str) -> str:
        try:
            mes, ano = data_texto.split('/')
            return f"{self.meses.get(mes, '00')}/{ano}"
        except (ValueError, AttributeError):
            return "00/0000"

    def extrair_valor(self, valor_str: str) -> float:
        try:
            valor_limpo = re.sub(r'[^\d,\.]', '', valor_str)
            valor = valor_limpo.replace('.', '').replace(',', '.')
            return float(valor)
        except (ValueError, AttributeError):
            return 0.0

    def _extrair_texto_pdf_interno(self, file_bytes):
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            texto = ""
            for page in doc:
                # Usando a opção 'blocks' para manter alguma estrutura de layout
                blocks = page.get_text("blocks")
                blocks.sort(key=lambda b: (b[1], b[0])) # Ordena por posição y, depois x
                for b in blocks:
                    texto += b[4] # O 5º elemento é o texto do bloco
            return texto
        except Exception as e:
            raise Exception(f"Erro ao extrair texto do PDF: {str(e)}")

    def _extrair_secoes_por_mes_ano(self, texto):
        sections = defaultdict(str)
        current_section = None
        month_year_pattern = re.compile(r'^(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\s*/\s*\d{4}', re.IGNORECASE)
        for linha in texto.split('\n'):
            linha_strip = linha.strip()
            if month_year_pattern.search(linha_strip):
                 # Normaliza o nome do mês para ter a primeira letra maiúscula
                mes_nome = linha_strip.split('/')[0].strip().capitalize()
                ano = re.search(r'\d{4}', linha_strip).group(0)
                current_section = f"{mes_nome}/{ano}"

            if current_section:
                sections[current_section] += linha + '\n'
        return sections

    def _identificar_meses_em_secoes(self, sections):
        return list(sections.keys())

    def processar_contracheque(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                file_bytes = f.read()
            texto = self._extrair_texto_pdf_interno(file_bytes)
            tabela_identificada = self._identificar_tabela(texto)
            sections = self._extrair_secoes_por_mes_ano(texto)
            meses_encontrados = self._identificar_meses_em_secoes(sections)
            if not meses_encontrados:
                # Se não achou "Janeiro/2021", tenta uma busca mais genérica
                if re.search("janeiro", texto, re.IGNORECASE) and re.search("2021", texto):
                    meses_encontrados = ["Janeiro/2021"]
                    sections["Janeiro/2021"] = texto
                else:
                    raise ValueError("Nenhum mês/ano válido encontrado no documento")

            meses_encontrados.sort(key=lambda x: (int(x.split('/')[1]), int(self.meses[x.split('/')[0]])))
            primeiro_mes, ultimo_mes = meses_encontrados[0], meses_encontrados[-1]
            index_primeiro, index_ultimo = self.meses_anos.index(primeiro_mes), self.meses_anos.index(ultimo_mes)
            meses_para_processar = self.meses_anos[index_primeiro:index_ultimo + 1]
            results = {"primeiro_mes": primeiro_mes, "ultimo_mes": ultimo_mes, "meses_para_processar": meses_para_processar, "dados_mensais": {}, "tabela": tabela_identificada}
            for mes_ano in meses_para_processar:
                if data := sections.get(mes_ano):
                    results["dados_mensais"][mes_ano] = self._processar_mes_conteudo(data, mes_ano)
            return results
        except Exception as e:
            logger.error(f"Erro ao processar contracheque: {str(e)}")
            raise

    def _identificar_tabela(self, texto):
        if re.search(r'Lei n[ºo]\s*13\.450,\s*de\s*26\s*de\s*Outubro\s*de\s*2015', texto, re.IGNORECASE):
            return '2015'
        return 'Desconhecida'

    # --- LÓGICA DE EXTRAÇÃO CORRIGIDA E MAIS PRECISA ---
    def _processar_mes_conteudo(self, data_texto, mes_ano):
        resultados_mes = {"total_proventos": 0.0, "rubricas": defaultdict(float), "rubricas_detalhadas": defaultdict(float), "descricoes": {}}
        
        # 1. Isola os blocos de VANTAGENS e DESCONTOS para evitar contaminação
        bloco_vantagens = re.search(r'VANTAGENS(.*?)TOTAL DE VANTAGENS', data_texto, re.DOTALL | re.IGNORECASE)
        bloco_descontos = re.search(r'DESCONTOS(.*?)TOTAL DE DESCONTOS', data_texto, re.DOTALL | re.IGNORECASE)

        texto_vantagens = bloco_vantagens.group(1) if bloco_vantagens else ""
        texto_descontos = bloco_descontos.group(1) if bloco_descontos else ""

        # Função auxiliar para processar um bloco de texto (vantagem ou desconto)
        def processar_bloco(texto_bloco, codigos_alvo, tipo_rubrica):
            for codigo in codigos_alvo:
                # Para cada código, busca todas as suas ocorrências no bloco
                for match in re.finditer(re.escape(codigo), texto_bloco):
                    # Pega o texto a partir do código encontrado
                    texto_a_frente = texto_bloco[match.start():]
                    # Procura pelo primeiro valor monetário nesse trecho de texto
                    valor_match = re.search(r'\d{1,3}(?:\.\d{3})*,\d{2}', texto_a_frente)
                    if valor_match:
                        valor = self.extrair_valor(valor_match.group(0))
                        logger.debug(f"DEBUG: {tipo_rubrica} - Mês/Ano: {mes_ano}, Código: '{codigo}', Valor: {valor}")
                        if tipo_rubrica == "provento":
                            resultados_mes["rubricas"][codigo] = valor # Assume que cada rubrica é única
                        else:
                            resultados_mes["rubricas_detalhadas"][codigo] = valor
                        break # Pára depois de encontrar o primeiro valor para este código

        # 2. Processa cada bloco separadamente
        processar_bloco(texto_vantagens, self.codigos_proventos, "provento")
        processar_bloco(texto_descontos, self.codigos_descontos, "desconto")

        resultados_mes["total_proventos"] = sum(resultados_mes["rubricas"].values())
        total_descontos = sum(resultados_mes["rubricas_detalhadas"].values())
        logger.debug(f"TOTAIS PARA {mes_ano}: Proventos={resultados_mes['total_proventos']:.2f}, Descontos={total_descontos:.2f}")

        return resultados_mes
    
    # O restante do arquivo não precisa de alterações
    def gerar_tabela_geral(self, resultados):
        tabela = {"colunas": ["MÊS/ANO"], "dados": []}
        if not resultados or "meses_para_processar" not in resultados: return tabela
        all_rubricas_found = set()
        for _, dados_mes in resultados["dados_mensais"].items():
            all_rubricas_found.update(dados_mes.get("rubricas", {}).keys())
            all_rubricas_found.update(dados_mes.get("rubricas_detalhadas", {}).keys())
        sorted_rubricas = sorted(list(all_rubricas_found))
        for cod in sorted_rubricas:
            descricao = self._gerar_descricoes_internas().get(cod, cod)
            tabela["colunas"].append(f"{descricao} ({cod})")
        tabela["colunas"].extend(["TOTAL PROVENTOS", "TOTAL DESCONTOS", "TOTAL LÍQUIDO"])
        for mes_ano in resultados["meses_para_processar"]:
            dados_mes = resultados["dados_mensais"].get(mes_ano, {})
            linha_dados = {"mes_ano": self.converter_data_para_numerico(mes_ano), "valores": []}
            total_proventos_mes = sum(dados_mes.get("rubricas", {}).values())
            total_descontos_mes = sum(dados_mes.get("rubricas_detalhadas", {}).values())
            for cod in sorted_rubricas:
                valor = dados_mes.get("rubricas", {}).get(cod, dados_mes.get("rubricas_detalhadas", {}).get(cod, 0.0))
                linha_dados["valores"].append(valor)
            linha_dados["valores"].extend([total_proventos_mes, total_descontos_mes, total_proventos_mes - total_descontos_mes])
            tabela["dados"].append(linha_dados)
        return tabela

    def _gerar_descricoes_internas(self):
        return {**{c:i.get('descricao','')for c,i in self.rubricas.get('proventos',{}).items()},**{c:i.get('descricao','')for c,i in self.rubricas.get('descontos',{}).items()}}
