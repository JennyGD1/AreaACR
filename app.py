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
    if 'file' not in request.files:
        flash('Nenhum arquivo enviado', 'error')
        return redirect(url_for('calculadora'))
    
    file = request.files['file']
    if file.filename == '':
        flash('Nenhum arquivo selecionado', 'error')
        return redirect(url_for('calculadora'))
    
    if not file.filename.lower().endswith('.pdf'):
        flash('Apenas arquivos PDF são aceitos', 'error')
        return redirect(url_for('calculadora'))
    
    try:
        # Processa o arquivo diretamente da memória
        file_bytes = file.read()
        resultados = processador.processar_pdf(file_bytes)
        
        # Debug: Verifique os resultados no console
        print("Resultados do processamento:", resultados)
        
        if not resultados:
            flash('Nenhum dado encontrado no PDF', 'error')
            return redirect(url_for('calculadora'))
        
        session['resultados'] = resultados
        return redirect(url_for('analise_detalhada'), code=303)  # Código 303 para redirecionamento POST-GET
    
    except Exception as e:
        flash(f'Erro no processamento: {str(e)}', 'error')
        print("Erro detalhado:", str(e))
        return redirect(url_for('calculadora'))

@app.route('/analise')
def analise_detalhada():
    if 'resultados' not in session:
        flash('Sessão expirada ou resultados não encontrados', 'error')
        return redirect(url_for('calculadora'))
    
    resultados = session['resultados']
    return render_template('analise_detalhada.html', resultados=resultados)
    
    # Debug: verifique se os resultados chegam no template
    print("Resultados enviados para o template:", resultados)
    
    return render_template('analise_detalhada.html', 
                         resultados=resultados)

if __name__ == '__main__':
    app.run(debug=True)
