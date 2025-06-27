# config_manager.py
import json

def load_rubricas():
    try:
        with open('rubricas.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Arquivo rubricas.json não encontrado. Criando estrutura vazia.")
        return {"rubricas": {"proventos": {}, "descontos": {}}}
    except json.JSONDecodeError as e:
        print(f"Erro no JSON na linha {e.lineno}, coluna {e.colno}: {e.msg}")
        print("Carregando estrutura vazia devido ao erro.")
        return {"rubricas": {"proventos": {}, "descontos": {}}}
