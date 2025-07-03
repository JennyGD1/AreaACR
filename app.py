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
        return resultados 
    
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
    
    session.pop('resultados', None)
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

    # Estrutura para agregar os resultados de todos os arquivos
    resultados_globais = {
        'dados_mensais': {},
        'erros': [],
        'quantidade_arquivos': 0
    }

    try:
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                logger.info(f"Processando arquivo: {filename}")
                
                # Processa um único contracheque
                dados_arquivo_atual = processador.processar_contracheque(filepath)
                
                # Verifica se houve erro no processamento do arquivo individual
                if dados_arquivo_atual.get('erro'):
                    logger.warning(f"Falha ao processar {filename}: {dados_arquivo_atual['erro']}")
                    resultados_globais['erros'].append(f"{filename}: {dados_arquivo_atual['erro']}")
                    os.remove(filepath)
                    continue # Pula para o próximo arquivo

                # Agrega os dados mensais do arquivo atual aos resultados globais
                for mes_ano, dados_mes in dados_arquivo_atual.get('dados_mensais', {}).items():
                    if mes_ano not in resultados_globais['dados_mensais']:
                        resultados_globais['dados_mensais'][mes_ano] = dados_mes
                    else:
                        # Se o mês já existe, soma os valores (caso haja múltiplos arquivos para o mesmo mês)
                        resultados_globais['dados_mensais'][mes_ano]['total_proventos'] += dados_mes.get('total_proventos', 0)
                        resultados_globais['dados_mensais'][mes_ano]['total_descontos'] += dados_mes.get('total_descontos', 0)
                        for codigo, valor in dados_mes.get('rubricas', {}).items():
                            resultados_globais['dados_mensais'][mes_ano]['rubricas'][codigo] = resultados_globais['dados_mensais'][mes_ano]['rubricas'].get(codigo, 0) + valor
                        for codigo, valor in dados_mes.get('rubricas_detalhadas', {}).items():
                            resultados_globais['dados_mensais'][mes_ano]['rubricas_detalhadas'][codigo] = resultados_globais['dados_mensais'][mes_ano]['rubricas_detalhadas'].get(codigo, 0) + valor

                resultados_globais['quantidade_arquivos'] += 1
                os.remove(filepath)

        # Após processar todos os arquivos, verifica se houve algum sucesso
        if not resultados_globais['dados_mensais']:
            # Agrupa todas as mensagens de erro em um único flash
            if resultados_globais['erros']:
                error_list_html = "<ul>" + "".join([f"<li>{err}</li>" for err in resultados_globais['erros']]) + "</ul>"
                flash(f"Nenhum arquivo pôde ser processado.<br>Detalhes:{error_list_html}", 'error')
            else:
                flash('Nenhum arquivo válido foi enviado ou processado.', 'error')
            return redirect(url_for('calculadora'))

        # **CORREÇÃO PRINCIPAL: Usa os métodos que existem no processador**
        tabela_geral = processador.gerar_tabela_geral(resultados_globais)
        totais = processador.gerar_totais(resultados_globais)
        
        # Analisa os resultados globais para obter os totais do Planserv
        analise_planserv = analisador.analisar_resultados(resultados_globais)

        # Combina todos os resultados em um único dicionário para a sessão
        resultados_finais = {
            **resultados_globais,
            'tabela_geral': tabela_geral,
            'totais': totais,
            'analise_planserv': analise_planserv # Adiciona a análise do Planserv
        }
        
        # Converte para um formato serializável e salva na sessão
        session['resultados'] = json.dumps(converter_para_dict_serializavel(resultados_finais))
        
        flash(f"{resultados_globais['quantidade_arquivos']} arquivo(s) processado(s) com sucesso!", 'success')
        return redirect(url_for('analise_detalhada'))

    except Exception as e:
        # Captura de exceção genérica para problemas inesperados
        logger.error(f"Erro inesperado no processamento global: {str(e)}", exc_info=True)
        flash(f'Ocorreu um erro inesperado ao processar os arquivos: {str(e)}', 'error')
        return redirect(url_for('calculadora'))


@app.route('/analise')
def analise_detalhada():
    
    if 'resultados' not in session:
        flash('Nenhum dado de análise disponível. Por favor, envie um arquivo primeiro.', 'error')
        return redirect(url_for('calculadora'))
    
    try:
        resultados_json = session['resultados']
       
        
        resultados = json.loads(resultados_json)
        
        logger.info(f"Resultados desserializados para template: {json.dumps(resultados, indent=2)}")
        
        return render_template('analise_detalhada.html', resultados=resultados)
        
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Erro ao carregar dados da sessão: {str(e)}")
        flash('Erro ao carregar dados da sessão. Por favor, tente novamente.', 'error')
        return redirect(url_for('calculadora'))


if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'False') == 'True')
