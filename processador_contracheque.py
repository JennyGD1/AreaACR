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
                # Usar 'text' com a opção sort=True ajuda a manter uma ordem de leitura mais lógica
                texto += page.get_text("text", sort=True) + "\n"
            return texto
        except Exception as e:
            raise Exception(f"Erro ao extrair texto do PDF: {str(e)}")

    def _extrair_secoes_por_mes_ano(self, texto):
        sections = defaultdict(str)
        current_section = None
        # Padrão para encontrar "Mês/Ano" (ex: "Fevereiro/2020")
        month_year_pattern = re.compile(r'^(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\s*/\s*\d{4}', re.IGNORECASE)
        for linha in texto.split('\n'):
            linha_strip = linha.strip()
            match = month_year_pattern.search(linha_strip)
            if match:
                mes_nome = match.group(1).capitalize()
                ano = re.search(r'\d{4}', linha_strip).group(0)
                current_section = f"{mes_nome}/{ano}"

            if current_section:
                sections[current_section] += linha + '\n'

        # Fallback para casos onde o cabeçalho do mês não é bem formatado
        if not sections:
            for mes in self.meses.keys():
                if re.search(mes, texto, re.IGNORECASE) and re.search(r'\d{4}', texto):
                    ano = re.search(r'\d{4}', texto).group(0)
                    sections[f"{mes}/{ano}"] = texto
                    break
        return sections

    def _identificar_meses_em_secoes(self, sections):
        return list(sections.keys())

    def processar_contracheque(self, filepath):
        try:
            with open(filepath, 'rb') as f: file_bytes = f.read()
            texto = self._extrair_texto_pdf_interno(file_bytes)
            sections = self._extrair_secoes_por_mes_ano(texto)
            meses_encontrados = self._identificar_meses_em_secoes(sections)
            if not meses_encontrados: raise ValueError("Nenhum mês/ano válido pôde ser identificado no documento.")
            
            meses_encontrados.sort(key=lambda x: (int(x.split('/')[1]), int(self.meses.get(x.split('/')[0], 0))))
            primeiro_mes, ultimo_mes = meses_encontrados[0], meses_encontrados[-1]
            index_primeiro, index_ultimo = self.meses_anos.index(primeiro_mes), self.meses_anos.index(ultimo_mes)
            meses_para_processar = self.meses_anos[index_primeiro:index_ultimo + 1]
            
            results = {"primeiro_mes": primeiro_mes, "ultimo_mes": ultimo_mes, "meses_para_processar": meses_para_processar, "dados_mensais": {}}
            for mes_ano in meses_para_processar:
                if data := sections.get(mes_ano):
                    results["dados_mensais"][mes_ano] = self._processar_mes_conteudo(data, mes_ano)
            return results
        except Exception as e:
            logger.error(f"Erro ao processar contracheque: {str(e)}")
            raise

    def _processar_mes_conteudo(self, data_texto, mes_ano):
        resultados_mes = {"rubricas": defaultdict(float), "rubricas_detalhadas": defaultdict(float)}

        # Padrão de Expressão Regular APRIMORADO
        # Procura por uma linha que COMEÇA com um código (4 dígitos OU até 4 alfanuméricos com 'P' no final)
        padrao_rubrica = re.compile(
            r'^(?P<code>\d{4}|[A-Z0-9]{1,4}P|[A-Z]\d{3}|\d[A-Z]\d{2})\s+(?P<descricao>.*?)\s+(?P<valor>\d{1,3}(?:[.,]\d{3})*,\d{2})\s*$', 
            re.MULTILINE
        )

        bloco_vantagens_match = re.search(r'VANTAGENS(.*?)TOTAL DE VANTAGENS', data_texto, re.DOTALL | re.IGNORECASE)
        texto_vantagens = bloco_vantagens_match.group(1) if bloco_vantagens_match else ""
        
        bloco_descontos_match = re.search(r'DESCONTOS(.*?)TOTAL DE DESCONTOS', data_texto, re.DOTALL | re.IGNORECASE)
        texto_descontos = bloco_descontos_match.group(1) if bloco_descontos_match else ""

        for match in padrao_rubrica.finditer(texto_vantagens + texto_descontos):
            codigo = match.group('code')
            valor = self.extrair_valor(match.group('valor'))
            
            if codigo in self.codigos_proventos:
                resultados_mes["rubricas"][codigo] = valor
                logger.debug(f"DEBUG: Provento Identificado - Mês/Ano: {mes_ano}, Código: '{codigo}', Valor: {valor}")
            elif codigo in self.codigos_descontos:
                 resultados_mes["rubricas_detalhadas"][codigo] = valor
                 logger.debug(f"DEBUG: Desconto Identificado - Mês/Ano: {mes_ano}, Código: '{codigo}', Valor: {valor}")

        total_proventos_calculado = 0
        for codigo, valor in resultados_mes["rubricas"].items():
            info_rubrica = self.rubricas.get('proventos', {}).get(codigo, {})
            if not info_rubrica.get('ignorar_na_soma', False):
                total_proventos_calculado += valor
        
        resultados_mes["total_proventos"] = total_proventos_calculado
        
        logger.debug(f"TOTAIS PARA {mes_ano}: Proventos (para soma)={total_proventos_calculado:.2f}, Descontos={sum(resultados_mes['rubricas_detalhadas'].values()):.2f}")
        
        return resultados_mes

    # Os outros métodos (gerar_tabela_proventos_resumida, etc.) não precisam de alteração
    def gerar_tabela_proventos_resumida(self, resultados):
        tabela = {"colunas": ["Mês/Ano", "Total de Proventos"], "dados": []}
        for mes_ano in resultados.get("meses_para_processar", []):
            dados_mes = resultados.get("dados_mensais", {}).get(mes_ano, {})
            total_proventos = dados_mes.get("total_proventos", 0.0)
            tabela["dados"].append({"mes_ano": self.converter_data_para_numerico(mes_ano), "total": total_proventos})
        return tabela

    def gerar_tabela_descontos_detalhada(self, resultados):
        descontos_de_origem = self.rubricas.get('descontos', {})
        codigos_encontrados = set()
        for dados_mes in resultados.get("dados_mensais", {}).values():
            codigos_encontrados.update(dados_mes.get("rubricas_detalhadas", {}).keys())
        codigos_descontos_relevantes = sorted(list(codigos_encontrados))
        descricoes = {cod: descontos_de_origem.get(cod, {}).get('descricao', cod) for cod in codigos_descontos_relevantes}
        tabela = {"colunas": ["Mês/Ano"] + [descricoes[cod] for cod in codigos_descontos_relevantes], "dados": []}
        for mes_ano in resultados.get("meses_para_processar", []):
            linha = {"mes_ano": self.converter_data_para_numerico(mes_ano), "valores": []}
            rubricas_detalhadas_mes = resultados.get("dados_mensais", {}).get(mes_ano, {}).get("rubricas_detalhadas", {})
            for cod in codigos_descontos_relevantes:
                linha["valores"].append(rubricas_detalhadas_mes.get(cod, 0.0))
            tabela["dados"].append(linha)
        return tabela
