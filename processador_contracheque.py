import re
from collections import defaultdict
import fitz  # PyMuPDF

class ProcessadorContracheque:
    def __init__(self):
        self.meses = {
            "Janeiro": "01", "Fevereiro": "02", "Março": "03", "Abril": "04",
            "Maio": "05", "Junho": "06", "Julho": "07", "Agosto": "08",
            "Setembro": "09", "Outubro": "10", "Novembro": "11", "Dezembro": "12"
        }
        
        # Lista de meses/anos (2019-2025)
        self.meses_anos = []
        for ano in range(2019, 2026):
            for mes in self.meses.keys():
                self.meses_anos.append(f"{mes}/{ano}")

       
        # Lista apenas com códigos de proventos
        self.codigos_proventos = [cod for cod, det in self.rubricas_completas.items() 
                                if det['tipo'] == 'provento']
        
        # Dicionário apenas com rubricas detalhadas (descontos)
        self.rubricas_detalhadas = {cod: det for cod, det in self.rubricas_completas.items() 
                                  if det['tipo'] == 'desconto'}
        
        
    def converter_data_para_numerico(self, data_texto):  # ← Corrigido (4 espaços)
        mes, ano = data_texto.split('/')
        return f"{self.meses[mes]}/{ano}"

    def extrair_valor(self, linha):  # ← Removida linha em branco extra
        padrao = r'(\d{1,3}(?:\.\d{3})*,\d{2})'
        match = re.search(padrao, linha)
        if match:
            valor = match.group(1).replace('.', '').replace(',', '.')
            try:
                return float(valor)
            except ValueError:
                return 0.0
        return 0.0

    def processar_pdf(self, file_bytes):
        """Processa o conteúdo PDF e retorna os resultados formatados"""
        try:
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
            
            resultados = {
                "primeiro_mes": primeiro_mes,
                "ultimo_mes": ultimo_mes,
                "meses_para_processar": meses_para_processar,
                "dados_mensais": {}
            }
            
            for mes_ano in meses_para_processar:
                data = sections.get(mes_ano, "")
                if data:
                    resultados["dados_mensais"][mes_ano] = self.processar_mes(data, mes_ano)
            
            return resultados
            
        except Exception as e:
            raise Exception(f"Erro ao processar PDF: {str(e)}")

    def _extrair_secoes(self, texto):
        """Extrai seções do texto por mês/ano"""
        sections = defaultdict(str)
        current_section = None
        
        # Padrão para identificar cabeçalhos de seção (Mês/Ano)
        padrao_secao = re.compile(r'^(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\/(\d{4})')
        
        for linha in texto.split('\n'):
            match = padrao_secao.search(linha)
            if match:
                current_section = f"{match.group(1)}/{match.group(2)}"
            elif current_section:
                sections[current_section] += linha + '\n'
        
        return sections

    def _identificar_meses(self, sections):
        """Identifica os meses presentes no texto"""
        meses_encontrados = []
        padrao_mes = re.compile(r'^(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\/(\d{4})')
        
        for linha in sections.keys():
            match = padrao_mes.search(linha)
            if match:
                mes_ano = f"{match.group(1)}/{match.group(2)}"
                if mes_ano in self.meses_anos:
                    meses_encontrados.append(mes_ano)
        
        return list(set(meses_encontrados))  # Remove duplicates

    def _extrair_texto_pdf(self, file_bytes):
        """Extrai texto do PDF usando PyMuPDF"""
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        texto = ""
        for page in doc:
            texto += page.get_text()
        return texto

    def processar_mes(self, data_texto, mes_ano):
        lines = data_texto.split('\n')
        
        # Passo 1: Identificar o ano mais recente
        ano_mais_recente = ''
        periodo_mais_recente = ''
        
        for line in lines:
            periodo_match = re.search(r'(\d{2})\.(\d{4})', line)
            if periodo_match:
                mes = periodo_match.group(1)
                ano = periodo_match.group(2)
                
                if not ano_mais_recente or ano > ano_mais_recente:
                    ano_mais_recente = ano
                
                if ano == ano_mais_recente and (not periodo_mais_recente or mes > periodo_mais_recente.split('.')[0]):
                    periodo_mais_recente = f"{mes}.{ano}"
        
        # Passo 2: Filtrar rubricas do período mais recente
        rubricas_filtradas = [
            line for line in lines 
            if periodo_mais_recente and re.search(fr'{periodo_mais_recente}', line)
        ]
        
        # Passo 3: Calcular totais
        totais = {
            "total_proventos": 0,
            "rubricas": defaultdict(float),
            "rubricas_detalhadas": defaultdict(float)
        }
        
        for line in rubricas_filtradas:
            # Verifica se é uma rubrica de provento
            if len(line) >= 4:
                rubrica = line[:4]
                if rubrica in self.codigos_proventos:
                    valor = self.extrair_valor(line)
                    totais["total_proventos"] += valor
                    totais["rubricas"][rubrica] += valor
            
            # Verifica rubricas detalhadas (7033, 7035, etc.)
            for cod, desc in self.rubricas_detalhadas.items():
                if cod in line:
                    valor = self.extrair_valor(line)
                    totais["rubricas_detalhadas"][cod] += valor
        
        return totais

    def gerar_tabela_geral(self, resultados):
        tabela = {
            "colunas": ["MÊS/ANO"],
            "dados": []
        }
        
        if not resultados or "meses_para_processar" not in resultados:
            return tabela
        
        # Verifica quais colunas têm dados
        colunas_com_dados = {cod: False for cod in self.rubricas_detalhadas}
        
        for mes_ano in resultados["meses_para_processar"]:
            dados_mes = resultados["dados_mensais"].get(mes_ano, {})
            for cod in colunas_com_dados:
                if dados_mes.get("rubricas_detalhadas", {}).get(cod, 0) > 0:
                    colunas_com_dados[cod] = True
        
        # Adiciona colunas que têm dados
        for cod, tem_dados in colunas_com_dados.items():
            if tem_dados:
                tabela["colunas"].append(self.rubricas_detalhadas[cod])
        
        # Preenche os dados
        for mes_ano in resultados["meses_para_processar"]:
            dados_mes = resultados["dados_mensais"].get(mes_ano, {})
            linha = {
                "mes_ano": self.converter_data_para_numerico(mes_ano),
                "valores": []
            }
            
            for cod, tem_dados in colunas_com_dados.items():
                if tem_dados:
                    valor = dados_mes.get("rubricas_detalhadas", {}).get(cod, 0)
                    linha["valores"].append(valor)
            
            tabela["dados"].append(linha)
        
        return tabela
