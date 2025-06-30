from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_session import Session
from werkzeug.utils import secure_filename
from config_manager import load_rubricas
import os
import re
import fitz # PyMuPDF
from collections import defaultdict
import logging
import json
from processador_contracheque import ProcessadorContracheque
from analisador import AnalisadorPlanserv # Alterado: AnalisadorDescontos para AnalisadorPlanserv

# Carrega as rubricas uma vez no início da aplicação
rubricas = load_rubricas()

# Inicializa os módulos com as rubricas
processador = ProcessadorContracheque(rubricas)
analisador = AnalisadorPlanserv() # Alterado: Instancia AnalisadorPlanserv

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
    MAX_CONTENT_LENGTH=16 * 1024 * 1024, # 16MB
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
            'descricoes': dados.get('descricoes', {}) # Descrições podem estar aqui ou serem geradas dinamicamente
        }
    
    # Cria novo dicionário serializável
    serializable_results = {
        'primeiro_mes': resultados.get('primeiro_mes'),
        'ultimo_mes': resultados.get('ultimo_mes'),
        'meses_para_processar': resultados.get('meses_para_processar', []),
        'dados_mensais': dados_mensais,
        'erros': resultados.get('erros', []),
        'tabela': resultados.get('tabela', 'Desconhecida'), # Adiciona a tabela
        # Adiciona os totais calculados pelo analisador aqui para serem serializados
        'proventos_totais_planserv': resultados.get('proventos_totais_planserv'),
        'descontos_totais_planserv': resultados.get('descontos_totais_planserv')
    }

    # Se 'totais' foi adicionado pelo `processador.gerar_totais`, garantir que também seja serializável
    if 'totais' in resultados:
        serializable_results['totais'] = {
            'mensais': {k: dict(v) for k, v in resultados['totais']['mensais'].items()},
            'anuais': {k: dict(v) for k, v in resultados['totais']['anuais'].items()},
            'geral': dict(resultados['totais']['geral'])
        }
    if 'descricoes' in resultados:
        serializable_results['descricoes_tabela_geral'] = resultados['descricoes'] # Renomeado para evitar conflito

    # Para 'tabela_geral' que é gerada no /analise, ela já deve ser um dict normal, mas vamos garantir
    if 'tabela_geral' in resultados:
        serializable_results['tabela_geral'] = resultados['tabela_geral']
    
    return serializable_results


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calculadora')
def calculadora():
    # Removido o bloco de código que tentava carregar resultados aqui
    return render_template('indexcalculadora.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'files[]' not in request.files:
        flash('Nenhum arquivo selecionado', 'error')
        return redirect(url_for('calculadora'))

    files = request.files.getlist('files[]')
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
                
                # Adicione logs para depuração
                app.logger.info(f"Processando arquivo: {filename}")
                
                dados_contracheque = processador.processar_contracheque(filepath)
                app.logger.info(f"Dados processados: {json.dumps(dados_contracheque, indent=2)}")
                
                resultados_globais['dados_mensais'].update(dados_contracheque.get('dados_mensais', {}))
                resultados_globais['quantidade_arquivos'] += 1
                os.remove(filepath)

        # Gera a tabela geral
        tabela_geral = processador.gerar_tabela_geral(resultados_globais)
        app.logger.info(f"Tabela geral gerada: {json.dumps(tabela_geral, indent=2)}")
        
        session['resultados'] = json.dumps(tabela_geral)
        return redirect(url_for('analise_detalhada'))
        
    except Exception as e:
        app.logger.error(f"Erro no processamento: {str(e)}")
        flash(f'Erro ao processar arquivos: {str(e)}', 'error')
        return redirect(url_for('calculadora'))
    
@app.route('/analise')
def analise_detalhada():
    if 'resultados' not in session:
        flash('Nenhum dado disponível', 'error')
        return redirect(url_for('calculadora'))
    
    try:
        resultados = json.loads(session['resultados'])
        app.logger.info(f"Resultados para análise: {json.dumps(resultados, indent=2)}")
        
        # Verifique a estrutura dos dados
        if 'colunas' not in resultados or 'dados' not in resultados:
            app.logger.error("Estrutura de resultados inválida")
            flash('Dados formatados incorretamente', 'error')
            return redirect(url_for('calculadora'))
            
        return render_template('analise_detalhada.html', resultados=resultados)
        
    except Exception as e:
        app.logger.error(f"Erro ao carregar análise: {str(e)}")
        flash('Erro ao exibir resultados', 'error')
        return redirect(url_for('calculadora'))
        
if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'False') == 'True')
