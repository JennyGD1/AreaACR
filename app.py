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
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

processador = ProcessadorContracheque()

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
        flash('Nenhum arquivo enviado')
        return redirect(url_for('calculadora'))
    
    file = request.files['file']
    if file.filename == '':
        flash('Nenhum arquivo selecionado')
        return redirect(url_for('calculadora'))
    
    if file and file.filename.lower().endswith('.pdf'):
        try:
            # Salva temporariamente o arquivo
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            
            # Processa o arquivo
            resultados = processador.processar_pdf(filepath)
            
            # Remove o arquivo temporário
            os.remove(filepath)
            
            # Armazena resultados na sessão
            session['resultados'] = resultados
            
            # Redireciona para a página de resultados
            return redirect(url_for('resultados'))
            
        except Exception as e:
            flash(f'Erro ao processar arquivo: {str(e)}')
            return redirect(url_for('calculadora'))
    
    flash('Por favor, envie um arquivo PDF válido')
    return redirect(url_for('calculadora'))

@app.route('/resultados')
def resultados():
    if 'resultados' not in session:
        flash('Nenhum resultado encontrado')
        return redirect(url_for('calculadora'))
    
    return render_template('resultados.html', resultados=session['resultados'])

@app.route('/calculadora')
def calculadora():
    return render_template('calculadora.html')


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
