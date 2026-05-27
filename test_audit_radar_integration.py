"""
test_audit_radar_integration.py - Testes de integração Auditoria + Radar (R6.2).

Testa que:
1. Auditoria sem radar_own_product_uid mantém comportamento antigo
2. radar_own_product_uid inexistente não quebra
3. status can_use=False não quebra
4. status can_use=True chama build_radar_prompt_block
5. generate_full_optimization recebe radar_context_block
6. prompt final inclui "CONTEXTO DO RADAR"
7. prompt final inclui "notebook" como off-niche/evitar
8. sem radar_context_block, prompt não muda
"""

import unittest
from unittest.mock import patch, MagicMock
import pandas as pd

from shopee_core.audit_service import generate_product_optimization
from backend_core import generate_full_optimization


class TestAuditRadarIntegration(unittest.TestCase):
    """Testes de integração entre Auditoria e Radar."""
    
    def setUp(self):
        """Setup comum para todos os testes."""
        self.product = {
            "name": "Mochila Escolar Infantil",
            "price": 89.90,
            "itemid": "123456",
            "shopid": "789",
        }
        self.segmento = "Mochilas Escolares"
    
    @patch("shopee_core.competitor_service.search_competitors_safe")
    @patch("backend_core.fetch_reviews_intercept")
    @patch("backend_core.generate_full_optimization")
    @patch("shopee_core.audit_market_source_service.get_radar_market_status_for_audit")
    @patch("shopee_core.audit_market_source_service.choose_audit_market_source")
    def test_audit_without_radar_maintains_old_behavior(
        self,
        mock_choose,
        mock_radar_status,
        mock_generate_full,
        mock_reviews,
        mock_competitors,
    ):
        """Teste 1: Auditoria sem radar_own_product_uid mantém comportamento antigo."""
        # Arrange
        mock_competitors.return_value = []
        mock_reviews.return_value = ([], [])
        mock_generate_full.return_value = "Otimização gerada"
        mock_radar_status.return_value = {"has_radar": False, "confidence_level": "insufficient", "warnings": []}
        mock_choose.return_value = {
            "source": "none",
            "reason": "Sem base de mercado.",
            "radar_used": False,
            "scraping_used": False,
            "warnings": [],
        }
        
        # Act
        result = generate_product_optimization(
            product=self.product,
            segmento=self.segmento,
            api_key="fake_key",
            # radar_own_product_uid NÃO fornecido
        )
        
        # Assert
        self.assertTrue(result.get("ok"))
        self.assertEqual(result["data"]["optimization"], "Otimização gerada")
        self.assertFalse(result["data"]["radar_used"])
        self.assertEqual(result["data"]["market_source"], "none")
        mock_choose.assert_called_once()
        
        # Verifica que generate_full_optimization foi chamado sem radar_context_block
        mock_generate_full.assert_called_once()
        call_kwargs = mock_generate_full.call_args[1]
        self.assertIsNone(call_kwargs.get("radar_context_block"))

    @patch("shopee_core.competitor_service.search_competitors_safe")
    @patch("backend_core.fetch_reviews_intercept")
    @patch("backend_core.generate_full_optimization")
    @patch("shopee_core.audit_market_source_service.get_radar_market_status_for_audit")
    @patch("shopee_core.audit_market_source_service.choose_audit_market_source")
    def test_generate_product_optimization_calls_auto_source_selector(
        self,
        mock_choose,
        mock_radar_status,
        mock_generate_full,
        mock_reviews,
        mock_competitors,
    ):
        """R7.5A: generate_product_optimization chama choose_audit_market_source."""
        mock_competitors.return_value = []
        mock_reviews.return_value = ([], [])
        mock_generate_full.return_value = "Otimização gerada"
        mock_radar_status.return_value = {"has_radar": False, "confidence_level": "insufficient", "warnings": []}
        mock_choose.return_value = {
            "source": "none",
            "reason": "Sem base de mercado.",
            "radar_used": False,
            "scraping_used": False,
            "warnings": [],
        }

        result = generate_product_optimization(
            product=self.product,
            segmento=self.segmento,
            api_key="fake_key",
        )

        self.assertTrue(result.get("ok"))
        mock_choose.assert_called_once()
        self.assertIn("market_source", result["data"])
        self.assertEqual(result["data"]["market_source"], "none")

    @patch("shopee_core.competitor_service.search_competitors_safe")
    @patch("backend_core.fetch_reviews_intercept")
    @patch("backend_core.generate_full_optimization")
    @patch("shopee_core.audit_market_source_service.get_radar_market_status_for_audit")
    @patch("shopee_core.audit_market_source_service.choose_audit_market_source")
    @patch("shopee_core.radar_audit_context_service.build_radar_audit_context")
    @patch("shopee_core.radar_audit_context_service.build_radar_prompt_block")
    def test_auto_radar_source_passes_context_to_generate_full(
        self,
        mock_build_prompt,
        mock_build_context,
        mock_choose,
        mock_radar_status,
        mock_generate_full,
        mock_reviews,
        mock_competitors,
    ):
        """R7.5A: quando Radar é escolhido, contexto entra no prompt."""
        mock_competitors.return_value = []
        mock_reviews.return_value = ([], [])
        mock_generate_full.return_value = "Otimização gerada"
        mock_radar_status.return_value = {
            "has_radar": True,
            "product_uid": "uid-auto",
            "radar_product_uid": "uid-auto",
            "confidence_level": "high",
            "is_fresh": True,
            "effective_competitor_count": 9,
            "warnings": [],
        }
        mock_choose.return_value = {
            "source": "radar",
            "reason": "Scraping indisponível. Usei Radar.",
            "radar_used": True,
            "scraping_used": False,
            "radar_product_uid": "uid-auto",
            "radar_confidence": "high",
            "radar_report_uid": "report-auto",
            "warnings": [],
        }
        mock_build_context.return_value = {"ok": True, "market_summary": {"competitor_count": 9}}
        mock_build_prompt.return_value = "=== CONTEXTO DO RADAR ===\nDados do Radar"

        result = generate_product_optimization(
            product=self.product,
            segmento=self.segmento,
            api_key="fake_key",
        )

        self.assertTrue(result.get("ok"))
        self.assertTrue(result["data"]["radar_used"])
        self.assertEqual(result["data"]["market_source"], "radar")
        self.assertEqual(result["data"]["market_source_reason"], "Scraping indisponível. Usei Radar.")
        call_kwargs = mock_generate_full.call_args[1]
        self.assertIn("CONTEXTO DO RADAR", call_kwargs.get("radar_context_block"))
    
    @patch("shopee_core.competitor_service.search_competitors_safe")
    @patch("backend_core.fetch_reviews_intercept")
    @patch("backend_core.generate_full_optimization")
    @patch("shopee_core.radar_audit_context_service.get_radar_audit_context_status")
    def test_nonexistent_radar_uid_does_not_break(
        self,
        mock_status,
        mock_generate_full,
        mock_reviews,
        mock_competitors,
    ):
        """Teste 2: radar_own_product_uid inexistente não quebra."""
        # Arrange
        mock_competitors.return_value = []
        mock_reviews.return_value = ([], [])
        mock_generate_full.return_value = "Otimização gerada"
        mock_status.return_value = {
            "can_use": False,
            "reason": "Produto próprio não encontrado",
            "confidence": None,
        }
        
        # Act
        result = generate_product_optimization(
            product=self.product,
            segmento=self.segmento,
            api_key="fake_key",
            radar_own_product_uid="uid-inexistente",
        )
        
        # Assert
        self.assertTrue(result.get("ok"))
        self.assertFalse(result["data"]["radar_used"])
        self.assertIsNotNone(result["data"]["radar_status"])
        self.assertFalse(result["data"]["radar_status"]["can_use"])
    
    @patch("shopee_core.competitor_service.search_competitors_safe")
    @patch("backend_core.fetch_reviews_intercept")
    @patch("backend_core.generate_full_optimization")
    @patch("shopee_core.radar_audit_context_service.get_radar_audit_context_status")
    def test_status_can_use_false_does_not_break(
        self,
        mock_status,
        mock_generate_full,
        mock_reviews,
        mock_competitors,
    ):
        """Teste 3: status can_use=False não quebra."""
        # Arrange
        mock_competitors.return_value = []
        mock_reviews.return_value = ([], [])
        mock_generate_full.return_value = "Otimização gerada"
        mock_status.return_value = {
            "can_use": False,
            "reason": "Base insuficiente: apenas 2 concorrentes diretos. Mínimo: 3.",
            "confidence": "insufficient",
            "direct_count": 2,
        }
        
        # Act
        result = generate_product_optimization(
            product=self.product,
            segmento=self.segmento,
            api_key="fake_key",
            radar_own_product_uid="uid-valido-mas-insuficiente",
        )
        
        # Assert
        self.assertTrue(result.get("ok"))
        self.assertFalse(result["data"]["radar_used"])
        self.assertEqual(result["data"]["radar_status"]["direct_count"], 2)
    
    @patch("shopee_core.competitor_service.search_competitors_safe")
    @patch("backend_core.fetch_reviews_intercept")
    @patch("backend_core.generate_full_optimization")
    @patch("shopee_core.radar_audit_context_service.get_radar_audit_context_status")
    @patch("shopee_core.radar_audit_context_service.build_radar_audit_context")
    @patch("shopee_core.radar_audit_context_service.build_radar_prompt_block")
    def test_status_can_use_true_calls_build_radar_prompt_block(
        self,
        mock_build_prompt,
        mock_build_context,
        mock_status,
        mock_generate_full,
        mock_reviews,
        mock_competitors,
    ):
        """Teste 4: status can_use=True chama build_radar_prompt_block."""
        # Arrange
        mock_competitors.return_value = []
        mock_reviews.return_value = ([], [])
        mock_generate_full.return_value = "Otimização gerada"
        mock_status.return_value = {
            "can_use": True,
            "reason": "Radar disponível com 10 concorrentes diretos.",
            "confidence": "high",
            "direct_count": 10,
        }
        mock_build_context.return_value = {
            "ok": True,
            "market_summary": {"competitor_count": 10},
        }
        mock_build_prompt.return_value = "=== CONTEXTO DO RADAR ===\nDados do Radar..."
        
        # Act
        result = generate_product_optimization(
            product=self.product,
            segmento=self.segmento,
            api_key="fake_key",
            radar_own_product_uid="uid-valido",
        )
        
        # Assert
        self.assertTrue(result.get("ok"))
        self.assertTrue(result["data"]["radar_used"])
        mock_build_prompt.assert_called_once()
        
        # Verifica que generate_full_optimization foi chamado COM radar_context_block
        mock_generate_full.assert_called_once()
        call_kwargs = mock_generate_full.call_args[1]
        self.assertIsNotNone(call_kwargs.get("radar_context_block"))
        self.assertIn("CONTEXTO DO RADAR", call_kwargs["radar_context_block"])
    
    def test_prompt_includes_radar_context_when_provided(self):
        """Teste 5: prompt inclui contexto do Radar quando fornecido."""
        # Arrange
        product = {"name": "Mochila Escolar", "price": 89.90}
        competitors_df = pd.DataFrame([
            {"nome": "Mochila A", "preco": 79.90, "avaliações": 100, "estrelas": 4.5}
        ])
        reviews = ["Ótima qualidade"]
        radar_context = "=== CONTEXTO DO RADAR ===\nTermos fortes: mochila, escolar"
        
        # Act - Captura o prompt via mock
        with patch("backend_core.generate_text_with_model_fallback") as mock_fallback:
            mock_fallback.return_value = "Otimização"
            
            generate_full_optimization(
                product=product,
                competitors_df=competitors_df,
                reviews=reviews,
                segmento="Mochilas",
                api_key="fake_key",
                radar_context_block=radar_context,
            )
            
            # Assert
            mock_fallback.assert_called_once()
            call_kwargs = mock_fallback.call_args[1]
            prompt = call_kwargs["prompt"]
            
            self.assertIn("CONTEXTO DO RADAR", prompt)
            self.assertIn("Termos fortes: mochila, escolar", prompt)
            self.assertIn("IMPORTANTE: Use o contexto do Radar", prompt)
            self.assertIn("Não recomende features marcadas como off-niche", prompt)
    
    def test_prompt_includes_notebook_as_off_niche(self):
        """Teste 6: prompt inclui 'notebook' como off-niche/evitar."""
        # Arrange
        product = {"name": "Mochila Escolar", "price": 89.90}
        competitors_df = pd.DataFrame([])
        reviews = []
        radar_context = """=== CONTEXTO DO RADAR ===
Features fora de nicho / evitar:
- notebook, caderno, estojo
"""
        
        # Act
        with patch("backend_core.generate_text_with_model_fallback") as mock_fallback:
            mock_fallback.return_value = "Otimização"
            
            generate_full_optimization(
                product=product,
                competitors_df=competitors_df,
                reviews=reviews,
                segmento="Mochilas",
                api_key="fake_key",
                radar_context_block=radar_context,
            )
            
            # Assert
            call_kwargs = mock_fallback.call_args[1]
            prompt = call_kwargs["prompt"]
            
            self.assertIn("notebook", prompt.lower())
            self.assertIn("evitar", prompt.lower())
    
    def test_prompt_without_radar_context_unchanged(self):
        """Teste 7: sem radar_context_block, prompt não muda."""
        # Arrange
        product = {"name": "Mochila Escolar", "price": 89.90}
        competitors_df = pd.DataFrame([])
        reviews = []
        
        # Act
        with patch("backend_core.generate_text_with_model_fallback") as mock_fallback:
            mock_fallback.return_value = "Otimização"
            
            generate_full_optimization(
                product=product,
                competitors_df=competitors_df,
                reviews=reviews,
                segmento="Mochilas",
                api_key="fake_key",
                radar_context_block=None,  # SEM Radar
            )
            
            # Assert
            call_kwargs = mock_fallback.call_args[1]
            prompt = call_kwargs["prompt"]
            
            self.assertNotIn("CONTEXTO DO RADAR", prompt)
            self.assertNotIn("IMPORTANTE: Use o contexto do Radar", prompt)
    
    def test_generate_full_optimization_accepts_radar_context_block(self):
        """Teste 8: generate_full_optimization aceita radar_context_block."""
        # Arrange
        product = {"name": "Mochila", "price": 89.90}
        competitors_df = pd.DataFrame([])
        reviews = []
        radar_context = "=== CONTEXTO DO RADAR ==="
        
        # Act & Assert - Não deve lançar exceção
        with patch("backend_core.generate_text_with_model_fallback") as mock_fallback:
            mock_fallback.return_value = "Otimização"
            
            result = generate_full_optimization(
                product=product,
                competitors_df=competitors_df,
                reviews=reviews,
                segmento="Mochilas",
                api_key="fake_key",
                radar_context_block=radar_context,
            )
            
            self.assertEqual(result, "Otimização")


def run_tests():
    """Executa os testes e retorna o resultado."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestAuditRadarIntegration)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
