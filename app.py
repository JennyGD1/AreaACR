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
from analisador import AnalisadorPlanserv

# Carrega as rubricas uma vez no início da aplicação
rubricas = load_rubricas()

# Inicializa os módulos com as rubricas
processador = ProcessadorContracheque(rubricas)
analisador = AnalisadorPlanserv()

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
        return {
            'dados_mensais': {},
            'erros': [],
            'tabela': 'Desconhecida',
            'tabela_geral': {'colunas': [], 'dados': []},
            'proventos_totais_planserv': None,
            'descontos_totais_planserv': None,
            'totais': {
                'mensais': {},
                'anuais': {},
                'geral': {}
            }
        }
    
    # Converte os dados mensais
    dados_mensais = {}
    for mes_ano, dados in resultados.get('dados_mensais', {}).items():
        dados_mensais[mes_ano] = {
            'total_proventos': dados.get('total_proventos', 0.0),
            'rubricas': dict(dados.get('rubricas', {})),
            'rubricas_detalhadas': dict(dados.get('rubricas_detalhadas', {})),
            'descricoes': dados.get('descricoes', {})
        }
    
    # Cria novo dicionário serializável com todos os campos necessários
    serializable_results = {
        'primeiro_mes': resultados.get('primeiro_mes'),
        'ultimo_mes': resultados.get('ultimo_mes'),
        'meses_para_processar': resultados.get('meses_para_processar', []),
        'dados_mensais': dados_mensais,
        'erros': resultados.get('erros', []),
        'tabela': resultados.get('tabela', 'Desconhecida'),
        'tabela_geral': resultados.get('tabela_geral', {'colunas': [], 'dados': []}),
        'proventos_totais_planserv': resultados.get('proventos_totais_planserv'),
        'descontos_totais_planserv': resultados.get('descontos_totais_planserv'),
        'totais': {
            'mensais': {},
            'anuais': {},
            'geral': {}
        }
    }

    # Adiciona totais se existirem
    if 'totais' in resultados:
        serializable_results['totais'] = {
            'mensais': {k: dict(v) for k, v in resultados['totais']['mensais'].items()},
            'anuais': {k: dict(v) for k, v in resultados['totais']['anuais'].items()},
            'geral': dict(resultados['totais'].get('geral', {}))
        }
    
    # Adiciona descrições se existirem
    if 'descricoes' in resultados:
        serializable_results['descricoes_tabela_geral'] = resultados['descricoes']
    
    return serializable_results

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calculadora')
def calculadora():
    return render_template('indexcalculadora.html', json=json)

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
                
                logger.info(f"Processando arquivo: {filename}")
                
                dados_contracheque = processador.processar_contracheque(filepath)
                dados_contracheque['dados_mensais'] = {  # Garante a estrutura esperada
                    list(dados_contracheque['dados_mensais'].keys())[0]: {
                        **dados_contracheque['dados_mensais'][list(dados_contracheque['dados_mensais'].keys())[0]],
                        'erro': None  # Adiciona campo esperado
                    }
                }
                logger.info(f"Dados processados: {json.dumps(dados_contracheque, indent=2)}")
                
                # Aplica a análise do Planserv
                analise_planserv = analisador.analisar_resultados(dados_contracheque)
                dados_contracheque.update({
                    'proventos_totais_planserv': analise_planserv['proventos'],
                    'descontos_totais_planserv': analise_planserv['descontos']
                })
                
                resultados_globais['dados_mensais'].update(dados_contracheque.get('dados_mensais', {}))
                resultados_globais['quantidade_arquivos'] += 1
                os.remove(filepath)

        # Gera a tabela geral e os totais
        tabela_geral = processador.gerar_tabela_geral(resultados_globais)
        totais = processador.gerar_totais(resultados_globais)
        
        # Combina todos os resultados
        resultados_finais = {
            **resultados_globais,
            'tabela_geral': tabela_geral,
            **totais
        }
        
        logger.info(f"Tabela geral gerada: {json.dumps(tabela_geral, indent=2)}")
        
        session['resultados'] = json.dumps(converter_para_dict_serializavel(resultados_finais))
        return redirect(url_for('analise_detalhada'))
        
    except Exception as e:
        logger.error(f"Erro no processamento: {str(e)}")
        flash(f'Erro ao processar arquivos: {str(e)}', 'error')
        return redirect(url_for('calculadora'))
        
    except Exception as e:
        logger.error(f"Erro no processamento: {str(e)}")
        flash(f'Erro ao processar arquivos: {str(e)}', 'error')
        return redirect(url_for('calculadora'))

@app.route('/analise')
def analise_detalhada():
    if 'resultados' not in session:
        flash('Nenhum dado disponível', 'error')
        return redirect(url_for('calculadora'))
    
    try:
        resultados = json.loads(session['resultados'])
        
        # Verifica se a estrutura básica dos dados está presente
        if not isinstance(resultados, dict) or 'dados_mensais' not in resultados:
            flash('Dados formatados incorretamente', 'error')
            return redirect(url_for('calculadora'))
            
        return render_template('analise_detalhada.html', resultados=resultados)
        
    except json.JSONDecodeError:
        logger.error("Erro ao decodificar resultados da sessão")
        flash('Erro ao carregar dados da sessão', 'error')
        return redirect(url_for('calculadora'))
    except Exception as e:
        logger.error(f"Erro ao carregar análise: {str(e)}")
        flash('Erro ao exibir resultados', 'error')
        return redirect(url_for('calculadora'))

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'False') == 'True')
