from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_session import Session
from werkzeug.utils import secure_filename
from config_manager import load_rubricas
import os
import re
import fitz  # PyMuPDF
from collections import defaultdict
import logging
import json
from processador_contracheque import ProcessadorContracheque
from analisador import AnalisadorDescontos

# Carrega as rubricas uma vez no início da aplicação
rubricas = load_rubricas()

# Inicializa os módulos com as rubricas
processador = ProcessadorContracheque(rubricas)
analisador = AnalisadorDescontos()

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configuração do Flask
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback_secret_key')

# Configurações
app.config.update(
    SESSION_TYPE='filesystem',
    UPLOAD_FOLDER=os.path.join('tmp', 'uploads'),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB
    SESSION_FILE_DIR=os.path.join('tmp', 'flask_session'),
    ALLOWED_EXTENSIONS={'pdf'}
)

# Garante que os diretórios existam
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Session(app)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def converter_para_dict_serializavel(resultados):
    """Converte os defaultdicts para dicts regulares para serialização"""
    if not resultados:
        return resultados
    
    # Converte os dados mensais
    dados_mensais = {}
    for mes_ano, dados in resultados.get('dados_mensais', {}).items():
        dados_mensais[mes_ano] = {
            'total_proventos': dados['total_proventos'],
            'rubricas': dict(dados['rubricas']),
            'rubricas_detalhadas': dict(dados['rubricas_detalhadas']),
            'descricoes': dados.get('descricoes', {})
        }
    
    # Cria novo dicionário serializável
    return {
        'primeiro_mes': resultados.get('primeiro_mes'),
        'ultimo_mes': resultados.get('ultimo_mes'),
        'meses_para_processar': resultados.get('meses_para_processar', []),
        'dados_mensais': dados_mensais,
        'erros': resultados.get('erros', [])
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calculadora')
def calculadora():
    return render_template('indexcalculadora.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        flash('Nenhum arquivo enviado', 'error')
        return redirect(url_for('calculadora'))
    
    file = request.files['file']
    if file.filename == '':
        flash('Nenhum arquivo selecionado', 'error')
        return redirect(url_for('calculadora'))
    
    if not allowed_file(file.filename):
        flash('Apenas arquivos PDF são aceitos', 'error')
        return redirect(url_for('calculadora'))
    
    try:
        file_bytes = file.read()
        logger.info(f"Arquivo recebido: {file.filename}, tamanho: {len(file_bytes)} bytes")
        
        # Usa o processador já inicializado com as rubricas
        resultados = processador.processar_pdf(file_bytes)
        resultados = converter_para_dict_serializavel(resultados)
        
        if not resultados or resultados.get('erros'):
            flash('Alguns problemas foram encontrados no processamento', 'warning')
        
        session['resultados'] = resultados
        session.modified = True
        return redirect(url_for('analise_detalhada'))
    
    except Exception as e:
        logger.error(f"Erro no upload: {str(e)}", exc_info=True)
        flash(f'Erro ao processar o arquivo: {str(e)}', 'error')
        return redirect(url_for('calculadora'))

@app.route('/analise')
def analise_detalhada():
    if 'resultados' not in session:
        flash('Nenhum dado de análise disponível. Por favor, envie um arquivo primeiro.', 'error')
        return redirect(url_for('calculadora'))
    
    try:
        resultados = session['resultados']
        
        # Garante que os dados estão no formato correto
        if not isinstance(resultados, dict):
            resultados = json.loads(resultados)
        
        # Processa a tabela geral se necessário
        if 'dados_mensais' in resultados:
            processador = ProcessadorContracheque()
            tabela_geral = processador.gerar_tabela_geral(resultados)
            resultados.update(tabela_geral)
        
        return render_template('analise_detalhada.html', resultados=resultados)
        
    except Exception as e:
        logger.error(f"Erro ao carregar análise: {str(e)}")
        flash('Erro ao carregar os resultados. Por favor, tente novamente.', 'error')
        return redirect(url_for('calculadora'))
        
if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'False') == 'True')
