from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_session import Session
from werkzeug.utils import secure_filename
import os
from processador_contracheque import ProcessadorContracheque

# Configuração do Flask
app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'  # Chave real em produção

# Configurações
app.config.update(
    SESSION_TYPE='filesystem',
    UPLOAD_FOLDER=os.path.join('tmp', 'uploads'),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB
    SESSION_FILE_DIR=os.path.join('tmp', 'flask_session')
)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)

Session(app)
processador = ProcessadorContracheque()

# Rotas principais
@app.route('/')
def index():
    """Página inicial com menu"""
    return render_template('index.html')

@app.route('/calculadora')
def calculadora():
    """Única rota para a calculadora ACR"""
    return render_template('indexcalculadora.html')

@app.route('/upload', methods=['POST'])
def upload():
    """Processamento do PDF"""
    if 'file' not in request.files:
        flash('Nenhum arquivo enviado', 'error')
        return redirect(url_for('calculadora'))
    
    file = request.files['file']
    if not file or file.filename == '':
        flash('Nenhum arquivo selecionado', 'error')
        return redirect(url_for('calculadora'))
    
    if not file.filename.lower().endswith('.pdf'):
        flash('Apenas arquivos PDF são aceitos', 'error')
        return redirect(url_for('calculadora'))

    try:
        # Processamento seguro
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        resultados = processador.processar_pdf(filepath)
        session['resultados'] = resultados
        os.remove(filepath)  # Limpeza
        
        return redirect(url_for('analise_detalhada'))
    except Exception as e:
        flash(f'Erro no processamento: {str(e)}', 'error')
        return redirect(url_for('calculadora'))

@app.route('/analise')
def analise_detalhada():
    """Exibição dos resultados"""
    if 'resultados' not in session:
        flash('Nenhum resultado disponível', 'error')
        return redirect(url_for('calculadora'))
    
    return render_template('analise_detalhada.html', 
                         resultados=session['resultados'])

if __name__ == '__main__':
    app.run(debug=True)
