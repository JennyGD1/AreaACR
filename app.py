from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_session import Session
from werkzeug.utils import secure_filename
import os
import re
import fitz # PyMuPDF
from collections import defaultdict
import logging
import json # Importar json aqui para usar em logs
from pathlib import Path # Importar Path para carregar rubricas

# Importa as classes ProcessadorContracheque e AnalisadorPlanserv
from processador_contracheque import ProcessadorContracheque
from analisador import AnalisadorPlanserv

# Configuração de logging (melhorar o nível para DEBUG para ver as saídas do print)
logging.basicConfig(level=logging.DEBUG) # Alterado para DEBUG
logger = logging.getLogger(__name__)

# Função para carregar rubricas (centralizada aqui para garantir que todos a usem)
def load_rubricas() -> Dict[str, Any]:
    try:
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
analisador = AnalisadorPlanserv(processador=processador) # Passa a mesma instância do processador


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

def converter_para_dict_serializavel(resultados: Dict) -> Dict:
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
    return render_template('indexcalculadora.html') # Removido 'json=json' pois não é mais necessário aqui

@app.route('/upload', methods=['POST'])
def upload():
    if 'files[]' not in request.files:
        flash('Nenhum arquivo selecionado', 'error')
        return redirect(url_for('calculadora'))

    files = request.files.getlist('files[]')
    if not files or all(file.filename == '' for file in files):
        flash('Nenhum arquivo selecionado', 'error')
        return redirect(url_for('calculadora'))

    # Inicializa resultados_globais para consolidar dados de múltiplos PDFs
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
                
                # Processa cada arquivo PDF usando o método processar_contracheque
                dados_contracheque_atual = processador.processar_contracheque(filepath)
                
                # Adiciona dados do arquivo atual aos resultados globais
                if 'dados_mensais' in dados_contracheque_atual:
                    for mes_ano, dados_mes in dados_contracheque_atual['dados_mensais'].items():
                        if mes_ano not in resultados_globais['dados_mensais']:
                            resultados_globais['dados_mensais'][mes_ano] = dados_mes
                        else:
                            # Se o mês já existe (pode acontecer com múltiplos PDFs), mesclar dados
                            # Esta lógica de mesclagem é simplificada; pode precisar ser mais robusta
                            # se houver rubricas diferentes no mesmo mês em PDFs distintos.
                            for rub_type in ['rubricas', 'rubricas_detalhadas']:
                                for cod, val in dados_mes.get(rub_type, {}).items():
                                    resultados_globais['dados_mensais'][mes_ano][rub_type][cod] += val
                            resultados_globais['dados_mensais'][mes_ano]['total_proventos'] += dados_mes.get('total_proventos', 0.0)

                # Atualiza os limites de meses para o período global
                if dados_contracheque_atual.get('primeiro_mes'):
                    if not resultados_globais['primeiro_mes'] or \
                       processador.meses_anos.index(dados_contracheque_atual['primeiro_mes']) < \
                       processador.meses_anos.index(resultados_globais['primeiro_mes']):
                        resultados_globais['primeiro_mes'] = dados_contracheque_atual['primeiro_mes']
                
                if dados_contracheque_atual.get('ultimo_mes'):
                    if not resultados_globais['ultimo_mes'] or \
                       processador.meses_anos.index(dados_contracheque_atual['ultimo_mes']) > \
                       processador.meses_anos.index(resultados_globais['ultimo_mes']):
                        resultados_globais['ultimo_mes'] = dados_contracheque_atual['ultimo_mes']

                if dados_contracheque_atual.get('tabela') and resultados_globais['tabela'] == 'Desconhecida':
                    resultados_globais['tabela'] = dados_contracheque_atual['tabela']

                resultados_globais['quantidade_arquivos'] += 1
                os.remove(filepath)
            else:
                flash(f'Arquivo {file.filename} não é um PDF válido', 'error')

        # Recalcula a lista completa de meses a processar com base nos limites globais
        if resultados_globais['primeiro_mes'] and resultados_globais['ultimo_mes']:
            index_primeiro = processador.meses_anos.index(resultados_globais['primeiro_mes'])
            index_ultimo = processador.meses_anos.index(resultados_globais['ultimo_mes'])
            resultados_globais['meses_para_processar'] = processador.meses_anos[index_primeiro:index_ultimo + 1]

        # Agora, chame o analisador e o gerador de tabela geral com os resultados consolidados
        analise_planserv = analisador.analisar_resultados(resultados_globais)
        resultados_globais['proventos_totais_planserv'] = analise_planserv['proventos']
        resultados_globais['descontos_totais_planserv'] = analise_planserv['descontos']

        tabela_geral = processador.gerar_tabela_geral(resultados_globais)
        
        # Combine os resultados para a sessão (use uma nova variável para evitar sobrescrever)
        final_results_for_session = {
            **resultados_globais, # Isso deve incluir dados_mensais, etc.
            'tabela_geral': tabela_geral,
            # 'proventos_totais_planserv' e 'descontos_totais_planserv' já estão em resultados_globais
        }

        # Converte para um dicionário serializável antes de salvar na sessão
        session['resultados'] = json.dumps(converter_para_dict_serializavel(final_results_for_session))
        
        logger.info(f"Resultados consolidados e serializados para sessão: {json.dumps(final_results_for_session, indent=2)}")
        
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
        flash('Erro ao exibir resultados. Por favor, tente novamente.', 'error')
        return redirect(url_for('calculadora'))

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'False') == 'True')
