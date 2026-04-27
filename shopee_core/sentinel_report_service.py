"""
shopee_core/sentinel_report_service.py — Geração de Relatórios do Sentinela
============================================================================
Gera gráficos, tabelas e resumos estruturados para o Sentinela.

Funcionalidades:
  - Resumo textual estruturado
  - DataFrame de concorrentes
  - Gráfico de preços (PNG)
  - Tabela de concorrentes (CSV)
  - Tabela de concorrentes (PNG - opcional)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Backend sem GUI
import matplotlib.pyplot as plt

log = logging.getLogger("sentinel_report")

# Diretório para salvar relatórios
REPORTS_DIR = Path("data/reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def build_sentinel_summary(resultado: dict) -> str:
    """
    Constrói resumo textual do resultado do Sentinela.
    
    Args:
        resultado: Dados estruturados do Sentinela
    
    Returns:
        Resumo em texto simples
    """
    loja = resultado.get("loja", "N/A")
    keyword = resultado.get("keyword", "N/A")
    total = resultado.get("total_analisado", 0)
    novos = len(resultado.get("novos_concorrentes", []))
    preco_medio = resultado.get("preco_medio", 0)
    menor_preco = resultado.get("menor_preco", 0)
    maior_preco = resultado.get("maior_preco", 0)
    
    summary = (
        f"🛡️ Sentinela - Relatório\n"
        f"{'=' * 40}\n\n"
        f"Loja: {loja}\n"
        f"Keyword: {keyword}\n"
        f"Concorrentes analisados: {total}\n"
        f"Novos concorrentes: {novos}\n\n"
        f"Preços:\n"
        f"  Médio: R$ {preco_medio:.2f}\n"
        f"  Mínimo: R$ {menor_preco:.2f}\n"
        f"  Máximo: R$ {maior_preco:.2f}\n"
    )
    
    return summary


def build_competitor_dataframe(resultado: dict) -> pd.DataFrame:
    """
    Constrói DataFrame com dados dos concorrentes.
    
    Args:
        resultado: Dados estruturados do Sentinela
    
    Returns:
        DataFrame com colunas: titulo, preco, loja, ranking, is_new
    """
    concorrentes = resultado.get("concorrentes", [])
    
    log.info(f"[REPORT] build_competitor_dataframe: recebeu {len(concorrentes)} concorrentes")
    
    if not concorrentes:
        log.warning("[REPORT] Nenhum concorrente para gerar DataFrame")
        return pd.DataFrame()
    
    # Log do primeiro concorrente para debug (U7.8)
    if concorrentes:
        log.info(f"[REPORT] Primeiro concorrente: {concorrentes[0]}")
    
    # Normaliza dados
    data = []
    for c in concorrentes:
        data.append({
            "Ranking": c.get("ranking", 0),
            "Título": c.get("titulo", "")[:50],  # Trunca para caber na tabela
            "Preço": c.get("preco", 0),
            "Loja": c.get("loja", "")[:30],
            "Novo": "✓" if c.get("is_new", False) else "",
        })
    
    df = pd.DataFrame(data)
    
    # Ordena por ranking
    if not df.empty:
        df = df.sort_values("Ranking")
    
    log.info(f"[REPORT] DataFrame criado: {len(df)} linhas")
    return df


def generate_price_chart(df: pd.DataFrame, output_path: str, keyword: str = "") -> str:
    """
    Gera gráfico de preços dos concorrentes.
    
    Args:
        df: DataFrame com dados dos concorrentes
        output_path: Caminho para salvar o gráfico PNG
        keyword: Keyword monitorada (para título)
    
    Returns:
        Caminho do arquivo gerado
    """
    if df.empty:
        log.warning("[REPORT] DataFrame vazio, não é possível gerar gráfico")
        return ""
    
    try:
        # Configura figura
        plt.figure(figsize=(12, 6))
        plt.style.use('seaborn-v0_8-darkgrid')
        
        # Dados
        rankings = df["Ranking"].values
        precos = df["Preço"].values
        is_new = df["Novo"].values == "✓"
        
        # Plota preços
        plt.plot(rankings, precos, marker='o', linewidth=2, markersize=8, 
                color='#2E86AB', label='Concorrentes')
        
        # Destaca novos concorrentes
        if any(is_new):
            new_rankings = rankings[is_new]
            new_precos = precos[is_new]
            plt.scatter(new_rankings, new_precos, color='#E63946', s=200, 
                       marker='*', label='Novos', zorder=5)
        
        # Linha de preço médio
        preco_medio = precos.mean()
        plt.axhline(y=preco_medio, color='#06A77D', linestyle='--', 
                   linewidth=2, label=f'Média: R$ {preco_medio:.2f}')
        
        # Formatação
        plt.xlabel('Ranking', fontsize=12, fontweight='bold')
        plt.ylabel('Preço (R$)', fontsize=12, fontweight='bold')
        plt.title(f'Análise de Preços - {keyword}' if keyword else 'Análise de Preços',
                 fontsize=14, fontweight='bold', pad=20)
        plt.legend(loc='best', fontsize=10)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        # Salva
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        log.info(f"[REPORT] Gráfico salvo: {output_path}")
        return output_path
        
    except Exception as e:
        log.error(f"[REPORT] Erro ao gerar gráfico: {e}")
        plt.close()
        return ""


def generate_competitor_table_csv(df: pd.DataFrame, output_path: str) -> str:
    """
    Gera tabela CSV com dados dos concorrentes.
    
    Args:
        df: DataFrame com dados dos concorrentes
        output_path: Caminho para salvar o CSV
    
    Returns:
        Caminho do arquivo gerado
    """
    if df.empty:
        log.warning("[REPORT] DataFrame vazio, não é possível gerar CSV")
        return ""
    
    try:
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        log.info(f"[REPORT] CSV salvo: {output_path}")
        return output_path
        
    except Exception as e:
        log.error(f"[REPORT] Erro ao gerar CSV: {e}")
        return ""


def generate_competitor_table_png(df: pd.DataFrame, output_path: str) -> str:
    """
    Gera imagem PNG da tabela de concorrentes com formatação profissional.
    
    Args:
        df: DataFrame com dados dos concorrentes
        output_path: Caminho para salvar o PNG
    
    Returns:
        Caminho do arquivo gerado
    """
    if df.empty:
        log.warning("[REPORT] DataFrame vazio, não é possível gerar PNG da tabela")
        return ""
    
    try:
        import textwrap
        
        # Limita a top 15 para legibilidade (U7.9)
        df_display = df.head(15).copy()
        
        # Renomeia colunas para ficarem mais curtas (U7.9)
        df_display = df_display.rename(columns={
            "Ranking": "Rank",
            "Título": "Produto",
            "Preço": "Preço",
            "Loja": "Loja",
            "Novo": "Novo"
        })
        
        # Formata preços (U7.9)
        df_display["Preço"] = df_display["Preço"].apply(lambda x: f"R$ {x:.2f}")
        
        # Quebra de linha em títulos longos (U7.9)
        df_display["Produto"] = df_display["Produto"].apply(
            lambda x: "\n".join(textwrap.wrap(str(x), width=28))
        )
        
        # Quebra de linha em lojas longas (U7.9)
        df_display["Loja"] = df_display["Loja"].apply(
            lambda x: "\n".join(textwrap.wrap(str(x), width=18))
        )
        
        # Calcula altura da figura baseado no número de linhas (U7.9)
        nrows = len(df_display)
        fig_height = max(4, nrows * 0.65 + 1.6)
        
        # Configura figura com tamanho adequado (U7.9)
        fig, ax = plt.subplots(figsize=(14, fig_height))
        ax.axis("off")
        
        # Cria tabela com larguras otimizadas (U7.9)
        table = ax.table(
            cellText=df_display.values,
            colLabels=df_display.columns,
            cellLoc="left",
            colLoc="center",
            loc="center",
            bbox=[0, 0, 1, 1],
            colWidths=[0.08, 0.42, 0.14, 0.24, 0.12],  # Rank, Produto, Preço, Loja, Novo
        )
        
        # Configurações de fonte (U7.9)
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.6)  # Altura de linha aumentada
        
        # Estilo profissional com bordas visíveis (U7.9)
        for (row, col), cell in table.get_celld().items():
            # Bordas em todas as células
            cell.set_edgecolor("#B8B8B8")
            cell.set_linewidth(0.8)
            
            if row == 0:
                # Cabeçalho destacado
                cell.set_facecolor("#2E86AB")
                cell.set_text_props(weight="bold", color="white", ha="center", va="center")
                cell.set_linewidth(1.2)
                cell.set_edgecolor("#7A7A7A")
            else:
                # Zebra striping para melhor leitura
                cell.set_facecolor("#F7F7F7" if row % 2 == 0 else "white")
                
                # Destaca novos concorrentes com fundo verde-claro (U7.9)
                if col == 4 and df_display.iloc[row - 1]["Novo"] == "✓":
                    cell.set_facecolor("#D4EDDA")
                
                # Alinhamento por coluna (U7.9)
                if col in [0, 2, 4]:  # Rank, Preço, Novo
                    cell.set_text_props(ha="center", va="center")
                else:  # Produto, Loja
                    cell.set_text_props(ha="left", va="center")
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=180, bbox_inches="tight", pad_inches=0.15)
        plt.close()
        
        log.info(f"[REPORT] PNG da tabela salvo: {output_path}")
        return output_path
        
    except Exception as e:
        log.error(f"[REPORT] Erro ao gerar PNG da tabela: {e}", exc_info=True)
        plt.close()
        return ""


def generate_sentinel_report(
    resultado: dict,
    include_chart: bool = True,
    include_csv: bool = True,
    include_table_png: bool = False
) -> dict:
    """
    Gera relatório completo do Sentinela.
    
    Args:
        resultado: Dados estruturados do Sentinela
        include_chart: Gerar gráfico de preços
        include_csv: Gerar tabela CSV
        include_table_png: Gerar tabela como PNG
    
    Returns:
        Dict com caminhos dos arquivos gerados:
        {
            "summary": str,
            "chart_path": str,
            "csv_path": str,
            "table_png_path": str
        }
    """
    log.info("[REPORT] Gerando relatório do Sentinela")
    log.info(f"[REPORT] include_chart={include_chart}, include_csv={include_csv}, include_table_png={include_table_png}")
    
    # Timestamp para nomes de arquivo
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    keyword_safe = resultado.get("keyword", "sentinela").replace(" ", "_")[:20]
    
    # Resumo textual
    summary = build_sentinel_summary(resultado)
    
    # DataFrame
    log.info("[REPORT] Construindo DataFrame...")
    df = build_competitor_dataframe(resultado)
    log.info(f"[REPORT] DataFrame construído: empty={df.empty}, shape={df.shape if not df.empty else 'N/A'}")
    
    # Gera arquivos
    report = {
        "summary": summary,
        "chart_path": "",
        "csv_path": "",
        "table_png_path": "",
    }
    
    if not df.empty:
        log.info("[REPORT] DataFrame não está vazio, gerando arquivos...")
        
        # Gráfico
        if include_chart:
            chart_path = REPORTS_DIR / f"sentinela_{keyword_safe}_{timestamp}_chart.png"
            log.info(f"[REPORT] Gerando gráfico: {chart_path}")
            report["chart_path"] = generate_price_chart(
                df, 
                str(chart_path), 
                resultado.get("keyword", "")
            )
            log.info(f"[REPORT] Gráfico gerado: {report['chart_path']}")
        
        # CSV
        if include_csv:
            csv_path = REPORTS_DIR / f"sentinela_{keyword_safe}_{timestamp}_table.csv"
            log.info(f"[REPORT] Gerando CSV: {csv_path}")
            report["csv_path"] = generate_competitor_table_csv(df, str(csv_path))
            log.info(f"[REPORT] CSV gerado: {report['csv_path']}")
        
        # PNG da tabela (opcional)
        if include_table_png:
            table_png_path = REPORTS_DIR / f"sentinela_{keyword_safe}_{timestamp}_table.png"
            log.info(f"[REPORT] Gerando PNG da tabela: {table_png_path}")
            report["table_png_path"] = generate_competitor_table_png(df, str(table_png_path))
            log.info(f"[REPORT] PNG da tabela gerado: {report['table_png_path']}")
    else:
        log.warning("[REPORT] DataFrame está vazio, não será possível gerar arquivos")
    
    log.info(f"[REPORT] Relatório gerado: chart={bool(report['chart_path'])} csv={bool(report['csv_path'])} png={bool(report['table_png_path'])}")
    return report
