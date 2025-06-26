# app.py (VERSÃO SIMPLIFICADA E FUNCIONAL)

from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
import os
import fitz
import re
from processador_contracheque import ProcessadorContracheque

app = Flask(__name__)
app.secret_key = 'sua-chave-secreta-aqui'
app.config['UPLOAD_FOLDER'] = 'uploads'
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
    
    # Processa os textos e mantém na mesma página
    try:
        resultados = processador.processar_texto("\n".join(textos))
        return render_template('indexcalculadora.html', 
                            resultados=resultados,
                            arquivos_processados=True)
    except Exception as e:
        flash(f'Erro ao processar arquivos: {str(e)}')
        return redirect(url_for('calculadora'))
    
@app.route('/resultados')
def resultados():
    if 'texto_contracheques' not in session:
        return redirect(url_for('calculadora'))
    
    texto = session['texto_contracheques']
    
    # Extrair meses/anos presentes
    meses_anos = []
    padrao_mes_ano = r'(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\/(\d{4})'
    matches = re.findall(padrao_mes_ano, texto)
    
    for mes, ano in matches:
        meses_anos.append(f"{mes}/{ano}")
    
    if not meses_anos:
        flash('Nenhum mês/ano encontrado nos contracheques')
        return redirect(url_for('calculadora'))
    
    # Processar rubricas
    rubricas = processador.processar_texto(texto)
    
    # Calcular total de proventos
    total_proventos = sum(valor for cod, valor in rubricas.items() if cod in processador.codigos_proventos)
    
    return render_template('resultados.html',
                         meses_anos=meses_anos,
                         rubricas=rubricas,
                         total_proventos=total_proventos,
                         meses=MESES,
                         rubricas_detalhadas=processador.rubricas_detalhadas)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
