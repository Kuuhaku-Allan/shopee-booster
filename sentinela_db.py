import sqlite3
from datetime import datetime, timedelta
import os

DB_PATH = "data/sentinela.db"

def init_db():
    if not os.path.exists("data"):
        os.makedirs("data")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tabela para as keywords do seu nicho
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keywords_monitoradas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE,
            ativa INTEGER DEFAULT 1
        )
    ''')
    
    # Tabela de histórico (Onde o "sentinela" vê as mudanças)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historico_precos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT,
            shop_id TEXT,
            nome_produto TEXT,
            preco REAL,
            ranking INTEGER,
            data_verificacao DATETIME
        )
    ''')

    # Configurações do Telegram e da Sentinela
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config_sentinela (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def salvar_config(chave, valor):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO config_sentinela (chave, valor) VALUES (?, ?)", (chave, str(valor)))
    conn.commit()
    conn.close()

def obter_config(chave):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM config_sentinela WHERE chave = ?", (chave,))
        res = cursor.fetchone()
        conn.close()
        return res[0] if res else None
    except Exception:
        return None

def adicionar_keyword(keyword: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO keywords_monitoradas (keyword) VALUES (?)", (keyword.strip().lower(),))
    conn.commit()
    conn.close()

def listar_keywords() -> list:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT keyword FROM keywords_monitoradas WHERE ativa = 1")
        res = cursor.fetchall()
        conn.close()
        return [r[0] for r in res]
    except Exception:
        return []

def remover_keyword(keyword: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM keywords_monitoradas WHERE keyword = ?", (keyword.strip().lower(),))
    conn.commit()
    conn.close()

def salvar_historico(item_id, shop_id, nome_produto, preco, ranking):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO historico_precos (item_id, shop_id, nome_produto, preco, ranking, data_verificacao)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (str(item_id), str(shop_id), str(nome_produto), float(preco), int(ranking), datetime.now()))
    conn.commit()
    conn.close()

def _obter_preco_anterior(item_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT preco FROM historico_precos WHERE item_id = ? ORDER BY data_verificacao DESC LIMIT 1", (str(item_id),))
        res = cursor.fetchone()
        conn.close()
        return res[0] if res else None
    except Exception:
        return None

def processar_mudancas_e_alertar(keyword: str, resultados: list, telegram):
    # Percorre o top e processa mudancas
    from telegram_service import TelegramSentinela
    
    for i, p in enumerate(resultados):
        item_id = str(p.get("item_id", ""))
        nome = p.get("nome", "")
        preco_novo = float(p.get("preco", 0))
        ranking_atual = i + 1

        if not item_id: continue
        
        preco_antigo = _obter_preco_anterior(item_id)
        
        if preco_antigo is None:
            # Produto novo aparecendo pela primeira vez no nosso radar
            if ranking_atual <= 10:
                msg = TelegramSentinela.formatar_novo_concorrente(nome, preco_novo, ranking_atual)
                telegram.enviar_alerta(msg)
        else:
            # Produto existente, calcular mudanca
            diferenca = abs(preco_novo - preco_antigo)
            if preco_antigo > 0:
                porcentagem = (diferenca / preco_antigo) * 100
                if porcentagem >= 5.0: # SO AVISAR SE MUDOU MAIS DE 5% (Filtro Anti-Spam)
                    msg = TelegramSentinela.formatar_mudanca_preco(nome, preco_antigo, preco_novo)
                    telegram.enviar_alerta(msg)
        
        # Salva o novo snapshot (ou o repetido, para contabilizarmos ranking das lojas depois)
        salvar_historico(item_id, p.get("shop_id", ""), nome, preco_novo, ranking_atual)

def gerar_ranking_lojas_nicho():
    """
    Power Radar: agregacao avançada para o Rank das 100 melhores lojas do nicho.
    Inclui: presenças no topo, melhor posição já alcançada, preço médio e
    tendência de preço (comparação últimas 24h vs anteriores).
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Ranking principal
        cursor.execute('''
            SELECT shop_id,
                   COUNT(*) as presencas,
                   AVG(preco) as preco_medio,
                   MIN(ranking) as melhor_posicao,
                   MAX(ranking) as pior_posicao
            FROM historico_precos
            GROUP BY shop_id
            ORDER BY presencas DESC, melhor_posicao ASC
            LIMIT 100
        ''')
        ranking = cursor.fetchall()

        # Tendência de preço por loja (últimas 24h vs geral)
        agora = datetime.now()
        vinte_quatroh = agora - timedelta(hours=24)

        resultado = []
        for shop_id, presencas, preco_medio, melhor_pos, pior_pos in ranking:
            # Preço médio nas últimas 24h
            cursor.execute('''
                SELECT AVG(preco) FROM historico_precos
                WHERE shop_id = ? AND data_verificacao >= ?
            ''', (str(shop_id), vinte_quatroh.isoformat()))
            res_rec = cursor.fetchone()
            preco_recente = res_rec[0] if res_rec[0] is not None else None

            # Tendência
            if preco_recente is not None and preco_medio > 0:
                diff_pct = ((preco_recente - preco_medio) / preco_medio) * 100
                if diff_pct > 2:
                    tendencia = "SUBINDO"
                elif diff_pct < -2:
                    tendencia = "Caindo"
                else:
                    tendencia = "ESTÁVEL"
            else:
                tendencia = "— dados insuficientes —"

            resultado.append({
                "shop_id": shop_id,
                "presencas": presencas,
                "preco_medio": round(preco_medio, 2),
                "melhor_posicao": melhor_pos,
                "pior_posicao": pior_pos,
                "preco_recente": round(preco_recente, 2) if preco_recente is not None else None,
                "tendencia": tendencia,
            })

        conn.close()
        return resultado
    except Exception:
        return []

def obter_ultimo_preco(item_id):
    """Busca o preço da última verificação para comparar (o 'Diff')."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT preco FROM historico_precos WHERE item_id = ? ORDER BY data_verificacao DESC LIMIT 1", (str(item_id),))
        res = cursor.fetchone()
        conn.close()
        return res[0] if res else None
    except Exception:
        return None

def configurar_loja_mestre(url_loja: str):
    """Salva a URL da loja mestra para identificação da Sentinela."""
    salvar_config("minha_loja_url", url_loja.strip())

def obter_loja_mestra() -> str | None:
    """Recupera a URL da loja mestra salva."""
    return obter_config("minha_loja_url")

def gerar_tendencia_precos_nicho(dias: int = 7):
    """
    Retorna a série temporal do preço médio do nicho nos últimos N dias.
    Usado para exibir o gráfico de tendência no app.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        limite = datetime.now() - timedelta(days=dias)
        cursor.execute('''
            SELECT DATE(data_verificacao) as dia, AVG(preco) as preco_medio
            FROM historico_precos
            WHERE data_verificacao >= ?
            GROUP BY DATE(data_verificacao)
            ORDER BY dia ASC
        ''', (limite.isoformat(),))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception:
        return []
