from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
import os
import fitz
import re
from processador_contracheque import ProcessadorContracheque

# Configuração do Flask
app = Flask(__name__)
app.secret_key = 'sua-chave-secreta-aqui'  # Use uma chave segura em produção
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SESSION_COOKIE_MAX_SIZE'] = 4093  # Tamanho máximo do cookie
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hora

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
    if 'files' not in request.files:
        flash('Nenhum arquivo enviado')
        return redirect(url_for('calculadora'))
    
    arquivos = request.files.getlist('files')
    textos = []
    
    for arquivo in arquivos:
        if arquivo.filename == '':
            continue
            
        if arquivo and arquivo.filename.lower().endswith('.pdf'):
            caminho = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(arquivo.filename))
            arquivo.save(caminho)
            
            try:
                doc = fitz.open(caminho)
                texto = ""
                for pagina in doc:
                    texto += pagina.get_text()
                textos.append(texto)
            except Exception as e:
                flash(f'Erro ao ler PDF {arquivo.filename}: {str(e)}')
            finally:
                os.remove(caminho)
    
    if not textos:
        flash('Nenhum texto válido extraído dos PDFs')
        return redirect(url_for('calculadora'))
    
    try:
        resultados = processador.processar_texto("\n".join(textos))
        
        # Armazena apenas os dados essenciais na sessão
        session['resultados'] = {
            codigo: valor for codigo, valor in resultados.items()
        }
        session['total_proventos'] = sum(
            valor for cod, valor in resultados.items() 
            if cod in processador.codigos_proventos
        )
        session['total_descontos'] = sum(
            valor for cod, valor in resultados.items() 
            if cod not in processador.codigos_proventos
        )
        
        return redirect(url_for('analise_detalhada'))
        
    except Exception as e:
        flash(f'Erro ao processar arquivos: {str(e)}')
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
