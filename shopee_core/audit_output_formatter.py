"""
shopee_core/audit_output_formatter.py — Normalizador de saída da Auditoria com Radar.

R6.3D: Corrige problemas de formatação e apresentação no output final gerado pela IA.

Funções exportadas:
    format_brl(value) -> str
        Formata um float como moeda brasileira: R$ 159,90

    normalize_brl_in_text(text) -> str
        Corrige padrões de moeda inválidos no texto (R 159,90 → R$ 159,90, etc.)

    remove_internal_compliance_notes(text) -> str
        Remove linhas/parágrafos que são notas internas geradas pela IA
        (Nota de conformidade:, Conforme as diretrizes, etc.)

    clean_audit_output(text) -> str
        Aplica normalize_brl_in_text + remove_internal_compliance_notes
        em sequência — usar esta para limpar o output final.
"""

from __future__ import annotations

import re


# ── Formatação de Moeda ────────────────────────────────────────────────────────

def format_brl(value: float | int | None) -> str:
    """
    Formata um número como moeda brasileira no padrão R$ XX,XX.

    Args:
        value: Valor numérico (float, int ou None)

    Returns:
        String formatada, ex: "R$ 159,90"
        Retorna "N/A" se value for None.

    Exemplos:
        >>> format_brl(159.9)
        'R$ 159,90'
        >>> format_brl(1234.5)
        'R$ 1.234,50'
        >>> format_brl(None)
        'N/A'
    """
    if value is None:
        return "N/A"
    try:
        # Formata com ponto de milhar e dois decimais
        # Troca separadores: . (milhar) e , (decimal) conforme pt-BR
        formatted = f"{float(value):,.2f}"
        # formatted agora está como "1,234.50" (padrão americano)
        # Converter para pt-BR: trocar , por X, . por ,, X por .
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatted}"
    except (ValueError, TypeError):
        return "N/A"


# ── Padrões de moeda a corrigir ────────────────────────────────────────────────

# Regex que captura faixas de preço: "R 59.00 - R 302.53" ou "R$ 59.00 - R$ 302.53"
_RANGE_PATTERN = re.compile(
    r"R\$?\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?)"  # preço inicial
    r"\s*[-–—]\s*"                                        # separador
    r"R\$?\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?)",  # preço final
    re.IGNORECASE,
)

# Regex que captura um único preço: "R 159,90" ou "R$ 159.90"
_SINGLE_PRICE_PATTERN = re.compile(
    r"R\$?\s+(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?)",
    re.IGNORECASE,
)


def _normalize_price_string(price_str: str) -> str:
    """
    Normaliza uma string de preço para formato pt-BR com ponto de milhar e vírgula decimal.

    Entrada:  "159.90"  →  Saída: "159,90"
    Entrada:  "1,234.50" → Saída: "1.234,50"
    Entrada:  "1.234,50" → Saída: "1.234,50"  (já correto)
    Entrada:  "159,90"  →  Saída: "159,90"   (já correto)
    """
    s = price_str.strip()

    # Detecta se usa ponto como decimal (padrão americano ou misto)
    # Heurística: se tem ponto após vírgula ou ponto no final com 2 dígitos
    dot_pos = s.rfind(".")
    comma_pos = s.rfind(",")

    if dot_pos > comma_pos:
        # Ponto é o separador decimal (formato americano: 1,234.50 ou 159.90)
        # Remove pontos de milhar e troca ponto decimal por vírgula
        integer_part, _, decimal_part = s.rpartition(".")
        integer_part = integer_part.replace(",", "").replace(".", "")
        # Reagrupa com ponto de milhar pt-BR
        int_val = int(integer_part) if integer_part else 0
        dec_val = decimal_part.ljust(2, "0")[:2]
        if int_val >= 1000:
            formatted_int = f"{int_val:,}".replace(",", ".")
        else:
            formatted_int = str(int_val)
        return f"{formatted_int},{dec_val}"
    elif comma_pos > dot_pos:
        # Vírgula é o separador decimal (formato pt-BR: 1.234,50 ou 159,90)
        # Apenas garante que está consistente
        integer_part, _, decimal_part = s.rpartition(",")
        integer_part = integer_part.replace(".", "")
        int_val = int(integer_part) if integer_part else 0
        dec_val = decimal_part.ljust(2, "0")[:2]
        if int_val >= 1000:
            formatted_int = f"{int_val:,}".replace(",", ".")
        else:
            formatted_int = str(int_val)
        return f"{formatted_int},{dec_val}"
    else:
        # Sem separador decimal — adiciona ,00
        integer_part = s.replace(".", "").replace(",", "")
        int_val = int(integer_part) if integer_part else 0
        if int_val >= 1000:
            formatted_int = f"{int_val:,}".replace(",", ".")
        else:
            formatted_int = str(int_val)
        return f"{formatted_int},00"


def normalize_brl_in_text(text: str) -> str:
    """
    Corrige todos os padrões de moeda inválidos em um texto.

    Padrões corrigidos:
        "R 159,90"        → "R$ 159,90"
        "R$ 159.90"       → "R$ 159,90"
        "R 59.00"         → "R$ 59,00"
        "R 59.00 - R 302.53"  → "R$ 59,00 - R$ 302,53"
        "R$ 59.00 - R$ 302.53" → "R$ 59,00 - R$ 302,53"

    Preserva:
        "R$ 159,90"       (formato correto, sem alteração)

    Args:
        text: Texto bruto com possíveis erros de formatação de moeda

    Returns:
        Texto com moeda corrigida para R$ XX,XX
    """
    if not text:
        return text

    def replace_range(match: re.Match) -> str:
        p1 = _normalize_price_string(match.group(1))
        p2 = _normalize_price_string(match.group(2))
        return f"R$ {p1} - R$ {p2}"

    def replace_single(match: re.Match) -> str:
        p = _normalize_price_string(match.group(1))
        return f"R$ {p}"

    # 1. Corrige faixas primeiro (ex: "R 59.00 - R 302.53")
    result = _RANGE_PATTERN.sub(replace_range, text)

    # 2. Corrige preços individuais restantes
    result = _SINGLE_PRICE_PATTERN.sub(replace_single, result)

    return result


# ── Remoção de Notas Internas ──────────────────────────────────────────────────

# Prefixos que indicam notas internas da IA que não devem aparecer para o usuário
_INTERNAL_NOTE_PREFIXES = (
    "nota de conformidade",
    "conforme as diretrizes",
    "validação interna",
    "observação interna",
    "nota interna",
    "compliance note",
    "aviso de conformidade",
    "observação de conformidade",
)


def remove_internal_compliance_notes(text: str) -> str:
    """
    Remove linhas e parágrafos que começam com prefixos de notas internas da IA.

    Prefixos removidos (case-insensitive):
        - "Nota de conformidade:"
        - "Conforme as diretrizes"
        - "Validação interna:"
        - "Observação interna:"
        - "Nota interna:"

    Estratégia:
        - Remove linhas individuais que começam com esses prefixos
        - Remove também parágrafo completo se a linha for início de parágrafo

    Args:
        text: Texto bruto da IA

    Returns:
        Texto sem notas internas
    """
    if not text:
        return text

    lines = text.splitlines()
    cleaned_lines = []
    skip_blank_after = False

    for line in lines:
        stripped = line.strip().lower()

        # Verifica se a linha começa com um dos prefixos internos
        is_internal = any(stripped.startswith(prefix) for prefix in _INTERNAL_NOTE_PREFIXES)

        if is_internal:
            skip_blank_after = True
            continue  # Pula a linha

        # Se a linha anterior era nota interna, pula a próxima linha em branco também
        if skip_blank_after and stripped == "":
            skip_blank_after = False
            continue

        skip_blank_after = False
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


# ── Limpeza Completa ───────────────────────────────────────────────────────────

def clean_audit_output(text: str) -> str:
    """
    Aplica todas as limpezas de output em sequência:
        1. normalize_brl_in_text   — corrige formatação de moeda
        2. remove_internal_compliance_notes — remove notas internas da IA

    Use esta função como ponto de entrada único para limpar o output final da IA
    antes de exibir para o usuário.

    Não afeta:
        - O bloco de debug (context bruto do Radar)
        - Logs internos do app

    Args:
        text: Texto bruto retornado pela IA

    Returns:
        Texto limpo e formatado para exibição ao usuário
    """
    if not text:
        return text

    result = normalize_brl_in_text(text)
    result = remove_internal_compliance_notes(result)
    return result
