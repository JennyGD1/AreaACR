# app.py - VERSÃO FINAL E CORRIGIDA

import fitz
import re
import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from datetime import datetime
from processador_contracheque import ProcessadorContracheque
from analisador import AnalisadorDescontos
import logging
from logging.handlers import RotatingFileHandler

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

# Dicionário de meses para ordenação
MESES_ORDEM = {
    'Janeiro': 1, 'Fevereiro': 2, 'Março': 3, 'Abril': 4,
    'Maio': 5, 'Junho': 6, 'Julho': 7, 'Agosto': 8,
    'Setembro': 9, 'Outubro': 10, 'Novembro': 11, 'Dezembro': 12
}

# Configurações do app
UPLOAD_FOLDER = '/tmp/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config.update({
    'UPLOAD_FOLDER': UPLOAD_FOLDER,
    'MAX_CONTENT_LENGTH': 100 * 1024 * 1024,
    'ALLOWED_EXTENSIONS': {'pdf'},
})

# Instâncias dos nossos especialistas
processador = ProcessadorContracheque('config.json')
analisador = AnalisadorDescontos('config.json')

# --- FUNÇÕES AUXILIARES ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extrair_mes_ano_do_texto(texto_pagina):
    padrao_mes_ano = r'(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\s*[/.-]?\s*(\d{4})'
    match = re.search(padrao_mes_ano, texto_pagina, re.IGNORECASE)
    if match:
        mes_nome = match.group(1).capitalize()
        ano = match.group(2)
        return f"{mes_nome}/{ano}", ano
    logger.warning("Mês/Ano não encontrado no texto da página.")
    return "Período não identificado", None

def processar_pdf(caminho_pdf):
    try:
        doc = fitz.open(caminho_pdf)
        resultados_por_pagina = []
        campos_obrigatorios = [
            'titular', 'conjuge', 'dependente', 'agregado_jovem',
            'agregado_maior', 'plano_especial', 'coparticipacao',
            'retroativo', 'restituicao', 'parcela_risco_titular', 'parcela_risco_dependente',
            'parcela_risco_conjuge', 'parcela_risco_agregado'
        ]
        for page_num, page in enumerate(doc):
            texto_pagina = page.get_text("text")
            mes_ano_encontrado, _ = extrair_mes_ano_do_texto(texto_pagina)
            tipo_contracheque = processador.identificar_tipo(texto_pagina)
            dados_extraidos = processador.extrair_dados(texto_pagina, tipo_contracheque)
            valores_pagina = {campo: 0.0 for campo in campos_obrigatorios}
            valores_pagina.update(dados_extraidos)
            resultados_por_pagina.append((mes_ano_encontrado, valores_pagina))
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
    if 'files' not in request.files:
        flash('Nenhum arquivo selecionado')
        return redirect(url_for('calculadora_index'))
    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        flash('Nenhum arquivo selecionado')
        return redirect(url_for('calculadora_index'))

    resultados_por_ano = {}
    erros = []
    campos_base = [
        'titular', 'conjuge', 'dependente', 'agregado_jovem', 'agregado_maior',
        'plano_especial', 'coparticipacao', 'retroativo', 'restituicao',
        'parcela_risco_titular', 'parcela_risco_dependente', 'parcela_risco_conjuge', 'parcela_risco_agregado'
    ]

    for file in files:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        try:
            file.save(filepath)
            resultados_pagina = processar_pdf(filepath)
            for mes_ano_str, valores_pagina in resultados_pagina:
                if mes_ano_str != "Período não identificado":
                    _, ano = mes_ano_str.split('/')
                    if ano not in resultados_por_ano:
                        resultados_por_ano[ano] = {'geral': {c: 0.0 for c in campos_base}, 'detalhes_mensais': {}}
                    
                    if mes_ano_str not in resultados_por_ano[ano]['detalhes_mensais']:
                         resultados_por_ano[ano]['detalhes_mensais'][mes_ano_str] = {'valores': {c: 0.0 for c in campos_base}}

                    for campo, valor in valores_pagina.items():
                        if campo in campos_base:
                            resultados_por_ano[ano]['geral'][campo] += valor
                            resultados_por_ano[ano]['detalhes_mensais'][mes_ano_str]['valores'][campo] += valor
        except Exception as e:
            logger.error(f"Erro no upload do arquivo {filename}: {e}", exc_info=True)
            erros.append(filename)
        finally:
            if os.path.exists(filepath):
                try: os.remove(filepath)
                except OSError as re_err: logger.error(f"Erro ao remover {filepath}: {re_err}")
    
    if not resultados_por_ano:
        flash('Nenhum dado válido pôde ser extraído dos arquivos PDF fornecidos.', 'warning')
        return redirect(url_for('calculadora_index'))

    for ano in resultados_por_ano:
        total_do_ano = sum(v for k, v in resultados_por_ano[ano]['geral'].items() if k != 'restituicao')
        resultados_por_ano[ano]['total_ano'] = total_do_ano

    session['resultados_por_ano'] = resultados_por_ano
    if erros: flash(f'Processamento concluído com erros em: {", ".join(erros)}', 'warning')
    return redirect(url_for('mostrar_resultados'))


@app.route('/resultados')
def mostrar_resultados():
    if 'resultados_por_ano' not in session:
        return redirect(url_for('calculadora_index'))
    resultados_por_ano = session.get('resultados_por_ano', {})
    total_geral = sum(dados_ano.get('total_ano', 0.0) for dados_ano in resultados_por_ano.values())
    anos_ordenados = sorted(resultados_por_ano.keys(), key=int, reverse=True)
    ordem_descontos = [
        "titular", "parcela_risco_titular", "conjuge", "parcela_risco_conjuge", "dependente", 
        "parcela_risco_dependente", "agregado_jovem", "agregado_maior", "parcela_risco_agregado",
        "plano_especial", "coparticipacao", "retroativo"
    ]
    return render_template('resultado.html',
                           resultados_por_ano={ano: resultados_por_ano[ano] for ano in anos_ordenados},
                           total_geral=total_geral,
                           ordem_descontos=ordem_descontos,
                           now=datetime.now())

@app.route('/detalhes')
def detalhes_mensais():
    if 'resultados_por_ano' not in session:
        return redirect(url_for('calculadora_index'))
    return render_template('detalhes_mes.html', resultados_por_ano=session.get('resultados_por_ano', {}), meses_ordem=MESES_ORDEM)

@app.route('/analise')
def mostrar_analise_detalhada():
    if 'resultados_por_ano' not in session:
        return redirect(url_for('calculadora_index'))
    
    resultados_por_ano = session.get('resultados_por_ano', {})
    dados_analisados = analisador.analisar_resultados(resultados_por_ano)
    
    anos_ordenados = sorted(dados_analisados.keys(), key=int, reverse=True)
    
    # Adicionamos uma lista de descrições para usar no HTML
    descricao_rubricas = {
        'titular': 'Titular', 'conjuge': 'Cônjuge', 'dependente': 'Dependente', 'agregado_jovem': 'Agregado Jovem', 
        'agregado_maior': 'Agregado Maior', 'plano_especial': 'Plano Especial', 'coparticipacao': 'Coparticipação', 
        'retroativo': 'Retroativo', 'restituicao': 'Restituição', 'parcela_risco_titular': 'P. Risco Titular', 
        'parcela_risco_dependente': 'P. Risco Dependente', 'parcela_risco_conjuge': 'P. Risco Cônjuge', 'parcela_risco_agregado': 'P. Risco Agregado'
    }
    
    return render_template('analise_detalhada.html', 
                           dados_analisados=dados_analisados,
                           anos_ordenados=anos_ordenados,
                           descricao_rubricas=descricao_rubricas,
                           meses_ordem_keys=list(MESES_ORDEM.keys()))


if __name__ == '__main__':
    app.run(debug=True)

