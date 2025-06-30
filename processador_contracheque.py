import json
import re
from pathlib import Path
from typing import Dict, List
from collections import defaultdict
import fitz # PyMuPDF

class ProcessadorContracheque:
    def __init__(self, rubricas=None):
        """Inicializa o processador com as rubricas fornecidas ou carrega do arquivo padrão"""
        # Carrega rubricas
        self.rubricas = self._carregar_rubricas(rubricas)
        
        # Dados auxiliares
        self.meses = {
            "Janeiro": "01", "Fevereiro": "02", "Março": "03", "Abril": "04",
            "Maio": "05", "Junho": "06", "Julho": "07", "Agosto": "08",
            "Setembro": "09", "Outubro": "10", "Novembro": "11", "Dezembro": "12"
        }
        
        self.meses_anos = self._gerar_meses_anos()
        self._processar_rubricas()

    def _carregar_rubricas(self, rubricas) -> Dict:
        """Carrega as rubricas do parâmetro ou do arquivo padrão"""
        if rubricas is not None:
            return rubricas
        
        try:
            # Caminho corrigido para rubricas.json
            rubricas_path = Path(__file__).parent.parent / 'rubricas.json'
            with open(rubricas_path, 'r', encoding='utf-8') as f:
                return json.load(f).get('rubricas', {"proventos": {}, "descontos": {}})
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Erro ao carregar rubricas: {str(e)}")
            return {"proventos": {}, "descontos": {}}

    def _gerar_meses_anos(self) -> List[str]:
        """Gera a lista de meses/anos (2019-2025)"""
        return [
            f"{mes}/{ano}" 
            for ano in range(2019, 2026) 
            for mes in self.meses.keys()
        ]

    def _processar_rubricas(self):
        """Prepara as estruturas de dados das rubricas"""
        self.rubricas_completas = {
            **self.rubricas.get('proventos', {}), 
            **self.rubricas.get('descontos', {})
        }
        self.codigos_proventos = list(self.rubricas.get('proventos', {}).keys())
        self.rubricas_detalhadas = self.rubricas.get('descontos', {}) # Mantido como 'descontos' para a lógica existente

    def converter_data_para_numerico(self, data_texto: str) -> str:
        """Converte data no formato 'Mês/Ano' para 'MM/AAAA'"""
        try:
            mes, ano = data_texto.split('/')
            return f"{self.meses.get(mes, '00')}/{ano}"
        except (ValueError, AttributeError):
            return "00/0000"

    def extrair_valor(self, linha: str) -> float:
        """Extrai valor monetário de uma string"""
        padrao = r'(\d{1,3}(?:\.\d{3})*,\d{2})'
        match = re.search(padrao, linha)
        if match:
            try:
                valor = match.group(1).replace('.', '').replace(',', '.')
                return float(valor)
            except (ValueError, AttributeError):
                return 0.0
        return 0.0

    def processar_pdf(self, file_bytes):
        """Processa o conteúdo PDF e retorna os resultados formatados"""
        try:
            if not hasattr(self, 'rubricas_completas'):
                raise ValueError("Rubricas não foram carregadas corretamente")
            
            texto = self._extrair_texto_pdf(file_bytes)
            sections = self._extrair_secoes(texto)
            meses_encontrados = self._identificar_meses(sections)
            
            if not meses_encontrados:
                raise ValueError("Nenhum mês/ano válido encontrado no documento")
            
            # Ordena os meses encontrados
            meses_encontrados.sort(key=lambda x: (
                int(x.split('/')[1]) * 100 + int(self.meses[x.split('/')[0]])
            ))
            
            primeiro_mes = meses_encontrados[0]
            ultimo_mes = meses_encontrados[-1]
            
            index_primeiro = self.meses_anos.index(primeiro_mes)
            index_ultimo = self.meses_anos.index(ultimo_mes)
            meses_para_processar = self.meses_anos[index_primeiro:index_ultimo + 1]
            
            results = {
                "primeiro_mes": primeiro_mes,
                "ultimo_mes": ultimo_mes,
                "meses_para_processar": meses_para_processar,
                "dados_mensais": {}
            }
            
            for mes_ano in meses_para_processar:
                data = sections.get(mes_ano, "")
                if data:
                    results["dados_mensais"][mes_ano] = self.processar_mes(data, mes_ano)
            
            return results
            
        except Exception as e:
            raise Exception(f"Erro ao processar PDF: {str(e)}")

    def processar_contracheque(self, filepath):
        """Processa um arquivo PDF de contracheque e retorna dados estruturados"""
        try:
            with open(filepath, 'rb') as f:
                file_bytes = f.read()
            
            # Extrai texto do PDF
            texto = self._extrair_texto_pdf(file_bytes)
            
            # Identifica a tabela (A, B ou C) - nova funcionalidade
            tabela = self._identificar_tabela(texto)
            
            # Processa os dados normalmente
            # Os dados mensais são preenchidos por processar_pdf, que chama processar_mes
            results = self.processar_pdf(file_bytes)
            results['tabela'] = tabela # Adiciona informação da tabela
            
            return results
            
        except Exception as e:
            raise Exception(f"Erro ao processar contracheque: {str(e)}")

    def _identificar_tabela(self, texto):
        """Identifica a qual tabela (A, B ou C) pertence o contracheque"""
        # Padrões para identificar cada tabela
        # Usando expressões regulares para flexibilidade e ignorando case
        padrao_tabela_a = re.compile(r'Tabela\s*A', re.IGNORECASE)
        padrao_tabela_b = re.compile(r'Tabela\s*B', re.IGNORECASE)
        padrao_tabela_c = re.compile(r'Tabela\s*C', re.IGNORECASE)
        
        if padrao_tabela_a.search(texto):
            return 'A'
        elif padrao_tabela_b.search(texto):
            return 'B'
        elif padrao_tabela_c.search(texto):
            return 'C'
        else:
            # Em 2015, o anexo I não era chamado de Tabela A explicitamente.
            # No entanto, a estrutura do documento sugere que ele pode ser o "padrão" inicial.
            # Poderíamos tentar identificar o ano ou conteúdo específico.
            # Por enquanto, se nenhuma tabela explícita for encontrada, podemos tentar inferir
            # baseando-nos em um padrão de texto ou deixar como desconhecida.
            # Se o texto contiver "Lei nº 13.450, de 26 de Outubro de 2015", pode ser um indício.
            if re.search(r'Lei n[ºo]\s*13\.450,\s*de\s*26\s*de\s*Outubro\s*de\s*2015', texto, re.IGNORECASE):
                return '2015' # Representando a tabela da Lei 13.450
            return 'Desconhecida'


    def gerar_totais(self, resultados):
        """Gera totais mensais e anuais organizados por tabela"""
        totais = {
            'mensais': defaultdict(lambda: defaultdict(float)),
            'anuais': defaultdict(lambda: defaultdict(float)),
            'geral': defaultdict(float)
        }
        
        if not resultados or 'dados_mensais' not in resultados:
            return totais
        
        tabela = resultados.get('tabela', 'Desconhecida')
        
        for mes_ano, dados in resultados['dados_mensais'].items():
            ano = mes_ano.split('/')[1]
            
            # Processa proventos
            for rubrica, valor in dados.get('rubricas', {}).items():
                totais['mensais'][mes_ano][rubrica] += valor
                totais['anuais'][ano][rubrica] += valor
                totais['geral'][rubrica] += valor
            
            # Processa descontos
            for rubrica, valor in dados.get('rubricas_detalhadas', {}).items():
                totais['mensais'][mes_ano][rubrica] += valor
                totais['anuais'][ano][rubrica] += valor
                totais['geral'][rubrica] += valor
        
        return {
            'tabela': tabela,
            'totais': totais,
            'descricoes': self._gerar_descricoes()
        }

    def _gerar_descricoes(self):
        """Gera dicionário com descrições de todas as rubricas"""
        return {
            **{cod: info.get('descricao', '') 
               for cod, info in self.rubricas.get('proventos', {}).items()},
            **{cod: info.get('descricao', '') 
               for cod, info in self.rubricas.get('descontos', {}).items()}
        }

    def _extrair_secoes(self, texto):
        """Extrai seções do texto por mês/ano"""
        sections = defaultdict(str)
        current_section = None
        
        # Padrão para identificar "Mês/Ano" (ex: Janeiro/2023)
        # Garante que seja o nome completo do mês e 4 dígitos para o ano.
        month_year_pattern = re.compile(r'^(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\/\d{4}$')
        
        lines = texto.split('\n')
        
        for i, linha in enumerate(lines):
            linha = linha.strip()
            if not linha:
                continue
                
            # Verifica se é um cabeçalho de mês/ano
            if month_year_pattern.match(linha):
                current_section = linha
            elif current_section:
                sections[current_section] += linha + '\n'
        
        return sections

    def _identificar_meses(self, sections):
        """Identifica os meses presentes no texto"""
        meses_validos = []
        for cabecalho in sections.keys():
            partes = cabecalho.split('/')
            if len(partes) == 2 and partes[0] in self.meses and partes[1].isdigit():
                meses_validos.append(cabecalho)
        return list(set(meses_validos)) # Remove duplicatas

    def _extrair_texto_pdf(self, file_bytes):
        """Extrai texto do PDF usando PyMuPDF, garantindo processamento de múltiplas páginas"""
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            texto = ""
            for page in doc:
                # Extrai texto com layout preservado para melhor identificação de tabelas
                texto += page.get_text("text", flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE)
                texto += "\n--- PAGE BREAK ---\n" # Marcador para separar páginas
            return texto
        except Exception as e:
            raise Exception(f"Erro ao extrair texto do PDF: {str(e)}")

    def processar_mes(self, data_texto, mes_ano):
        """Processa os dados de um mês específico"""
        lines = [line.strip() for line in data_texto.split('\n') if line.strip()]
        
        # Dicionário para armazenar os resultados
        resultados_mes = {
            "total_proventos": 0.0,
            "rubricas": defaultdict(float), # Armazena proventos
            "rubricas_detalhadas": defaultdict(float), # Armazena descontos
            "descricoes": {} # Descrições serão preenchidas na camada de análise/apresentação
        }

        # Padrão para identificar rubricas (código da rubrica)
        # O padrão agora é mais flexível para incluir 4 dígitos, 3 dígitos + letra, ou letra + 3 dígitos
        padrao_rubrica = re.compile(r'^((\d{4})|(\d{3}[A-Za-z])|([A-Za-z]\d{3}))\s+.*(\d{1,3}(?:\.\d{3})*,\d{2})$')


        for line in lines:
            # Verifica se a linha contém uma rubrica conhecida e um valor monetário
            match = padrao_rubrica.match(line)
            if match:
                rubrica_codigo = match.group(1).strip() # O código da rubrica é o primeiro grupo
                valor_str = match.group(5) # O valor é o quinto grupo capturado
                valor = self.extrair_valor(valor_str) # Reutiliza a função extrair_valor

                print(f"DEBUG: Mês/Ano: {mes_ano}, Linha: '{line}'")
                print(f"DEBUG: Rubrica encontrada: '{rubrica_codigo}', Valor: {valor}")
                
                # Classifica como provento ou desconto
                if rubrica_codigo in self.codigos_proventos:
                    resultados_mes["total_proventos"] += valor
                    resultados_mes["rubricas"][rubrica_codigo] += valor
                elif rubrica_codigo in self.rubricas_detalhadas: # verifica se é um código de desconto
                    resultados_mes["rubricas_detalhadas"][rubrica_codigo] += valor
        
        # As descrições devem ser acessadas do `self.rubricas` (o dicionário completo de rubricas)
        # e não calculadas aqui para cada mês, pois são estáticas.
        # result['descricoes'] será preenchida na função `gerar_totais` ou `analisar_resultados`.
        return resultados_mes
        
    def gerar_tabela_geral(self, resultados):
        """Gera uma tabela consolidada com os resultados"""
        tabela = {
            "colunas": ["MÊS/ANO"],
            "dados": []
        }
        
        if not resultados or "meses_para_processar" not in resultados:
            return tabela
        
        # Coleta todas as rubricas que apareceram nos dados mensais
        all_rubricas_found = set()
        for mes_ano, dados_mes in resultados["dados_mensais"].items():
            all_rubricas_found.update(dados_mes.get("rubricas", {}).keys())
            all_rubricas_found.update(dados_mes.get("rubricas_detalhadas", {}).keys())
        
        # Ordena as rubricas para garantir uma ordem consistente nas colunas
        sorted_rubricas = sorted(list(all_rubricas_found))

        # Adiciona colunas para proventos e descontos que foram encontrados
        for cod in sorted_rubricas:
            descricao = self._gerar_descricoes().get(cod, cod) # Use a descrição ou o código
            tabela["colunas"].append(f"{descricao} ({cod})")
        
        # Adiciona colunas para totais
        tabela["colunas"].append("TOTAL PROVENTOS")
        tabela["colunas"].append("TOTAL DESCONTOS")
        tabela["colunas"].append("TOTAL LÍQUIDO") # Adicionar total líquido

        # Preenche os dados
        for mes_ano in resultados["meses_para_processar"]:
            dados_mes = resultados["dados_mensais"].get(mes_ano, {})
            linha_dados = {
                "mes_ano": self.converter_data_para_numerico(mes_ano),
                "valores": []
            }
            
            total_proventos_mes = 0.0
            total_descontos_mes = 0.0

            # Preenche os valores para as rubricas encontradas
            for cod in sorted_rubricas:
                valor_provento = dados_mes.get("rubricas", {}).get(cod, 0.0)
                valor_desconto = dados_mes.get("rubricas_detalhadas", {}).get(cod, 0.0)
                
                # Se uma rubrica for tanto provento quanto desconto, decide como apresentar.
                # Para simplificar, vou adicionar o valor, mas em um cenário real, talvez queira separar.
                if cod in self.rubricas.get('proventos', {}):
                    linha_dados["valores"].append(valor_provento)
                    total_proventos_mes += valor_provento
                elif cod in self.rubricas.get('descontos', {}):
                    linha_dados["valores"].append(valor_desconto)
                    total_descontos_mes += valor_desconto
                else:
                    linha_dados["valores"].append(0.0) # Se não for nem provento nem desconto mapeado

            # Adiciona os totais no final da linha
            linha_dados["valores"].append(total_proventos_mes)
            linha_dados["valores"].append(total_descontos_mes)
            linha_dados["valores"].append(total_proventos_mes - total_descontos_mes) # Total líquido
            
            tabela["dados"].append(linha_dados)
            
        return tabela
