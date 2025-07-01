# processador_contracheque.py
import json
import re
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict # <--- 1. CORREÇÃO: IMPORT ADICIONADO
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
                texto += page.get_text("text", flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE)
                texto += "\n--- PAGE BREAK ---\n"
            return texto
        except Exception as e:
            raise Exception(f"Erro ao extrair texto do PDF: {str(e)}")

    def _extrair_secoes_por_mes_ano(self, texto):
        sections = defaultdict(str)
        current_section = None
        month_year_pattern = re.compile(r'^(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\/\d{4}$')
        for linha in texto.split('\n'):
            linha_strip = linha.strip()
            if month_year_pattern.match(linha_strip):
                current_section = linha_strip
            elif current_section:
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

    # --- 2. CORREÇÃO: LÓGICA DE EXTRAÇÃO TOTALMENTE REFEITA ---
    def _processar_mes_conteudo(self, data_texto, mes_ano):
        """
        Processa o conteúdo de texto de um mês para extrair proventos e descontos.
        Esta nova versão é mais robusta e não depende da formatação linha a linha.
        """
        resultados_mes = {"total_proventos": 0.0, "rubricas": defaultdict(float), "rubricas_detalhadas": defaultdict(float), "descricoes": {}}
        
        # Cria uma expressão regular para encontrar QUALQUER um dos nossos códigos de rubrica.
        todos_codigos = self.codigos_proventos + self.codigos_descontos
        # O 're.escape' garante que caracteres especiais nos códigos não quebrem a regex.
        padrao_codigos = r'(' + '|'.join(re.escape(c) for c in todos_codigos) + r')'
        
        # Encontra a posição de todos os códigos no texto.
        matches_codigos = list(re.finditer(padrao_codigos, data_texto))
        
        # Encontra a posição de todos os valores monetários no texto.
        padrao_valor = r'\d{1,3}(?:\.\d{3})*,\d{2}'
        matches_valores = list(re.finditer(padrao_valor, data_texto))

        # Associa cada código ao valor monetário mais próximo DEPOIS dele.
        i_valor = 0
        for match_codigo in matches_codigos:
            codigo = match_codigo.group(1)
            pos_codigo = match_codigo.end()

            # Procura o próximo valor que aparece depois do código
            while i_valor < len(matches_valores) and matches_valores[i_valor].start() < pos_codigo:
                i_valor += 1
            
            if i_valor < len(matches_valores):
                valor_str = matches_valores[i_valor].group(0)
                valor = self.extrair_valor(valor_str)
                
                logger.debug(f"DEBUG: Mês/Ano: {mes_ano}, Código: '{codigo}', Valor Encontrado: {valor}")

                if codigo in self.codigos_proventos:
                    resultados_mes["rubricas"][codigo] += valor
                elif codigo in self.codigos_descontos:
                    resultados_mes["rubricas_detalhadas"][codigo] += valor
                
                i_valor += 1 # Move para o próximo valor para não ser usado de novo

        resultados_mes["total_proventos"] = sum(resultados_mes["rubricas"].values())
        total_descontos = sum(resultados_mes["rubricas_detalhadas"].values())
        logger.debug(f"TOTAIS PARA {mes_ano}: Proventos={resultados_mes['total_proventos']:.2f}, Descontos={total_descontos:.2f}")

        return resultados_mes
        
    # Os métodos abaixo não precisam de alteração.
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
            total_proventos_mes = 0.0
            total_descontos_mes = 0.0
            for cod in sorted_rubricas:
                valor_provento = dados_mes.get("rubricas", {}).get(cod, 0.0)
                valor_desconto = dados_mes.get("rubricas_detalhadas", {}).get(cod, 0.0)
                if cod in self.rubricas.get('proventos', {}):
                    linha_dados["valores"].append(valor_provento)
                    total_proventos_mes += valor_provento
                elif cod in self.rubricas.get('descontos', {}):
                    linha_dados["valores"].append(valor_desconto)
                    total_descontos_mes += valor_desconto
                else:
                    linha_dados["valores"].append(0.0)
            linha_dados["valores"].extend([total_proventos_mes, total_descontos_mes, total_proventos_mes - total_descontos_mes])
            tabela["dados"].append(linha_dados)
        return tabela

    def _gerar_descricoes_internas(self):
        return {**{c:i.get('descricao','')for c,i in self.rubricas.get('proventos',{}).items()},**{c:i.get('descricao','')for c,i in self.rubricas.get('descontos',{}).items()}}
