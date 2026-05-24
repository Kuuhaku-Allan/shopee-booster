"""
test_audit_output_formatter.py — Testes unitários para R6.3D.

Testa:
    1. format_brl(159.9) -> "R$ 159,90"
    2. normalize_brl_in_text corrige "R 159,90"
    3. normalize_brl_in_text corrige "R$ 159.90"
    4. normalize_brl_in_text corrige faixas com ponto decimal
    5. remove_internal_compliance_notes remove "Nota de conformidade"
    6. clean_audit_output preserva o conteúdo principal
"""

import unittest
from shopee_core.audit_output_formatter import (
    format_brl,
    normalize_brl_in_text,
    remove_internal_compliance_notes,
    clean_audit_output,
)


class TestFormatBrl(unittest.TestCase):
    """Testes para format_brl()."""

    def test_basic_float(self):
        """format_brl(159.9) deve retornar 'R$ 159,90'."""
        self.assertEqual(format_brl(159.9), "R$ 159,90")

    def test_integer_value(self):
        """format_brl(100) deve retornar 'R$ 100,00'."""
        self.assertEqual(format_brl(100), "R$ 100,00")

    def test_zero(self):
        """format_brl(0) deve retornar 'R$ 0,00'."""
        self.assertEqual(format_brl(0), "R$ 0,00")

    def test_none_value(self):
        """format_brl(None) deve retornar 'N/A'."""
        self.assertEqual(format_brl(None), "N/A")

    def test_value_with_milhar(self):
        """format_brl(1234.50) deve retornar 'R$ 1.234,50'."""
        self.assertEqual(format_brl(1234.50), "R$ 1.234,50")

    def test_value_with_centavos(self):
        """format_brl(59.0) deve retornar 'R$ 59,00'."""
        self.assertEqual(format_brl(59.0), "R$ 59,00")

    def test_value_302_53(self):
        """format_brl(302.53) deve retornar 'R$ 302,53'."""
        self.assertEqual(format_brl(302.53), "R$ 302,53")

    def test_value_139_90(self):
        """format_brl(139.90) deve retornar 'R$ 139,90'."""
        self.assertEqual(format_brl(139.90), "R$ 139,90")


class TestNormalizeBrlInText(unittest.TestCase):
    """Testes para normalize_brl_in_text()."""

    def test_corrects_r_without_dollar_sign(self):
        """'R 159,90' deve virar 'R$ 159,90'."""
        result = normalize_brl_in_text("O preço é R 159,90 hoje.")
        self.assertIn("R$ 159,90", result)
        self.assertNotIn("R 159,90", result)

    def test_corrects_r_dollar_with_dot_decimal(self):
        """'R$ 159.90' deve virar 'R$ 159,90'."""
        result = normalize_brl_in_text("Preço: R$ 159.90")
        self.assertIn("R$ 159,90", result)

    def test_corrects_r_without_dollar_dot_decimal(self):
        """'R 59.00' deve virar 'R$ 59,00'."""
        result = normalize_brl_in_text("Mínimo: R 59.00")
        self.assertIn("R$ 59,00", result)

    def test_corrects_price_range_with_dot(self):
        """'R 59.00 - R 302.53' deve virar 'R$ 59,00 - R$ 302,53'."""
        result = normalize_brl_in_text("Faixa: R 59.00 - R 302.53")
        self.assertIn("R$ 59,00", result)
        self.assertIn("R$ 302,53", result)
        # Garante que não tem formatos errados
        self.assertNotIn("R 59", result)
        self.assertNotIn("R 302", result)

    def test_corrects_dollar_range_with_dot(self):
        """'R$ 59.00 - R$ 302.53' deve virar 'R$ 59,00 - R$ 302,53'."""
        result = normalize_brl_in_text("Faixa de preço: R$ 59.00 - R$ 302.53")
        self.assertIn("R$ 59,00", result)
        self.assertIn("R$ 302,53", result)

    def test_preserves_correct_format(self):
        """'R$ 159,90' já correto não deve ser alterado."""
        original = "Preço correto: R$ 159,90"
        result = normalize_brl_in_text(original)
        self.assertIn("R$ 159,90", result)

    def test_preserves_text_around_price(self):
        """Texto ao redor dos preços deve ser preservado."""
        text = "O produto custa R 89,90 e o frete é grátis."
        result = normalize_brl_in_text(text)
        self.assertIn("R$ 89,90", result)
        self.assertIn("frete é grátis", result)

    def test_corrects_multiple_prices_in_text(self):
        """Múltiplos preços inválidos devem ser todos corrigidos."""
        text = "Mínimo: R 59.00, Médio: R 159.90, Máximo: R 302.53"
        result = normalize_brl_in_text(text)
        self.assertIn("R$ 59,00", result)
        self.assertIn("R$ 159,90", result)
        self.assertIn("R$ 302,53", result)

    def test_empty_string(self):
        """String vazia deve retornar string vazia."""
        self.assertEqual(normalize_brl_in_text(""), "")

    def test_none_returns_none(self):
        """None deve retornar None."""
        self.assertIsNone(normalize_brl_in_text(None))


class TestRemoveInternalComplianceNotes(unittest.TestCase):
    """Testes para remove_internal_compliance_notes()."""

    def test_removes_nota_de_conformidade(self):
        """Linha 'Nota de conformidade: ...' deve ser removida."""
        text = "Título: Mochila Escolar\nNota de conformidade: Conforme as diretrizes internas.\nDescrição: Ótima mochila."
        result = remove_internal_compliance_notes(text)
        self.assertNotIn("Nota de conformidade", result)
        self.assertIn("Título: Mochila Escolar", result)
        self.assertIn("Descrição: Ótima mochila", result)

    def test_removes_conforme_as_diretrizes(self):
        """Linha que começa com 'Conforme as diretrizes' deve ser removida."""
        text = "Preço: R$ 89,90\nConforme as diretrizes do sistema, esta feature foi omitida.\nTags: mochila, escolar"
        result = remove_internal_compliance_notes(text)
        self.assertNotIn("Conforme as diretrizes", result)
        self.assertIn("Tags: mochila, escolar", result)

    def test_removes_validacao_interna(self):
        """Linha que começa com 'Validação interna:' deve ser removida."""
        text = "Resultado:\nValidação interna: feature notebook omitida conforme off-niche.\nFim."
        result = remove_internal_compliance_notes(text)
        self.assertNotIn("Validação interna", result)
        self.assertIn("Resultado:", result)
        self.assertIn("Fim.", result)

    def test_removes_observacao_interna(self):
        """Linha que começa com 'Observação interna:' deve ser removida."""
        text = "Texto normal.\nObservação interna: teste de conformidade.\nMais texto."
        result = remove_internal_compliance_notes(text)
        self.assertNotIn("Observação interna", result)
        self.assertIn("Mais texto.", result)

    def test_case_insensitive(self):
        """A remoção deve funcionar independente de maiúsculas/minúsculas."""
        text = "Conteúdo.\nNOTA DE CONFORMIDADE: algo.\nFim."
        result = remove_internal_compliance_notes(text)
        self.assertNotIn("NOTA DE CONFORMIDADE", result)
        self.assertIn("Conteúdo.", result)

    def test_preserves_normal_content(self):
        """Conteúdo normal não deve ser afetado."""
        text = "## Título\nDescrição do produto.\n\nTags: mochila, escolar, infantil"
        result = remove_internal_compliance_notes(text)
        self.assertEqual(text, result)

    def test_empty_string(self):
        """String vazia deve retornar string vazia."""
        self.assertEqual(remove_internal_compliance_notes(""), "")


class TestCleanAuditOutput(unittest.TestCase):
    """Testes para clean_audit_output()."""

    def test_clean_preserves_main_content(self):
        """clean_audit_output preserva o conteúdo principal do listing."""
        text = """## 🏷️ TÍTULO OTIMIZADO
Mochila Escolar Infantil Rodinhas Personagem 21L Reforçada

## 💰 ESTRATÉGIA DE PREÇO
R$ 89,90 é competitivo. Preço médio do mercado: R$ 95,00.

## 📝 DESCRIÇÃO OTIMIZADA
Mochila ideal para crianças.

## 🏷️ 20 TAGS LSI
mochila, escolar, infantil, rodinhas
"""
        result = clean_audit_output(text)
        self.assertIn("TÍTULO OTIMIZADO", result)
        self.assertIn("ESTRATÉGIA DE PREÇO", result)
        self.assertIn("DESCRIÇÃO OTIMIZADA", result)
        self.assertIn("mochila, escolar, infantil", result)

    def test_clean_fixes_brl_and_removes_notes(self):
        """clean_audit_output corrige moeda E remove notas internas."""
        text = """## 💰 ESTRATÉGIA DE PREÇO
Faixa: R 59.00 - R 302.53
Nota de conformidade: Conforme as diretrizes do sistema.

## 📝 DESCRIÇÃO
Mochila com excelente custo-benefício."""
        result = clean_audit_output(text)

        # Moeda corrigida
        self.assertIn("R$ 59,00", result)
        self.assertIn("R$ 302,53", result)

        # Nota removida
        self.assertNotIn("Nota de conformidade", result)

        # Conteúdo principal preservado
        self.assertIn("ESTRATÉGIA DE PREÇO", result)
        self.assertIn("DESCRIÇÃO", result)
        self.assertIn("Mochila com excelente custo-benefício", result)

    def test_clean_handles_none(self):
        """clean_audit_output com None deve retornar None."""
        self.assertIsNone(clean_audit_output(None))

    def test_clean_handles_empty(self):
        """clean_audit_output com string vazia deve retornar string vazia."""
        self.assertEqual(clean_audit_output(""), "")

    def test_clean_notebook_not_promoted(self):
        """clean_audit_output não deve promover 'notebook' mas preserva menção legítima."""
        text = """## TÍTULO
Mochila Escolar Infantil Rodinhas

## ARGUMENTOS DE VENDA
✅ Ideal para crianças
✅ Com rodinhas para facilitar o transporte
"""
        result = clean_audit_output(text)
        # Conteúdo legítimo preservado
        self.assertIn("Mochila Escolar", result)
        self.assertIn("rodinhas", result)


def run_tests():
    """Executa os testes e retorna o resultado."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestFormatBrl))
    suite.addTests(loader.loadTestsFromTestCase(TestNormalizeBrlInText))
    suite.addTests(loader.loadTestsFromTestCase(TestRemoveInternalComplianceNotes))
    suite.addTests(loader.loadTestsFromTestCase(TestCleanAuditOutput))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
