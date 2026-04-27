"""
test_telegram_sentinel.py — Teste do Telegram com Sentinela
===========================================================
Script para testar envio de relatórios do Sentinela para o Telegram.
"""

from datetime import datetime
from telegram_service import TelegramSentinela
from shopee_core.sentinel_report_service import generate_sentinel_report

# Dados simulados do Sentinela
resultado_simulado = {
    "ok": True,
    "loja": "totalmenteseu",
    "keyword": "mochila infantil princesa",
    "concorrentes": [
        {
            "titulo": "Mochila Infantil Princesa Rosa com Glitter",
            "preco": 49.90,
            "loja": "loja_concorrente_1",
            "url": "https://shopee.com.br/...",
            "ranking": 1,
            "is_new": True
        },
        {
            "titulo": "Mochila Escolar Princesa Frozen Elsa",
            "preco": 67.50,
            "loja": "loja_concorrente_2",
            "url": "https://shopee.com.br/...",
            "ranking": 2,
            "is_new": False
        },
        {
            "titulo": "Mochila Infantil Princesa Sofia 3D",
            "preco": 89.90,
            "loja": "loja_concorrente_3",
            "url": "https://shopee.com.br/...",
            "ranking": 3,
            "is_new": True
        },
        {
            "titulo": "Mochila Princesa Cinderela com Rodinhas",
            "preco": 129.90,
            "loja": "loja_concorrente_4",
            "url": "https://shopee.com.br/...",
            "ranking": 4,
            "is_new": False
        },
        {
            "titulo": "Mochila Infantil Princesa Rapunzel",
            "preco": 75.00,
            "loja": "loja_concorrente_5",
            "url": "https://shopee.com.br/...",
            "ranking": 5,
            "is_new": False
        },
    ],
    "novos_concorrentes": [
        {
            "titulo": "Mochila Infantil Princesa Rosa com Glitter",
            "preco": 49.90,
            "ranking": 1,
        },
        {
            "titulo": "Mochila Infantil Princesa Sofia 3D",
            "preco": 89.90,
            "ranking": 3,
        },
    ],
    "total_analisado": 5,
    "preco_medio": 82.44,
    "menor_preco": 49.90,
    "maior_preco": 129.90,
    "seu_preco": 95.00,
    "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
}


def test_telegram_connection():
    """Teste 1: Conexão básica"""
    print("=" * 60)
    print("TESTE 1: Conexão com Telegram")
    print("=" * 60)
    
    telegram = TelegramSentinela()
    success = telegram.testar_conexao()
    
    if success:
        print("✅ Conexão OK - Mensagem de teste enviada")
    else:
        print("❌ Falha na conexão")
    
    return success


def test_telegram_message():
    """Teste 2: Mensagem formatada"""
    print("\n" + "=" * 60)
    print("TESTE 2: Mensagem Formatada")
    print("=" * 60)
    
    telegram = TelegramSentinela()
    
    mensagem = (
        "🧪 <b>Teste de Formatação HTML</b>\n\n"
        "Este é um teste de <b>negrito</b> e <i>itálico</i>.\n\n"
        "Lista:\n"
        "• Item 1\n"
        "• Item 2\n"
        "• Item 3\n\n"
        "<code>Código monospace</code>"
    )
    
    success = telegram.enviar_mensagem(mensagem)
    
    if success:
        print("✅ Mensagem formatada enviada")
    else:
        print("❌ Falha ao enviar mensagem")
    
    return success


def test_telegram_report():
    """Teste 3: Relatório completo do Sentinela"""
    print("\n" + "=" * 60)
    print("TESTE 3: Relatório Completo do Sentinela")
    print("=" * 60)
    
    # Gera relatório
    print("Gerando gráfico e tabela...")
    report = generate_sentinel_report(
        resultado_simulado,
        include_chart=True,
        include_csv=True,
        include_table_png=False
    )
    
    print(f"  Gráfico: {report['chart_path']}")
    print(f"  CSV: {report['csv_path']}")
    
    # Envia para Telegram
    print("\nEnviando para Telegram...")
    telegram = TelegramSentinela()
    success = telegram.enviar_relatorio_sentinela(
        resultado_simulado,
        chart_path=report["chart_path"],
        table_path=report["csv_path"]
    )
    
    if success:
        print("✅ Relatório completo enviado")
    else:
        print("❌ Falha ao enviar relatório")
    
    return success


def test_telegram_alerts():
    """Teste 4: Alertas específicos"""
    print("\n" + "=" * 60)
    print("TESTE 4: Alertas Específicos")
    print("=" * 60)
    
    telegram = TelegramSentinela()
    
    # Alerta de mudança de preço
    print("Enviando alerta de mudança de preço...")
    msg_preco = TelegramSentinela.formatar_mudanca_preco(
        "Mochila Infantil Princesa Rosa",
        89.90,
        49.90
    )
    success1 = telegram.enviar_mensagem(msg_preco)
    
    # Alerta de novo concorrente
    print("Enviando alerta de novo concorrente...")
    msg_novo = TelegramSentinela.formatar_novo_concorrente(
        "Mochila Infantil Princesa Sofia 3D",
        89.90,
        3
    )
    success2 = telegram.enviar_mensagem(msg_novo)
    
    if success1 and success2:
        print("✅ Alertas enviados")
    else:
        print("❌ Falha ao enviar alertas")
    
    return success1 and success2


if __name__ == "__main__":
    print("\n🧪 TESTE DO TELEGRAM SENTINELA\n")
    
    results = []
    
    # Executa testes
    results.append(("Conexão", test_telegram_connection()))
    results.append(("Mensagem Formatada", test_telegram_message()))
    results.append(("Relatório Completo", test_telegram_report()))
    results.append(("Alertas Específicos", test_telegram_alerts()))
    
    # Resumo
    print("\n" + "=" * 60)
    print("RESUMO DOS TESTES")
    print("=" * 60)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
    
    total = len(results)
    passed = sum(1 for _, s in results if s)
    
    print(f"\nTotal: {passed}/{total} testes passaram")
    
    if passed == total:
        print("\n🎉 Todos os testes passaram!")
    else:
        print(f"\n⚠️ {total - passed} teste(s) falharam")
