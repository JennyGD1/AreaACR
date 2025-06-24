# app.py - VERSÃO ATUALIZADA PARA REPLICAR JAVASCRIPT

import fitz
import re
import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from datetime import datetime
from processador_contracheque import ProcessadorContracheque
# O AnalisadorDescontos não é mais necessário aqui, a lógica foi centralizada
import logging
from logging.handlers import RotatingFileHandler
from collections import OrderedDict

app = Flask(__name__)
app.secret_key = 'sua-chave-secreta-aqui'

# Configuração do logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('app.log', maxBytes=100000, backupCount=3),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Dicionário de meses para ordenação e conversão
MESES_ORDEM = {
    'Janeiro': 1, 'Fevereiro': 2, 'Março': 3, 'Abril': 4,
    'Maio': 5, 'Junho': 6, 'Julho': 7, 'Agosto': 8,
    'Setembro': 9, 'Outubro': 10, 'Novembro': 11, 'Dezembro': 12
}
MESES_NUM_PARA_NOME = {v: k for k, v in MESES_ORDEM.items()}


# Configurações do app
UPLOAD_FOLDER = '/tmp/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config.update({
    'UPLOAD_FOLDER': UPLOAD_FOLDER,
    'MAX_CONTENT_LENGTH': 100 * 1024 * 1024,
    'ALLOWED_EXTENSIONS': {'pdf'},
})

# Instância do nosso especialista
processador = ProcessadorContracheque('config.json')

# --- FUNÇÕES AUXILIARES ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extrair_mes_ano_do_texto(texto_pagina):
    padrao_mes_ano = r'(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\s*[/.-]?\s*(\d{4})'
    match = re.search(padrao_mes_ano, texto_pagina, re.IGNORECASE)
    if match:
        mes_nome = match.group(1).capitalize()
        ano = match.group(2)
        return f"{mes_nome}/{ano}"
    logger.warning("Mês/Ano não encontrado no texto da página.")
    return "Período não identificado"

def processar_pdf(caminho_pdf):
    try:
        doc = fitz.open(caminho_pdf)
        resultados_por_pagina = []
        for page_num, page in enumerate(doc):
            texto_pagina = page.get_text("text")
            mes_ano_encontrado = extrair_mes_ano_do_texto(texto_pagina)
            if mes_ano_encontrado != "Período não identificado":
                # Adicionado filtro para pegar apenas o período mais recente na página
                linhas = texto_pagina.split('\n')
                periodos_na_pagina = re.findall(r'\b\d{2}\.\d{4}\b', texto_pagina)
                if periodos_na_pagina:
                    periodos_na_pagina.sort(key=lambda p: (int(p[3:]), int(p[:2])), reverse=True)
                    periodo_recente = periodos_na_pagina[0]
                    
                    texto_filtrado = []
                    for linha in linhas:
                        if periodo_recente in linha or not re.search(r'\b\d{2}\.\d{4}\b', linha):
                             texto_filtrado.append(linha)
                    texto_pagina = "\n".join(texto_filtrado)

                tipo_contracheque = processador.identificar_tipo(texto_pagina)
                dados_extraidos = processador.extrair_dados(texto_pagina, tipo_contracheque)
                resultados_por_pagina.append((mes_ano_encontrado, dados_extraidos))
        return resultados_por_pagina
    except Exception as e:
        logger.error(f"Erro ao processar PDF {caminho_pdf}: {str(e)}", exc_info=True)
        return []

# --- ROTAS DA APLICAÇÃO ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calculadora')
def calculadora_index():
    session.clear()
    return render_template('indexcalculadora.html')

@app.route('/upload', methods=['POST'])
def upload():
    # ... (o código de upload pode permanecer o mesmo até a parte de salvar na sessão)
    if 'files' not in request.files:
        flash('Nenhum arquivo selecionado')
        return redirect(url_for('calculadora_index'))
    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        flash('Nenhum arquivo selecionado')
        return redirect(url_for('calculadora_index'))

    # Usamos um dicionário simples para armazenar os dados extraídos por Mês/Ano
    resultados_finais = {}
    erros = []

    for file in files:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        try:
            file.save(filepath)
            resultados_pagina = processar_pdf(filepath)
            for mes_ano_str, dados_mes in resultados_pagina:
                if mes_ano_str != "Período não identificado":
                    # Se já existe uma entrada para este mês, não sobrescreva.
                    # A primeira extração (geralmente do contracheque principal) é a que vale.
                    if mes_ano_str not in resultados_finais:
                        resultados_finais[mes_ano_str] = dados_mes
        except Exception as e:
            logger.error(f"Erro no upload do arquivo {filename}: {e}", exc_info=True)
            erros.append(filename)
        finally:
            if os.path.exists(filepath):
                try: os.remove(filepath)
                except OSError as re_err: logger.error(f"Erro ao remover {filepath}: {re_err}")
    
    if not resultados_finais:
        flash('Nenhum dado válido pôde ser extraído dos arquivos PDF fornecidos.', 'warning')
        return redirect(url_for('calculadora_index'))

    # Salva os resultados processados na sessão
    session['resultados_finais'] = resultados_finais
    if erros: flash(f'Processamento concluído com erros em: {", ".join(erros)}', 'warning')
    return redirect(url_for('mostrar_analise_detalhada'))


@app.route('/analise')
def mostrar_analise_detalhada():
    if 'resultados_finais' not in session:
        return redirect(url_for('calculadora_index'))
    
    resultados_finais = session.get('resultados_finais', {})
    if not resultados_finais:
        return redirect(url_for('calculadora_index'))

    # 1. Encontrar o primeiro e último mês com dados
    def chave_de_ordenacao(mes_ano_str):
        mes_nome, ano = mes_ano_str.split('/')
        return int(ano) * 100 + MESES_ORDEM.get(mes_nome, 0)

    meses_encontrados_ordenados = sorted(resultados_finais.keys(), key=chave_de_ordenacao)
    
    primeiro_mes_str = meses_encontrados_ordenados[0]
    ultimo_mes_str = meses_encontrados_ordenados[-1]

    # 2. Gerar a lista completa de meses no intervalo
    meses_para_processar = []
    mes_atual, ano_atual = primeiro_mes_str.split('/')
    num_mes_atual = MESES_ORDEM[mes_atual]
    num_ano_atual = int(ano_atual)

    while True:
        meses_para_processar.append(f"{MESES_NUM_PARA_NOME[num_mes_atual]}/{num_ano_atual}")
        if MESES_NUM_PARA_NOME[num_mes_atual] == ultimo_mes_str.split('/')[0] and str(num_ano_atual) == ultimo_mes_str.split('/')[1]:
            break
        num_mes_atual += 1
        if num_mes_atual > 12:
            num_mes_atual = 1
            num_ano_atual += 1
            
    # 3. Montar a estrutura de dados final para a tabela
    dados_tabela = []
    colunas_ativas = set(['total_proventos']) # 'total_proventos' sempre será uma coluna

    for mes_ano in meses_para_processar:
        dados_mes = resultados_finais.get(mes_ano)
        
        comp_dict = {'competencia': mes_ano.replace("/", "/\n")} # Adiciona quebra de linha para display
        
        if dados_mes:
            comp_dict['total_proventos'] = dados_mes.get('total_proventos', 0.0)
            descontos = dados_mes.get('descontos', {})
            comp_dict.update(descontos)
            
            # Atualiza o conjunto de colunas ativas
            for chave, valor in descontos.items():
                if valor > 0:
                    colunas_ativas.add(chave)
        else:
            # Se o mês não foi encontrado nos dados, preenche com 0
            comp_dict['total_proventos'] = 0.0

        dados_tabela.append(comp_dict)

    # 4. Ordenar as colunas e definir as descrições
    ordem_desejada = ["total_proventos", "titular", "conjuge", "agregado_jovem", "agregado_maior", "dependente", "plano_especial", "coparticipacao", "parcela_risco_titular", "parcela_risco_conjuge", "parcela_risco_agregado", "parcela_risco_dependente", "restituicao", "retroativo"]
    
    colunas_ordenadas = [chave for chave in ordem_desejada if chave in colunas_ativas]

    descricao_rubricas = {
        'total_proventos': 'TOTAL PROVENTOS', 'titular': 'TITULAR', 'conjuge': 'CONJUGE', 
        'dependente': 'DEPEND.', 'agregado_jovem': 'AGREG. JOVEM', 
        'agregado_maior': 'AGREG. MAIOR', 'plano_especial': 'ESPECIAL', 
        'coparticipacao': 'COPART.', 'retroativo': 'RETROATIVO', 'restituicao': 'RESTITUIÇÃO',
        'parcela_risco_titular': 'PARC. RISCO TITUL', 'parcela_risco_dependente': 'PARC. RISCO DEPEND',
        'parcela_risco_conjuge': 'PARC. RISCO CONJUG', 'parcela_risco_agregado': 'PARC. RISCO AGREG'
    }
    
    return render_template('analise_detalhada.html', 
                           dados_tabela=dados_tabela,
                           colunas_ordenadas=colunas_ordenadas,
                           descricao_rubricas=descricao_rubricas)


if __name__ == '__main__':
    app.run(debug=True)
