from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_session import Session
from werkzeug.utils import secure_filename
import os
import json
from pathlib import Path
from typing import Dict, Any
from collections import defaultdict
from processador_contracheque import ProcessadorContracheque
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def load_rubricas() -> Dict[str, Any]:
    try:
        rubricas_path = Path(__file__).parent / 'rubricas.json'
        with open(rubricas_path, 'r', encoding='utf-8') as f:
            # Carrega o JSON completo para o processador
            return json.load(f)
    except Exception as e:
        logger.error(f"Erro fatal ao carregar rubricas.json: {e}")
        return {"rubricas": {"proventos": {}, "descontos": {}}}

# Carrega as rubricas uma vez
rubricas_globais = load_rubricas()
# Passa a seção 'rubricas' para o processador
processador = ProcessadorContracheque(rubricas=rubricas_globais.get('rubricas', {}))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'uma_chave_secreta_muito_forte')

app.config.update(
    SESSION_TYPE='filesystem',
    UPLOAD_FOLDER=os.path.join('tmp', 'uploads'),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    SESSION_FILE_DIR=os.path.join('tmp', 'flask_session'),
    ALLOWED_EXTENSIONS={'pdf'}
)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)

Session(app)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def converter_para_dict_serializavel(data):
    if isinstance(data, dict):
        return {k: converter_para_dict_serializavel(v) for k, v in data.items()}
    if isinstance(data, list):
        return [converter_para_dict_serializavel(i) for i in data]
    return data

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calculadora')
def calculadora():
    session.pop('resultados', None)
    return render_template('indexcalculadora.html')

@app.route('/upload', methods=['POST'])
def upload():
    files = request.files.getlist('files[]')
    if not files or all(f.filename == '' for f in files):
        flash('Nenhum arquivo selecionado', 'error')
        return redirect(url_for('calculadora'))

    try:
        # Simplificado para processar o primeiro arquivo
        file = files[0]
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            logger.info(f"Processando arquivo: {filename}")
            resultados_finais = processador.processar_contracheque(filepath)
            os.remove(filepath)
            
            # Chama os métodos corretos para gerar as tabelas
            tabela_proventos = processador.gerar_tabela_proventos_resumida(resultados_finais)
            tabela_descontos = processador.gerar_tabela_descontos_detalhada(resultados_finais)

            final_results_for_session = {
                'tabela_proventos_resumida': tabela_proventos,
                'tabela_descontos_detalhada': tabela_descontos,
            }

            session['resultados'] = json.dumps(converter_para_dict_serializavel(final_results_for_session))
            flash('Arquivo processado com sucesso!', 'success')
            return redirect(url_for('analise_detalhada'))
        else:
            flash('Arquivo inválido ou não permitido.', 'error')
            return redirect(url_for('calculadora'))

    except Exception as e:
        logger.error(f"Erro no processamento: {e}", exc_info=True)
        flash(f'Ocorreu um erro ao processar o arquivo: {e}', 'error')
        return redirect(url_for('calculadora'))

@app.route('/analise')
def analise_detalhada():
    resultados_json = session.get('resultados')
    if not resultados_json:
        flash('Nenhum dado de análise disponível. Por favor, envie um arquivo primeiro.', 'error')
        return redirect(url_for('calculadora'))
    
    try:
        resultados = json.loads(resultados_json)
        return render_template('analise_detalhada.html', resultados=resultados)
    except json.JSONDecodeError:
        flash('Erro ao carregar dados da sessão.', 'error')
        return redirect(url_for('calculadora'))

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'False') == 'True')
