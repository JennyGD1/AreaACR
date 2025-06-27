from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_session import Session
from werkzeug.utils import secure_filename
import os
import re
import fitz  # PyMuPDF
from collections import defaultdict
import logging
import json

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configuração do Flask
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback_secret_key')  # Chave via variável de ambiente

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

# Constantes
CODIGOS = {
    '7033': 'titular',
    '7035': 'conjuge',
    '7034': 'dependente',
    '7038': 'agregado_jovem',
    '7039': 'agregado_maior',
    '7037': 'plano_especial',
    '7040': 'coparticipacao',
    '7049': 'retroativo',
    '7088': 'parcela_risco_titular',
    '7089': 'parcela_risco_dependente',
    '7090': 'parcela_risco_conjuge',
    '7091': 'parcela_risco_agregado'
}

MESES_ORDEM = {
    'Janeiro': 1, 'Fevereiro': 2, 'Março': 3, 'Abril': 4,
    'Maio': 5, 'Junho': 6, 'Julho': 7, 'Agosto': 8,
    'Setembro': 9, 'Outubro': 10, 'Novembro': 11, 'Dezembro': 12
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extrair_mes_ano_do_texto(texto):
    padrao_mes_ano = r'(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\s+(\d{4})'
    match = re.search(padrao_mes_ano, texto, re.IGNORECASE)
    if match:
        return f"{match.group(1)}/{match.group(2)}", None
    return None, "Período não identificado no PDF"

def extrair_valor_linha(linha):
    # Padrão para identificar valores (incluindo negativos e formatos brasileiros)
    padrao_valor = r'([-+]?\s*\d{1,3}(?:[.,\s]?\d{3})*(?:[.,]\d{2}))'
    valores = re.findall(padrao_valor, linha)
    
    if valores:
        # Pega o último valor encontrado na linha (mais à direita)
        valor_str = valores[-1].strip()
        
        # Remove espaços e pontos de milhar, substitui vírgula decimal por ponto
        valor_str = valor_str.replace(' ', '').replace('.', '').replace(',', '.')
        
        try:
            valor = float(valor_str)
            logger.debug(f"Valor extraído: {valor} da linha: {linha}")
            return valor
        except ValueError:
            logger.warning(f"Valor inválido na linha: {linha}")
            return 0.0
    return 0.0

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
            'rubricas_detalhadas': dict(dados['rubricas_detalhadas'])
        }
    
    # Cria novo dicionário serializável
    return {
        'primeiro_mes': resultados.get('primeiro_mes'),
        'ultimo_mes': resultados.get('ultimo_mes'),
        'meses_para_processar': resultados.get('meses_para_processar', []),
        'dados_mensais': dados_mensais,
        'total_geral': resultados.get('total_geral', {}),
        'erros': resultados.get('erros', [])
    }

def processar_pdf(file_bytes):
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        logger.info(f"PDF aberto com {len(doc)} páginas")
        
        resultados = {
            'primeiro_mes': None,
            'ultimo_mes': None,
            'meses_para_processar': [],
            'dados_mensais': defaultdict(lambda: {
                'total_proventos': 0,
                'rubricas': defaultdict(float),
                'rubricas_detalhadas': defaultdict(float)
            }),
            'total_geral': {
                'total_proventos': 0,
                'total_descontos': 0
            },
            'erros': []
        }

        for page_num, page in enumerate(doc):
            logger.info(f"Processando página {page_num + 1}")
            texto = page.get_text("text")
            logger.debug(f"Texto da página {page_num + 1}:\n{texto[:500]}...")  # Loga apenas o início
            
            mes_ano, erro = extrair_mes_ano_do_texto(texto)
            
            if erro:
                resultados['erros'].append(erro)
                continue
            
            if mes_ano not in resultados['meses_para_processar']:
                resultados['meses_para_processar'].append(mes_ano)

            for linha in texto.split('\n'):
                linha = linha.strip()
                codigo_match = re.match(r'^(\d{4})\b', linha)
                
                if codigo_match and codigo_match.group(1) in CODIGOS:
                    codigo = codigo_match.group(1)
                    valor = extrair_valor_linha(linha)
                    logger.debug(f"Linha processada - Código: {codigo}, Valor: {valor}, Linha: {linha}")
                    
                    resultados['dados_mensais'][mes_ano]['rubricas'][codigo] += valor
                    resultados['dados_mensais'][mes_ano]['total_proventos'] += valor
                    resultados['total_geral']['total_proventos'] += valor

        # Ordenação e outros processamentos...
        return converter_para_dict_serializavel(resultados)
        
    except Exception as e:
        logger.error(f"Erro ao processar PDF: {str(e)}", exc_info=True)
        return {
            'erro': "Erro ao processar o arquivo PDF",
            'erros': [f"Erro no processamento: {str(e)}"]
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
        
        resultados = processar_pdf(file_bytes)
        logger.info(f"Resultados do processamento: {resultados}")
        
        if not resultados or 'erro' in resultados:
            flash(resultados.get('erro', 'Nenhum dado válido encontrado no PDF'), 'error')
            return redirect(url_for('calculadora'))
        
        if resultados.get('erros'):
            flash('Alguns problemas foram encontrados no processamento', 'warning')
        
        session['resultados'] = resultados
        session.modified = True
        return redirect(url_for('analise_detalhada'))
    
    except Exception as e:
        logger.error(f"Erro no upload: {str(e)}", exc_info=True)
        flash('Erro ao processar o arquivo. Tente novamente.', 'error')
        return redirect(url_for('calculadora'))

@app.route('/analise')
def analise_detalhada():
    resultados = session.get('resultados')
    
    if not resultados:
        flash('Nenhum dado de análise disponível. Por favor, envie um arquivo primeiro.', 'error')
        return redirect(url_for('calculadora'))
    
    total_geral = resultados.get('total_geral', {})
    return render_template(
        'analise_detalhada.html',
        resultados=resultados,
        total_proventos=total_geral.get('total_proventos', 0),
        total_descontos=total_geral.get('total_descontos', 0),
        CODIGOS=CODIGOS  # Adicionando esta linha para passar a constante CODIGOS para o template
    )
if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'False') == 'True')
