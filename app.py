# app.py - VERSÃO FINAL, COMPLETA E COM INDENTAÇÃO CORRIGIDA

import fitz
import re
import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from datetime import datetime
from processador_contracheque import ProcessadorContracheque
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)
app.secret_key = 'sua-chave-secreta-aqui'

# Configuração do logger
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('app.log', maxBytes=100000, backupCount=3),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Dicionário de meses
MESES_ORDEM = {
    'Janeiro': 1, 'Fevereiro': 2, 'Março': 3, 'Abril': 4,
    'Maio': 5, 'Junho': 6, 'Julho': 7, 'Agosto': 8,
    'Setembro': 9, 'Outubro': 10, 'Novembro': 11, 'Dezembro': 12,
    'JAN': 1, 'FEV': 2, 'MAR': 3, 'ABR': 4, 'MAI': 5, 'JUN': 6,
    'JUL': 7, 'AGO': 8, 'SET': 9, 'OUT': 10, 'NOV': 11, 'DEZ': 12
}

# Configurações do app
UPLOAD_FOLDER = '/tmp/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config.update({
    'UPLOAD_FOLDER': UPLOAD_FOLDER,
    'MAX_CONTENT_LENGTH': 100 * 1024 * 1024,
    'ALLOWED_EXTENSIONS': {'pdf'},
})

# Instância do processador
processador = ProcessadorContracheque('config.json')

# --- FUNÇÕES AUXILIARES ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extrair_mes_ano_do_texto(texto_pagina):
    padrao_mes_ano = r'(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro|JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)\s*[/.-]?\s*(\d{4})'
    match = re.search(padrao_mes_ano, texto_pagina, re.IGNORECASE)
    if match:
        mes_nome = match.group(1).capitalize()
        ano = match.group(2)
        mes_num = MESES_ORDEM.get(mes_nome[:3].upper())
        # Encontra o nome completo do mês para padronização
        for nome_completo, num in MESES_ORDEM.items():
            if num == mes_num and len(nome_completo) > 3:
                return f"{nome_completo} {ano}", ano
    logger.warning("Mês/Ano não encontrado no texto da página.")
    return "Período não identificado", None

def processar_pdf(caminho_pdf):
    """
    Processa o PDF usando a lógica centralizada do ProcessadorContracheque.
    """
    try:
        doc = fitz.open(caminho_pdf)
        resultados_por_pagina = []
        
        campos_obrigatorios = [
            'titular', 'conjuge', 'dependente', 'agregado_jovem',
            'agregado_maior', 'plano_especial', 'coparticipacao',
            'retroativo', 'parcela_risco_titular', 'parcela_risco_dependente',
            'parcela_risco_conjuge', 'parcela_risco_agregado'
        ]

        for page_num, page in enumerate(doc):
            texto_pagina = page.get_text("text")
            logger.debug(f"Processando Página {page_num + 1} do arquivo {os.path.basename(caminho_pdf)}")
            
            mes_ano_encontrado, _ = extrair_mes_ano_do_texto(texto_pagina)
            
            tipo_contracheque = processador.identificar_tipo(texto_pagina)
            logger.info(f"Arquivo '{os.path.basename(caminho_pdf)}' identificado como: '{tipo_contracheque}'")
            
            dados_extraidos = processador.extrair_dados(texto_pagina, tipo_contracheque)
            
            valores_pagina = {campo: 0.0 for campo in campos_obrigatorios}
            valores_pagina.update(dados_extraidos)

            resultados_por_pagina.append((mes_ano_encontrado, valores_pagina))
            
        return resultados_por_pagina

    except Exception as e:
        logger.error(f"Erro ao processar PDF {caminho_pdf}: {str(e)}", exc_info=True)
        return []

# --- ROTAS DA APLICAÇÃO ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calculadora')
def calculadora_index():
    session.clear()
    return render_template('indexcalculadora.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'files' not in request.files:
        flash('Nenhum arquivo selecionado')
        return redirect(url_for('calculadora_index'))

    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        flash('Nenhum arquivo selecionado')
        return redirect(url_for('calculadora_index'))

    resultados_por_ano = {}
    erros = []
    arquivos_processados_count = 0 
    
    campos_base = [ 
        'titular', 'conjuge', 'dependente',
        'agregado_jovem', 'agregado_maior',
        'plano_especial', 'coparticipacao',
        'retroativo', 'parcela_risco_titular', 'parcela_risco_dependente', 
        'parcela_risco_conjuge', 'parcela_risco_agregado'
    ]

    for file in files:
        if file.filename == '' or not allowed_file(file.filename):
            continue

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        arquivo_teve_erro = False 

        try:
            file.save(filepath)
            logger.info(f"Arquivo salvo: {filepath}")

            resultados_pagina = processar_pdf(filepath) 

            if resultados_pagina:
                arquivos_processados_count += 1
                for mes_ano_str, valores_pagina in resultados_pagina:
                    if mes_ano_str != "Período não identificado":
                        try:
                            ano = mes_ano_str.split()[-1]
                            if not ano.isdigit() or len(ano) != 4:
                                raise ValueError("Ano inválido extraído")

                            if ano not in resultados_por_ano:
                                resultados_por_ano[ano] = {
                                    'geral': {campo: 0.0 for campo in campos_base},
                                    'total_ano': 0.0,
                                    'detalhes_mensais': []
                                }

                            total_pagina = 0.0
                            for campo, valor in valores_pagina.items():
                                if campo in resultados_por_ano[ano]['geral']:
                                    resultados_por_ano[ano]['geral'][campo] += valor
                                    total_pagina += valor
                                else:
                                    logger.warning(f"Campo '{campo}' da pág/mês {mes_ano_str} (arq: {filename}) não encontrado na estrutura do ano {ano}.")

                            resultados_por_ano[ano]['total_ano'] += total_pagina 

                            resultados_por_ano[ano]['detalhes_mensais'].append({
                                'mes': mes_ano_str,
                                'arquivo': filename,
                                'valores': valores_pagina
                            })

                        except (IndexError, ValueError) as e:
                            logger.error(f"Não foi possível extrair/validar o ano de '{mes_ano_str}' (arq: '{filename}'). Erro: {e}")
                            if not arquivo_teve_erro:
                                erros.append(f"{filename} (dados inválidos: {mes_ano_str})")
                                arquivo_teve_erro = True
                    else:
                        logger.warning(f"Mês/Ano não identificado em uma página do arquivo: {filename}")
                        if not arquivo_teve_erro:
                            erros.append(f"{filename} (período não identificado)")
                            arquivo_teve_erro = True
            else:
                logger.error(f"Falha ao processar PDF (retorno vazio): {filename}")
                if not arquivo_teve_erro:
                    erros.append(f"{filename} (falha no processamento)")
                    arquivo_teve_erro = True
        except Exception as e:
            logger.error(f"Erro GERAL no loop de upload para o arquivo {filename}: {str(e)}", exc_info=True)
            if not arquivo_teve_erro:
                erros.append(f"{filename} (erro inesperado)")
            if os.path.exists(filepath):
                try: os.remove(filepath)
                except OSError as re: logger.error(f"Erro ao remover {filepath} após erro: {re}")

    if not resultados_por_ano and arquivos_processados_count == 0:
        if erros:
            flash(f'Falha ao processar todos os arquivos enviados. Erros: {"; ".join(erros)}', 'error')
        else:
            flash('Nenhum arquivo PDF válido encontrado ou processado.', 'warning')
        return redirect(url_for('calculadora_index'))

    session['resultados_por_ano'] = resultados_por_ano
    session['erros'] = list(set(erros))

    if session['erros']:
        flash(f'Processamento concluído com {len(session["erros"])} erro(s). Verifique os detalhes. Arquivos com erro: {", ".join(session["erros"])}', 'warning')

    return redirect(url_for('mostrar_resultados'))

@app.route('/resultados')
def mostrar_resultados():
    if 'resultados_por_ano' not in session:
        flash('Nenhum resultado encontrado. Por favor, faça o upload dos arquivos primeiro.', 'warning')
        return redirect(url_for('calculadora_index'))

    resultados_por_ano = session.get('resultados_por_ano', {})
    erros_proc = session.get('erros', []) 
    
    total_geral_calculado = 0.0
    for ano, dados_ano in resultados_por_ano.items():
        if ano.isdigit() and len(ano) == 4:
            total_geral_calculado += dados_ano.get('total_ano', 0.0)

    anos_ordenados = sorted([a for a in resultados_por_ano.keys() if a.isdigit()], key=int, reverse=True)
    outros_anos = sorted([a for a in resultados_por_ano.keys() if not a.isdigit()])
    chaves_ordenadas = anos_ordenados + outros_anos
    resultados_por_ano_ordenado = {chave: resultados_por_ano[chave] for chave in chaves_ordenadas}

    return render_template('resultado.html',
                           resultados_por_ano=resultados_por_ano_ordenado,
                           total_geral=total_geral_calculado,
                           erros_processamento=erros_proc,
                           now=datetime.now())

@app.route('/detalhes')
def detalhes_mensais():
    if 'resultados_por_ano' not in session:
        return redirect(url_for('calculadora_index'))

    resultados_por_ano = session['resultados_por_ano']
    detalhes = []
    anos_disponiveis = set()

    for ano, dados_ano in resultados_por_ano.items():
        anos_disponiveis.add(ano)
        for detalhe_mensal in dados_ano.get('detalhes_mensais', []):
            detalhe_mensal['ano'] = ano
            detalhes.append(detalhe_mensal)

    erros_proc = session.get('erros', [])
    resultados_validos = []
    resultados_invalidos = []

    for r in detalhes:
        mes_str = r.get('mes', 'Período não identificado')
        if mes_str == 'Período não identificado':
            resultados_invalidos.append(r)
            continue

        try:
            partes = mes_str.split()
            mes_nome = partes[0]
            ano = int(partes[1])
            mes_num = 13 
            for nome_map, num_map in MESES_ORDEM.items():
                if mes_nome.lower() == nome_map.lower():
                    mes_num = num_map
                    break
            if mes_num != 13:
                resultados_validos.append((ano, mes_num, r))
            else:
                logger.warning(f"Não foi possível mapear o mês '{mes_nome}' para um número.")
                resultados_invalidos.append(r)

        except (ValueError, IndexError, TypeError) as e:
            logger.error(f"Erro ao parsear/ordenar mês '{mes_str}' do arquivo {r.get('arquivo')}: {e}")
            resultados_invalidos.append(r)

    resultados_ordenados = [r for _, _, r in sorted(resultados_validos, key=lambda x: (x[0], x[1]))]
    resultados_ordenados += resultados_invalidos

    return render_template('detalhes_mes.html',
                           resultados=resultados_ordenados,
                           anos_disponiveis=sorted(list(anos_disponiveis), reverse=True),
                           erros_processamento=erros_proc,
                           now=datetime.now())


if __name__ == '__main__':
    app.run(debug=True)
