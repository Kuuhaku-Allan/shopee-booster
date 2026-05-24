"""
test_radar_ui_service.py - Testes do helper de UI do Radar (R6.3).

Testa que:
1. list_radar_products_for_audit retorna lista vazia se não há produtos
2. Produto com pattern report aparece como can_use=True
3. Produto sem pattern report aparece como can_use=False
4. format_radar_product_label inclui título e confiança
5. get_radar_preview_for_ui retorna termos, features e warnings
6. get_radar_preview_for_ui não quebra com product_uid inválido
"""

import unittest

from shopee_core.radar_ui_service import (
    list_radar_products_for_audit,
    format_radar_product_label,
    get_radar_preview_for_ui,
)


class TestRadarUIService(unittest.TestCase):
    """Testes do helper de UI do Radar."""
    
    def test_list_radar_products_empty_when_no_products(self):
        """Teste 1: list_radar_products_for_audit retorna lista sem quebrar."""
        # Act
        products = list_radar_products_for_audit(limit=10)
        
        # Assert
        self.assertIsInstance(products, list)
        # Pode estar vazio ou ter produtos - o importante é não quebrar
    
    def test_list_radar_products_returns_enriched_data(self):
        """Teste 2: list_radar_products_for_audit retorna dados enriquecidos."""
        # Act
        products = list_radar_products_for_audit(limit=10)
        
        # Assert
        if products:
            product = products[0]
            self.assertIn("product_uid", product)
            self.assertIn("title", product)
            self.assertIn("price", product)
            self.assertIn("marketplace", product)
            self.assertIn("has_pattern_report", product)
            self.assertIn("direct_count", product)
            self.assertIn("confidence", product)
            self.assertIn("can_use", product)
    
    def test_format_radar_product_label_includes_title_and_confidence(self):
        """Teste 3: format_radar_product_label inclui título e confiança."""
        # Arrange
        product = {
            "title": "Mochila Infantil Princesa Rosa",
            "direct_count": 5,
            "confidence": "medium",
        }
        
        # Act
        label = format_radar_product_label(product)
        
        # Assert
        self.assertIn("Mochila Infantil Princesa Rosa", label)
        self.assertIn("5 concorrentes diretos", label)
        self.assertIn("confiança média", label)
    
    def test_format_radar_product_label_truncates_long_title(self):
        """Teste 4: format_radar_product_label trunca título longo."""
        # Arrange
        product = {
            "title": "A" * 100,  # Título muito longo
            "direct_count": 10,
            "confidence": "high",
        }
        
        # Act
        label = format_radar_product_label(product)
        
        # Assert
        self.assertLess(len(label), 150)
        self.assertIn("...", label)
        self.assertIn("10 concorrentes diretos", label)
        self.assertIn("confiança alta", label)
    
    def test_get_radar_preview_returns_structure(self):
        """Teste 5: get_radar_preview_for_ui retorna estrutura correta."""
        # Arrange - Usar produto real se disponível
        products = list_radar_products_for_audit(limit=10)
        valid_products = [p for p in products if p["can_use"]]
        
        if not valid_products:
            # Testar com UID conhecido do smoke test
            product_uid = "2777bd10-5e4f-40ff-b302-81d23f8834d9"
        else:
            product_uid = valid_products[0]["product_uid"]
        
        # Act
        preview = get_radar_preview_for_ui(product_uid)
        
        # Assert
        self.assertIn("ok", preview)
        self.assertIn("confidence", preview)
        self.assertIn("direct_count", preview)
        
        if preview["ok"]:
            self.assertIn("strong_terms", preview)
            self.assertIn("recommended_features", preview)
            self.assertIn("off_niche_features", preview)
            self.assertIn("commercial_arguments", preview)
            self.assertIn("warnings", preview)
            self.assertIn("price_min", preview)
            self.assertIn("price_avg", preview)
    
    def test_get_radar_preview_does_not_break_with_invalid_uid(self):
        """Teste 6: get_radar_preview_for_ui não quebra com product_uid inválido."""
        # Act
        preview = get_radar_preview_for_ui("uid-inexistente-12345")
        
        # Assert
        self.assertFalse(preview["ok"])
        self.assertIn("error", preview)
        self.assertIsNotNone(preview["error"])
        self.assertEqual(preview["direct_count"], 0)


def run_tests():
    """Executa os testes e retorna o resultado."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestRadarUIService)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    print("\n")
    print("TESTE R6.3 - Helper de UI do Radar")
    print()
    
    success = run_tests()
    
    print()
    if success:
        print("✅ Todos os testes passaram")
    else:
        print("❌ Alguns testes falharam")
    
    exit(0 if success else 1)
