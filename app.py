from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_session import Session
from werkzeug.utils import secure_filename
import os
from processador_contracheque import ProcessadorContracheque

# Configuração do Flask
app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'  # Substitua por uma chave real e segura

# Configurações importantes
app.config.update(
    SESSION_TYPE='filesystem',
    UPLOAD_FOLDER=os.path.join('tmp', 'uploads'),  # Pasta temporária para uploads
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB
    SESSION_FILE_DIR=os.path.join('tmp', 'flask_session')  # Pasta para sessões
)

# Garante que as pastas existam
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)

# Inicializa a sessão
Session(app)

processador = ProcessadorContracheque()

@app.route('/')
def home():
    return redirect(url_for('index.html'))

@app.route('/calculadora')
def indexcalculadora():
    return render_template('indexcalculadora.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        print("DEBUG - Arquivos recebidos:", request.files)  # Adicione para debug
        flash('Nenhum arquivo na requisição')
        return redirect(url_for('indexcalculadora'))
    
    file = request.files['file']
    if file.filename == '':
        flash('Arquivo vazio')
        return redirect(url_for('indexcalculadora'))
    
    try:
        # Processamento do PDF
        resultados = processador.processar_pdf(file)
        session['resultados'] = resultados
        return redirect(url_for('analise_detalhada'))
    
    except Exception as e:
        flash(f'Erro no processamento: {str(e)}')
        return redirect(url_for('indexcalculadora'))

@app.route('/analise')
def analise_detalhada():
    if 'resultados' not in session:
        flash('Nenhum resultado encontrado', 'error')
        return redirect(url_for('indexcalculadora'))
    
    return render_template('analise_detalhada.html', resultados=session['resultados'])

if __name__ == '__main__':
    app.run(debug=True)
