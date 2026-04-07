import sqlite3, os

def inspect(path):
    if not os.path.exists(path):
        print(f"NAO ENCONTRADO: {path}")
        return
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute("SELECT keyword FROM keywords_monitoradas WHERE ativa=1")
    kws = [r[0] for r in c.fetchall()]
    c.execute("SELECT chave, valor FROM config_sentinela")
    cfg = c.fetchall()
    c.execute("SELECT nome_produto, preco, ranking, data_verificacao FROM historico_precos ORDER BY data_verificacao DESC LIMIT 3")
    hist = c.fetchall()
    conn.close()
    print(f"\n=== {path} ===")
    print("Keywords:", kws)
    for chave, valor in cfg:
        if "token" in chave or "chat" in chave:
            print(f"  Config {chave}: {valor[:15]}...")
        else:
            print(f"  Config {chave}: {valor}")
    print("Historico (top3):", hist)

inspect("data/sentinela.db")
inspect("dist/data/sentinela.db")
