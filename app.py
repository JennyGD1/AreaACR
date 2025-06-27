from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_session import Session  # pip install Flask-Session
from werkzeug.utils import secure_filename
import os
import fitz
import re
from processador_contracheque import ProcessadorContracheque

# Configuração do Flask
app = Flask(__name__)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
app.config['SECRET_KEY'] = 'sua-chave-secreta-aqui'  # Substitua por uma chave real
Session(app)

# Garante que a pasta de uploads existe
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

@app.route('/calculadora')
def calculadora():
    session.clear()
    return render_template('indexcalculadora.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        try:
            # Processa o arquivo
            resultados = processador.processar_pdf(file)
            
            # Armazena apenas o necessário na sessão ou usa cache
            session['resultados'] = {
                'resumo': resultados.get('resumo', {}),
                'dados_principais': resultados.get('dados_principais', {})
            }
            
            # Renderiza diretamente em vez de redirecionar
            return render_template('resultado.html', resultados=resultados)
            
        except Exception as e:
            flash(f"Erro ao processar arquivo: {str(e)}")
            return redirect(url_for('calculadora'))
    else:
        flash("Tipo de arquivo não permitido")
        return redirect(url_for('calculadora'))

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
