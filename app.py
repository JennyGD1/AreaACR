from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_session import Session  # pip install Flask-Session
from werkzeug.utils import secure_filename
import os
import fitz
import re
from processador_contracheque import ProcessadorContracheque

# Configuração do Flask
app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
Session(app)

# Garante que a pasta de uploads existe
app.config['UPLOAD_FOLDER'] = os.path.join('tmp')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

processador = ProcessadorContracheque()

MESES = {
    "Janeiro": "01", "Fevereiro": "02", "Março": "03", "Abril": "04",
    "Maio": "05", "Junho": "06", "Julho": "07", "Agosto": "08",
    "Setembro": "09", "Outubro": "10", "Novembro": "11", "Dezembro": "12"
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return redirect(url_for('indexcalculadora'))
    
    file = request.files['file']
    if file.filename == '':
        return redirect(url_for('indexcalculadora'))
    
    if file and file.filename.lower().endswith('.pdf'):
        try:
            # Processa diretamente da memória
            resultados = processador.processar_pdf(file)
            
            # Armazena resultados na sessão
            session['resultados'] = resultados
            
            # Redireciona para análise detalhada
            return redirect(url_for('analise_detalhada'))
            
        except Exception as e:
            print(f"Erro no processamento: {str(e)}")
            return redirect(url_for('indexcalculadora'))
    
    return redirect(url_for('indexcalculadora'))

@app.route('/analise')
def analise_detalhada():
    resultados = session.get('resultados', {})
    return render_template('analise_detalhada.html', resultados=resultados)

@app.route('/calculadora')
def indexcalculadora():
    return render_template('indexcalculadora.html')


@app.route('/analise_detalhada')
def analise_detalhada():
    if 'resultados' not in session:
        flash('Nenhum dado disponível para análise')
        return redirect(url_for('calculadora'))
    
    # Extrai o período do texto processado (se necessário)
    periodo = "Período não identificado"
    
    return render_template(
        'analise_detalhada.html',
        resultados=session['resultados'],
        total_proventos=session['total_proventos'],
        total_descontos=session['total_descontos'],
        periodo=periodo,
        rubricas_detalhadas=processador.rubricas_detalhadas,
        codigos_proventos=processador.codigos_proventos,
        meses=MESES
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
