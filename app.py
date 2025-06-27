from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_session import Session
from werkzeug.utils import secure_filename
import os
from processador_contracheque import ProcessadorContracheque

# Configuração do Flask
app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'  # Em produção, use uma chave segura e variável de ambiente

# Configurações
app.config.update(
    SESSION_TYPE='filesystem',
    UPLOAD_FOLDER=os.path.join('tmp', 'uploads'),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB
    SESSION_FILE_DIR=os.path.join('tmp', 'flask_session')
)

# Garante que os diretórios existam
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
    """Rota para a calculadora ACR"""
    return render_template('indexcalculadora.html')

@app.route('/upload', methods=['POST'])
def upload():
    """Processa o upload do arquivo PDF"""
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
        
        if not resultados or not resultados.get('dados_mensais'):
            flash('Nenhum dado válido encontrado no PDF', 'error')
            return redirect(url_for('calculadora'))
        
        session['resultados'] = resultados
        return redirect(url_for('analise_detalhada'))
    
    except Exception as e:
        flash(f'Erro no processamento: {str(e)}', 'error')
        app.logger.error(f"Erro no processamento: {str(e)}", exc_info=True)
        return redirect(url_for('calculadora'))

@app.route('/analise')
def analise_detalhada():
    """Exibe a análise detalhada dos contracheques processados"""
    resultados = session.get('resultados')
    
    if not resultados:
        flash('Nenhum dado de análise disponível. Por favor, envie um arquivo primeiro.', 'error')
        return redirect(url_for('calculadora'))
    
    try:
        total_geral = resultados.get('total_geral', {})
        total_proventos = total_geral.get('total_proventos', 0)
        total_descontos = total_geral.get('total_descontos', 0)
        
        return render_template(
            'analise_detalhada.html',
            resultados=resultados,
            total_proventos=total_proventos,
            total_descontos=total_descontos
        )
    except Exception as e:
        app.logger.error(f"Erro na análise detalhada: {str(e)}", exc_info=True)
        flash('Ocorreu um erro ao gerar a análise detalhada', 'error')
        return redirect(url_for('calculadora'))

if __name__ == '__main__':
    app.run(debug=True)
