"""
scripts/radar_debug_app_visibility.py - Diagnóstico de visibilidade do radar.db

Verifica se o app consegue encontrar e ler os produtos do Radar corretamente.
"""

import os
import sys
from pathlib import Path

# Adicionar raiz do projeto ao path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

print("=" * 80)
print("DIAGNÓSTICO DE VISIBILIDADE DO RADAR.DB")
print("=" * 80)
print()

# 1. Verificar diretório atual
print("1. DIRETÓRIO ATUAL")
print(f"   cwd: {os.getcwd()}")
print(f"   __file__: {__file__}")
print(f"   PROJECT_ROOT: {PROJECT_ROOT}")
print()

# 2. Verificar caminho do radar.db
print("2. CAMINHO DO RADAR.DB")
from shopee_core.radar_db import DB_PATH, get_connection

print(f"   DB_PATH: {DB_PATH}")
print(f"   DB_PATH absoluto: {DB_PATH.resolve()}")
print(f"   Arquivo existe: {DB_PATH.exists()}")
if DB_PATH.exists():
    size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    print(f"   Tamanho: {size_mb:.2f} MB")
else:
    print("   ⚠️ ARQUIVO NÃO EXISTE!")
print()

# 3. Verificar variável de ambiente
print("3. VARIÁVEL DE AMBIENTE")
env_path = os.getenv("SHOPEE_RADAR_DB_PATH")
if env_path:
    print(f"   SHOPEE_RADAR_DB_PATH: {env_path}")
else:
    print("   SHOPEE_RADAR_DB_PATH: (não definida)")
print()

# 4. Verificar conteúdo do banco
print("4. CONTEÚDO DO BANCO")
if not DB_PATH.exists():
    print("   ⚠️ Banco não existe, pulando verificação")
else:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Total de produtos
        cursor.execute("SELECT COUNT(*) FROM radar_products")
        total_products = cursor.fetchone()[0]
        print(f"   Total de radar_products: {total_products}")
        
        # Total de pattern reports
        cursor.execute("SELECT COUNT(*) FROM radar_pattern_reports")
        total_reports = cursor.fetchone()[0]
        print(f"   Total de radar_pattern_reports: {total_reports}")
        
        # Produtos own_product
        cursor.execute("SELECT COUNT(*) FROM radar_products WHERE source_type = 'own_product'")
        own_products = cursor.fetchone()[0]
        print(f"   Produtos own_product: {own_products}")
        
        # Produtos com pattern reports
        cursor.execute("""
            SELECT COUNT(DISTINCT p.product_uid)
            FROM radar_products p
            INNER JOIN radar_pattern_reports r ON p.product_uid = r.own_product_uid
        """)
        products_with_reports = cursor.fetchone()[0]
        print(f"   Produtos com pattern reports: {products_with_reports}")
        
        # Produtos own_product com pattern reports
        cursor.execute("""
            SELECT COUNT(DISTINCT p.product_uid)
            FROM radar_products p
            INNER JOIN radar_pattern_reports r ON p.product_uid = r.own_product_uid
            WHERE p.source_type = 'own_product'
        """)
        own_with_reports = cursor.fetchone()[0]
        print(f"   Produtos own_product com pattern reports: {own_with_reports}")
        
        conn.close()
        print()
        
    except Exception as e:
        print(f"   ❌ Erro ao ler banco: {e}")
        print()

# 5. Verificar list_radar_products_for_audit()
print("5. SAÍDA DE list_radar_products_for_audit()")
try:
    from shopee_core.radar_ui_service import list_radar_products_for_audit
    
    products = list_radar_products_for_audit(limit=100)
    print(f"   Total retornado: {len(products)}")
    
    if products:
        print(f"   Produtos listados:")
        for i, p in enumerate(products[:5], 1):
            print(f"      {i}. {p['product_uid'][:8]}... - {p['title'][:50]} - can_use={p['can_use']}")
        if len(products) > 5:
            print(f"      ... e mais {len(products) - 5} produtos")
    else:
        print("   ⚠️ NENHUM PRODUTO RETORNADO!")
    print()
    
except Exception as e:
    print(f"   ❌ Erro ao chamar list_radar_products_for_audit: {e}")
    import traceback
    traceback.print_exc()
    print()

# 6. Verificar produto específico: 2777bd10-5e4f-40ff-b302-81d23f8834d9
print("6. VERIFICAR PRODUTO ESPECÍFICO: 2777bd10-5e4f-40ff-b302-81d23f8834d9")
test_uid = "2777bd10-5e4f-40ff-b302-81d23f8834d9"

if not DB_PATH.exists():
    print("   ⚠️ Banco não existe, pulando verificação")
else:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Verificar se produto existe
        cursor.execute("SELECT * FROM radar_products WHERE product_uid = ?", (test_uid,))
        product = cursor.fetchone()
        
        if product:
            print(f"   ✅ Produto encontrado no banco")
            print(f"      source_type: {product['source_type']}")
            print(f"      status: {product['status']}")
            print(f"      title: {product['title'][:60] if product['title'] else 'N/A'}")
            print(f"      price: R$ {product['price']:.2f}" if product['price'] else "      price: N/A")
            
            # Verificar pattern report
            cursor.execute("SELECT * FROM radar_pattern_reports WHERE own_product_uid = ?", (test_uid,))
            report = cursor.fetchone()
            
            if report:
                print(f"   ✅ Pattern report encontrado")
                print(f"      direct_count: {report['direct_count']}")
                print(f"      price_avg: R$ {report['price_avg']:.2f}" if report['price_avg'] else "      price_avg: N/A")
            else:
                print(f"   ⚠️ Pattern report NÃO encontrado")
        else:
            print(f"   ⚠️ Produto NÃO encontrado no banco")
        
        conn.close()
        print()
        
    except Exception as e:
        print(f"   ❌ Erro ao verificar produto: {e}")
        print()

# 7. Verificar get_radar_audit_context_status()
print("7. STATUS DO CONTEXTO DE AUDITORIA")
try:
    from shopee_core.radar_audit_context_service import get_radar_audit_context_status
    
    status = get_radar_audit_context_status(test_uid)
    print(f"   can_use: {status['can_use']}")
    print(f"   confidence: {status['confidence']}")
    print(f"   direct_count: {status['direct_count']}")
    print(f"   has_pattern_report: {status['has_pattern_report']}")
    if status['warnings']:
        print(f"   warnings: {status['warnings']}")
    print()
    
except Exception as e:
    print(f"   ❌ Erro ao verificar status: {e}")
    import traceback
    traceback.print_exc()
    print()

# 8. Verificar filtros de list_radar_products_for_audit()
print("8. ANÁLISE DE FILTROS")
if not DB_PATH.exists():
    print("   ⚠️ Banco não existe, pulando análise")
else:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Produtos own_product
        cursor.execute("SELECT COUNT(*) FROM radar_products WHERE source_type = 'own_product'")
        own_count = cursor.fetchone()[0]
        print(f"   Produtos own_product: {own_count}")
        
        # Produtos own_product com status=collected
        cursor.execute("SELECT COUNT(*) FROM radar_products WHERE source_type = 'own_product' AND status = 'collected'")
        collected_count = cursor.fetchone()[0]
        print(f"   Produtos own_product + status=collected: {collected_count}")
        
        # Produtos own_product com pattern report
        cursor.execute("""
            SELECT COUNT(DISTINCT p.product_uid)
            FROM radar_products p
            INNER JOIN radar_pattern_reports r ON p.product_uid = r.own_product_uid
            WHERE p.source_type = 'own_product'
        """)
        with_report_count = cursor.fetchone()[0]
        print(f"   Produtos own_product + pattern report: {with_report_count}")
        
        # Produtos own_product com pattern report e direct_count >= 3
        cursor.execute("""
            SELECT COUNT(DISTINCT p.product_uid)
            FROM radar_products p
            INNER JOIN radar_pattern_reports r ON p.product_uid = r.own_product_uid
            WHERE p.source_type = 'own_product' AND r.direct_count >= 3
        """)
        usable_count = cursor.fetchone()[0]
        print(f"   Produtos own_product + pattern report + direct_count >= 3: {usable_count}")
        
        # Listar produtos own_product com detalhes
        cursor.execute("""
            SELECT p.product_uid, p.title, p.status, r.direct_count
            FROM radar_products p
            LEFT JOIN radar_pattern_reports r ON p.product_uid = r.own_product_uid
            WHERE p.source_type = 'own_product'
            ORDER BY r.direct_count DESC NULLS LAST
            LIMIT 10
        """)
        products = cursor.fetchall()
        
        if products:
            print(f"\n   Produtos own_product encontrados:")
            for p in products:
                uid = p['product_uid'][:8]
                title = (p['title'][:40] + "...") if p['title'] and len(p['title']) > 40 else (p['title'] or "N/A")
                status = p['status']
                direct = p['direct_count'] if p['direct_count'] is not None else 0
                can_use = "✅" if p['direct_count'] and p['direct_count'] >= 3 else "❌"
                print(f"      {can_use} {uid}... - {title} - status={status} - direct={direct}")
        
        conn.close()
        print()
        
    except Exception as e:
        print(f"   ❌ Erro ao analisar filtros: {e}")
        import traceback
        traceback.print_exc()
        print()

# 9. Resumo e recomendações
print("=" * 80)
print("RESUMO E RECOMENDAÇÕES")
print("=" * 80)

if not DB_PATH.exists():
    print("❌ PROBLEMA: radar.db não existe no caminho esperado")
    print(f"   Caminho esperado: {DB_PATH.resolve()}")
    print()
    print("SOLUÇÃO:")
    print("   1. Verificar se o banco está em outro local")
    print("   2. Definir variável de ambiente SHOPEE_RADAR_DB_PATH")
    print("   3. Ou copiar o banco para o caminho esperado")
else:
    try:
        from shopee_core.radar_ui_service import list_radar_products_for_audit
        products = list_radar_products_for_audit(limit=100)
        
        if len(products) == 0:
            print("❌ PROBLEMA: Banco existe mas list_radar_products_for_audit() retorna vazio")
            print()
            print("POSSÍVEIS CAUSAS:")
            print("   1. Nenhum produto com source_type='own_product'")
            print("   2. Nenhum produto com pattern report")
            print("   3. Nenhum produto com direct_count >= 3")
            print("   4. Filtro de status muito restritivo")
            print()
            print("SOLUÇÃO:")
            print("   1. Verificar filtros em radar_ui_service.py")
            print("   2. Ajustar critério de can_use")
            print("   3. Permitir produtos com pattern report independente do status")
        else:
            print(f"✅ SUCESSO: {len(products)} produtos disponíveis para auditoria")
            print()
            print("PRÓXIMOS PASSOS:")
            print("   1. Testar no app.py local")
            print("   2. Verificar se selectbox mostra os produtos")
            print("   3. Recompilar o .exe")
    except Exception as e:
        print(f"❌ ERRO ao executar diagnóstico: {e}")

print()
print("=" * 80)
