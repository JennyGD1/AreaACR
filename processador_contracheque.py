import json
import re
from pathlib import Path
from typing import Dict, Any, List, DefaultDict
from collections import defaultdict
import fitz  # PyMuPDF
import logging

logger = logging.getLogger(__name__)

class ProcessadorContracheque:
    def __init__(self, rubricas=None):
        """Inicializa o processador de contracheques com as rubricas definidas"""
        self.rubricas = rubricas if rubricas is not None else self._carregar_rubricas_default()
        self.meses = {
            "Janeiro": "01", "Fevereiro": "02", "Março": "03",
            "Abril": "04", "Maio": "05", "Junho": "06",
            "Julho": "07", "Agosto": "08", "Setembro": "09",
            "Outubro": "10", "Novembro": "11", "Dezembro": "12"
        }
        self.meses_anos = self._gerar_meses_anos()
        self._processar_rubricas_internas()

    def _carregar_rubricas_default(self) -> Dict[str, Dict[str, Dict]]:
        """Carrega as rubricas padrão do arquivo rubricas.json"""
        try:
            rubricas_path = Path(__file__).parent.parent / 'rubricas.json'
            with open(rubricas_path, 'r', encoding='utf-8') as f:
                return json.load(f).get('rubricas', {"proventos": {}, "descontos": {}})
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Erro ao carregar rubricas padrão: {str(e)}")
            return {"proventos": {}, "descontos": {}}

    def _gerar_meses_anos(self) -> List[str]:
        """Gera a lista de meses/anos no formato 'Mês/Ano' de 2019 a 2025"""
        return [f"{mes}/{ano}" for ano in range(2019, 2026) for mes in self.meses.keys()]

    def _processar_rubricas_internas(self):
        """Prepara listas de códigos de proventos e descontos para processamento rápido"""
        self.codigos_proventos = list(self.rubricas.get('proventos', {}).keys())
        self.codigos_descontos = list(self.rubricas.get('descontos', {}).keys())

    def extrair_valor(self, valor_str: str) -> float:
        """Converte uma string de valor (ex: '1.234,56') para float (1234.56)"""
        try:
            # Remove caracteres não numéricos exceto vírgula e substitui separadores
            valor_limpo = re.sub(r'[^\d,]', '', valor_str.replace('.', '').replace(',', '.'))
            return float(valor_limpo)
        except (ValueError, AttributeError):
            logger.warning(f"Valor inválido encontrado: {valor_str}")
            return 0.0

    def _extrair_secoes_por_mes_ano(self, doc: fitz.Document) -> Dict[str, List[str]]:
        """Extrai seções do PDF agrupadas por mês/ano"""
        sections = defaultdict(list)
        month_year_pattern = re.compile(
            r'(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\s*[/\s]*(\d{4})',
            re.IGNORECASE
        )
        
        for page in doc:
            texto_pagina = page.get_text("text", sort=True)
            matches = list(month_year_pattern.finditer(texto_pagina))
            
            if matches:
                for match in matches:
                    mes = match.group(1).capitalize()
                    ano = match.group(2)
                    mes_ano_chave = f"{mes}/{ano}"
                    sections[mes_ano_chave].append(texto_pagina)
            else:
                # Fallback para páginas sem identificação de mês/ano
                sections["Desconhecido"].append(texto_pagina)
                logger.warning(f"Página {page.number} não contém identificação de mês/ano")
        
        return sections

    def _extrair_bloco(self, texto: str, inicio: str, fim: str) -> str:
        """Extrai um bloco de texto entre os marcadores de início e fim"""
        padrao = re.compile(
            rf'{re.escape(inicio)}(.*?){re.escape(fim)}',
            re.DOTALL | re.IGNORECASE
        )
        match = padrao.search(texto)
        return match.group(1).strip() if match else ""

    def _processar_bloco_rubricas(self, texto_bloco: str, codigos_alvo: List[str]) -> DefaultDict[str, float]:
        """Processa um bloco de texto (VANTAGENS ou DESCONTOS) extraindo rubricas e valores"""
        resultados = defaultdict(float)
        
        # Padrão para capturar código seguido de valor na mesma linha
        padrao_rubrica = re.compile(
            r'^\s*([A-Z0-9/]+)\b.*?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})\s*$',
            re.MULTILINE
        )
        
        for match in padrao_rubrica.finditer(texto_bloco):
            codigo, valor_str = match.groups()
            if codigo in codigos_alvo:
                valor = self.extrair_valor(valor_str)
                resultados[codigo] += valor
                logger.debug(f"Rubrica encontrada: {codigo} = {valor:.2f}")
            else:
                logger.debug(f"Código não mapeado encontrado: {codigo} (valor: {valor_str})")
        
        return resultados

    def _processar_conteudo_mes(self, texto_secao: str, mes_ano: str) -> Dict[str, DefaultDict[str, float]]:
        """Processa o conteúdo de um mês específico, extraindo VANTAGENS e DESCONTOS"""
        resultados_mes = {
            "rubricas": defaultdict(float),
            "rubricas_detalhadas": defaultdict(float)
        }

        # Extrair blocos de VANTAGENS e DESCONTOS
        bloco_vantagens = self._extrair_bloco(texto_secao, 'VANTAGENS', 'TOTAL DE VANTAGENS')
        bloco_descontos = self._extrair_bloco(texto_secao, 'DESCONTOS', 'TOTAL DE DESCONTOS')

        # Processar cada bloco separadamente
        if bloco_vantagens:
            resultados_mes["rubricas"].update(
                self._processar_bloco_rubricas(bloco_vantagens, self.codigos_proventos)
            )
        
        if bloco_descontos:
            resultados_mes["rubricas_detalhadas"].update(
                self._processar_bloco_rubricas(bloco_descontos, self.codigos_descontos)
            )
        
        return resultados_mes

    def processar_contracheque(self, filepath: str) -> Dict[str, Any]:
        """Processa um arquivo de contracheque PDF e retorna os dados estruturados"""
        try:
            logger.info(f"Iniciando processamento do arquivo: {filepath}")
            
            with open(filepath, 'rb') as f:
                file_bytes = f.read()

            doc = fitz.open(stream=file_bytes, filetype="pdf")
            secoes = self._extrair_secoes_por_mes_ano(doc)
            
            resultados_finais = {"dados_mensais": {}}

            for mes_ano, textos_pagina in secoes.items():
                dados_mensais_agregados = {
                    "rubricas": defaultdict(float),
                    "rubricas_detalhadas": defaultdict(float)
                }
                
                for texto_secao in textos_pagina:
                    dados_pagina = self._processar_conteudo_mes(texto_secao, mes_ano)
                    for cod, val in dados_pagina["rubricas"].items():
                        dados_mensais_agregados["rubricas"][cod] += val
                    for cod, val in dados_pagina["rubricas_detalhadas"].items():
                        dados_mensais_agregados["rubricas_detalhadas"][cod] += val
                
                # Cálculo dos totais
                total_proventos = sum(
                    val for cod, val in dados_mensais_agregados["rubricas"].items()
                    if not self.rubricas.get('proventos', {}).get(cod, {}).get('ignorar_na_soma', False)
                )
                
                total_descontos = sum(dados_mensais_agregados["rubricas_detalhadas"].values())
                
                dados_mensais_agregados["total_proventos"] = total_proventos
                dados_mensais_agregados["total_descontos"] = total_descontos
                
                logger.info(
                    f"Totais para {mes_ano}: "
                    f"Proventos={total_proventos:.2f}, "
                    f"Descontos={total_descontos:.2f}"
                )
                
                resultados_finais["dados_mensais"][mes_ano] = dados_mensais_agregados

            # Ordenação dos meses processados
            meses_processados = sorted(
                resultados_finais['dados_mensais'].keys(),
                key=lambda m: (int(m.split('/')[1]), int(self.meses.get(m.split('/')[0], 0)))
            
            if meses_processados:
                resultados_finais['primeiro_mes'] = meses_processados[0]
                resultados_finais['ultimo_mes'] = meses_processados[-1]
                resultados_finais['meses_para_processar'] = meses_processados
            else:
                logger.warning("Nenhum mês foi processado com sucesso")
                resultados_finais['meses_para_processar'] = []

            return resultados_finais
        except Exception as e:
            logger.error(f"Erro ao processar contracheque {filepath}: {str(e)}", exc_info=True)
            raise

    def converter_data_para_numerico(self, data_texto: str) -> str:
        """Converte data no formato 'Mês/Ano' para 'MM/AAAA'"""
        try:
            mes, ano = data_texto.split('/')
            return f"{self.meses.get(mes, '00')}/{ano}"
        except (ValueError, AttributeError):
            return "00/0000"
        
    def gerar_tabela_proventos_resumida(self, resultados: Dict[str, Any]) -> Dict[str, Any]:
        """Gera tabela resumida de proventos por mês"""
        tabela = {
            "colunas": ["Mês/Ano", "Total de Proventos"],
            "dados": []
        }
        
        for mes_ano in resultados.get("meses_para_processar", []):
            dados_mes = resultados.get("dados_mensais", {}).get(mes_ano, {})
            total_proventos = dados_mes.get("total_proventos", 0.0)
            tabela["dados"].append({
                "mes_ano": self.converter_data_para_numerico(mes_ano),
                "total": total_proventos
            })
        
        return tabela

    def gerar_tabela_descontos_detalhada(self, resultados: Dict[str, Any]) -> Dict[str, Any]:
        """Gera tabela detalhada de descontos por mês"""
        descontos_de_origem = self.rubricas.get('descontos', {})
        
        # Coletar todos os códigos de descontos encontrados
        codigos_encontrados = set(
            cod for dados_mes in resultados.get("dados_mensais", {}).values()
            for cod in dados_mes.get("rubricas_detalhadas", {}).keys()
        )
        
        # Filtrar apenas os descontos do tipo 'planserv'
        codigos_para_exibir = sorted([
            cod for cod in codigos_encontrados
            if descontos_de_origem.get(cod, {}).get("tipo") == "planserv"
        ])
        
        # Preparar descrições para exibição
        descricoes = {
            cod: descontos_de_origem.get(cod, {}).get('descricao', cod) 
            for cod in codigos_para_exibir
        }
        
        # Construir estrutura da tabela
        tabela = {
            "colunas": ["Mês/Ano"] + [descricoes.get(cod, cod) for cod in codigos_para_exibir],
            "dados": []
        }
        
        # Preencher com os valores
        for mes_ano in resultados.get("meses_para_processar", []):
            linha = {
                "mes_ano": self.converter_data_para_numerico(mes_ano),
                "valores": []
            }
            
            rubricas_detalhadas_mes = resultados.get("dados_mensais", {}).get(mes_ano, {}).get("rubricas_detalhadas", {})
            
            for cod in codigos_para_exibir:
                linha["valores"].append(rubricas_detalhadas_mes.get(cod, 0.0))
            
            tabela["dados"].append(linha)
        
        return tabela
