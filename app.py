# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_session import Session
from werkzeug.utils import secure_filename
import os
import re
import fitz # PyMuPDF
from collections import defaultdict
import logging
import json 
from pathlib import Path 
from typing import Dict, Any # <--- ESSA LINHA É CRUCIAL E PRECISA ESTAR AQUI!

# Importa as classes ProcessadorContracheque e AnalisadorPlanserv
from processador_contracheque import ProcessadorContracheque
from analisador import AnalisadorPlanserv

# Configuração de logging
logging.basicConfig(level=logging.DEBUG) # Alterado para DEBUG
logger = logging.getLogger(__name__)

# Função para carregar rubricas (centralizada aqui para garantir que todos a usem)
def load_rubricas() -> Dict[str, Any]: # Corrigido para Dict[str, Any]
    try:
        # Caminho corrigido para rubricas.json (assumindo que rubricas.json está na raiz do projeto)
        rubricas_path = Path(__file__).parent / 'rubricas.json' 
        with open(rubricas_path, 'r', encoding='utf-8') as f:
            return json.load(f).get('rubricas', {"proventos": {}, "descontos": {}})
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Erro ao carregar rubricas: {str(e)}")
        # Retorna uma estrutura vazia para evitar crash se o arquivo não for encontrado
        return {"proventos": {}, "descontos": {}}

# Carrega as rubricas uma vez no início da aplicação
rubricas_globais = load_rubricas()

# Inicializa os módulos com as rubricas carregadas
processador = ProcessadorContracheque(rubricas=rubricas_globais)
analisador = AnalisadorPlanserv(processador=processador) 


try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configuração do Flask
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback_secret_key')

# Configurações de sessão e upload
app.config.update(
    SESSION_TYPE='filesystem',
    UPLOAD_FOLDER=os.path.join('tmp', 'uploads'),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024, # 16MB
    SESSION_FILE_DIR=os.path.join('tmp', 'flask_session'),
    ALLOWED_EXTENSIONS={'pdf'}
)

# Garante que os diretórios existam
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)

Session(app)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def converter_para_dict_serializavel(resultados: Dict[str, Any]) -> Dict[str, Any]:
    """Converte defaultdicts e outros objetos não serializáveis para dicts/listas regulares."""
    if not isinstance(resultados, dict):
        return resultados # Já é serializável ou um tipo inesperado
    
    serializable_results = {}
    for key, value in resultados.items():
        if isinstance(value, defaultdict):
            serializable_results[key] = dict(value)
        elif isinstance(value, dict):
            serializable_results[key] = converter_para_dict_serializavel(value)
        elif isinstance(value, list):
            serializable_results[key] = [converter_para_dict_serializavel(item) for item in value]
        else:
            serializable_results[key] = value
    return serializable_results


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calculadora')
def calculadora():
    return render_template('indexcalculadora.html') 

@app.route('/upload', methods=['POST'])
def upload():
    if 'files[]' not in request.files:
        flash('Nenhum arquivo selecionado', 'error')
        return redirect(url_for('calculadora'))

    files = request.files.getlist('files[]')
    if not files or all(file.filename == '' for file in files):
        flash('Nenhum arquivo selecionado', 'error')
        return redirect(url_for('calculadora'))

    resultados_globais = {
        'dados_mensais': {},
        'erros': [],
        'quantidade_arquivos': 0,
        'primeiro_mes': None,
        'ultimo_mes': None,
        'meses_para_processar': [],
        'tabela': 'Desconhecida'
    }

    try:
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                logger.info(f"Processando arquivo: {filename}")
                dados_arquivo_atual = processador.processar_contracheque(filepath)
                
                for mes_ano, dados_mes in dados_arquivo_atual.get('dados_mensais', {}).items():
                    if mes_ano not in resultados_globais['dados_mensais']:
                        resultados_globais['dados_mensais'][mes_ano] = dados_mes
                    else:
                        for k, v in dados_mes.items():
                            if isinstance(v, dict):
                                for sub_k, sub_v in v.items():
                                    # A linha com o erro de digitação foi aqui.
                                    # Forma correta é [mes_ano] e não [mes_ano']
                                    resultados_globais['dados_mensais'][mes_ano][k][sub_k] += sub_v
                            elif isinstance(v, (int, float)):
                                # E aqui também.
                                resultados_globais['dados_mensais'][mes_ano][k] += v

                if dados_arquivo_atual.get('primeiro_mes'):
                    if not resultados_globais['primeiro_mes'] or processador.meses_anos.index(dados_arquivo_atual['primeiro_mes']) < processador.meses_anos.index(resultados_globais['primeiro_mes']):
                        resultados_globais['primeiro_mes'] = dados_arquivo_atual['primeiro_mes']
                
                if dados_arquivo_atual.get('ultimo_mes'):
                    if not resultados_globais['ultimo_mes'] or processador.meses_anos.index(dados_arquivo_atual['ultimo_mes']) > processador.meses_anos.index(resultados_globais['ultimo_mes']):
                        resultados_globais['ultimo_mes'] = dados_arquivo_atual['ultimo_mes']

                resultados_globais['quantidade_arquivos'] += 1
                os.remove(filepath)

        if resultados_globais['primeiro_mes'] and resultados_globais['ultimo_mes']:
            idx_primeiro = processador.meses_anos.index(resultados_globais['primeiro_mes'])
            idx_ultimo = processador.meses_anos.index(resultados_globais['ultimo_mes'])
            resultados_globais['meses_para_processar'] = processador.meses_anos[idx_primeiro:idx_ultimo + 1]

        tabela_proventos = processador.gerar_tabela_proventos_resumida(resultados_globais)
        tabela_descontos = processador.gerar_tabela_descontos_detalhada(resultados_globais)

        final_results_for_session = {
            'tabela_proventos_resumida': tabela_proventos,
            'tabela_descontos_detalhada': tabela_descontos,
        }

        session['resultados'] = json.dumps(converter_para_dict_serializavel(final_results_for_session))
        
        flash('Arquivos processados com sucesso!', 'success')
        return redirect(url_for('analise_detalhada'))

    except Exception as e:
        logger.error(f"Erro no processamento global: {str(e)}")
        flash(f'Ocorreu um erro ao processar os arquivos: {str(e)}', 'error')
        return redirect(url_for('calculadora'))

@app.route('/analise')
def analise_detalhada():
    if 'resultados' not in session:
        flash('Nenhum dado de análise disponível. Por favor, envie um arquivo primeiro.', 'error')
        return redirect(url_for('calculadora'))
    
    try:
        resultados = json.loads(session['resultados'])
        
        # O logger aqui mostrará a estrutura de dados DESERIALIZADA que o template vai usar.
        logger.info(f"Resultados desserializados para template: {json.dumps(resultados, indent=2)}")
        
        return render_template('analise_detalhada.html', resultados=resultados)
        
    except json.JSONDecodeError:
        logger.error("Erro ao decodificar resultados da sessão: JSON inválido")
        flash('Erro ao carregar dados da sessão. Por favor, tente novamente.', 'error')
        return redirect(url_for('calculadora'))
    except Exception as e:
        logger.error(f"Erro ao carregar análise para template: {str(e)}")
        flash('Erro ao exibir resultados', 'error')
        return redirect(url_for('calculadora'))

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'False') == 'True')
