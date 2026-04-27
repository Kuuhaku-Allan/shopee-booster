"""
Test script para verificar geração de relatório a partir do último sentinel_run
"""
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shopee_core.bot_state import get_latest_sentinel_run
from shopee_core.sentinel_report_service import generate_sentinel_report

def test_report_generation():
    """Testa geração de relatório a partir do último run"""
    
    user_id = "5511988600050@s.whatsapp.net"
    shop_uid = "8de0c133-f9b3-475b-bf68-cd59be13f461"
    
    print("=" * 60)
    print("TESTE: Geração de Relatório do Sentinela")
    print("=" * 60)
    
    # 1. Carrega último run
    print("\n1. Carregando último sentinel_run...")
    run = get_latest_sentinel_run(user_id, shop_uid)
    
    if not run:
        print("❌ Nenhum sentinel_run encontrado")
        return
    
    print(f"✅ Run encontrado: {run['run_id']}")
    print(f"   Status: {run['status']}")
    print(f"   Created: {run['created_at']}")
    
    # 2. Verifica resultado
    print("\n2. Verificando resultado...")
    resultado = run.get("resultado", {})
    
    print(f"   Keys: {list(resultado.keys())}")
    print(f"   Loja: {resultado.get('loja')}")
    print(f"   Keyword: {resultado.get('keyword')}")
    print(f"   Total analisado: {resultado.get('total_analisado')}")
    
    concorrentes = resultado.get("concorrentes", [])
    print(f"   Concorrentes: {len(concorrentes)}")
    
    if concorrentes:
        print(f"\n   Primeiro concorrente:")
        primeiro = concorrentes[0]
        for key, value in primeiro.items():
            print(f"     {key}: {value}")
    
    # 3. Verifica paths salvos
    print("\n3. Verificando paths salvos no banco...")
    print(f"   chart_path: {run.get('chart_path')}")
    print(f"   table_csv_path: {run.get('table_csv_path')}")
    print(f"   table_png_path: {run.get('table_png_path')}")
    
    # 4. Tenta gerar relatório
    print("\n4. Gerando relatório...")
    try:
        report = generate_sentinel_report(
            resultado,
            include_chart=True,
            include_csv=True,
            include_table_png=True
        )
        
        print(f"✅ Relatório gerado:")
        print(f"   chart_path: {report.get('chart_path')}")
        print(f"   csv_path: {report.get('csv_path')}")
        print(f"   table_png_path: {report.get('table_png_path')}")
        
        # 5. Verifica se arquivos existem
        print("\n5. Verificando se arquivos existem no disco...")
        
        chart_path = report.get('chart_path')
        if chart_path:
            exists = Path(chart_path).exists()
            print(f"   chart: {exists} ({chart_path})")
        else:
            print(f"   chart: ❌ path vazio")
        
        csv_path = report.get('csv_path')
        if csv_path:
            exists = Path(csv_path).exists()
            print(f"   csv: {exists} ({csv_path})")
        else:
            print(f"   csv: ❌ path vazio")
        
        png_path = report.get('table_png_path')
        if png_path:
            exists = Path(png_path).exists()
            print(f"   png: {exists} ({png_path})")
        else:
            print(f"   png: ❌ path vazio")
        
        # 6. Diagnóstico
        print("\n6. Diagnóstico:")
        if len(concorrentes) > 0 and not chart_path:
            print("   ❌ ERRO: Concorrentes existem mas chart_path está vazio")
            print("   Causa provável: Problema na normalização dos dados")
        elif len(concorrentes) == 0:
            print("   ⚠️ Nenhum concorrente no resultado")
        elif chart_path and Path(chart_path).exists():
            print("   ✅ Tudo OK: Relatório gerado com sucesso")
        else:
            print("   ⚠️ Relatório gerado mas arquivos não existem")
        
    except Exception as e:
        print(f"❌ Erro ao gerar relatório: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_report_generation()
