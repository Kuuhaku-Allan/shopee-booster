"""
telegram_service.py — Serviço de Notificações do Telegram
==========================================================
Canal de alertas e relatórios do Sentinela.

Funcionalidades:
  - Envio de mensagens formatadas em HTML
  - Envio de fotos (gráficos)
  - Envio de documentos (tabelas CSV)
  - Relatórios completos do Sentinela

Não é um bot conversacional — apenas notificações.
"""

from __future__ import annotations

import html
import logging
import requests
from typing import Optional
from pathlib import Path

log = logging.getLogger("telegram_service")


class TelegramSentinela:
    """Cliente do Telegram Bot API para envio de alertas do Sentinela."""
    
    def __init__(self, token: str = None, chat_id: str = None):
        """
        Inicializa o cliente do Telegram.
        
        Args:
            token: Token do bot (obtido do BotFather)
            chat_id: ID do chat/canal de destino
        """
        from sentinela_db import obter_config
        
        self.token = token or obter_config("telegram_token")
        self.chat_id = chat_id or obter_config("telegram_chat_id")
        
        # URLs da API
        if self.token:
            self.base_url = f"https://api.telegram.org/bot{self.token}"
            self.send_message_url = f"{self.base_url}/sendMessage"
            self.send_photo_url = f"{self.base_url}/sendPhoto"
            self.send_document_url = f"{self.base_url}/sendDocument"
        else:
            self.base_url = None
            self.send_message_url = None
            self.send_photo_url = None
            self.send_document_url = None
        
        log.info(f"[TELEGRAM] Inicializado: token={'✓' if self.token else '✗'} chat_id={'✓' if self.chat_id else '✗'}")
    
    def _is_configured(self) -> bool:
        """Verifica se o Telegram está configurado."""
        return bool(self.token and self.chat_id and self.base_url)
    
    def testar_conexao(self) -> bool:
        """
        Testa a conexão enviando uma mensagem de teste.
        
        Returns:
            True se enviou com sucesso
        """
        return self.enviar_mensagem(
            "🚀 <b>Shopee Booster Online!</b>\n\n"
            "Sentinela ativada e pronta para monitoramento."
        )
    
    def enviar_mensagem(self, mensagem: str, disable_preview: bool = True) -> bool:
        """
        Envia mensagem de texto formatada em HTML.
        
        Args:
            mensagem: Texto da mensagem (suporta HTML)
            disable_preview: Desabilita preview de links
        
        Returns:
            True se enviou com sucesso
        """
        if not self._is_configured():
            log.warning("[TELEGRAM] Não configurado. Mensagem não enviada.")
            return False
        
        payload = {
            "chat_id": self.chat_id,
            "text": mensagem,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_preview,
        }
        
        try:
            log.info(f"[TELEGRAM] Enviando mensagem: {len(mensagem)} chars")
            response = requests.post(self.send_message_url, json=payload, timeout=15)
            
            if response.status_code == 200:
                log.info("[TELEGRAM] Mensagem enviada com sucesso")
                return True
            else:
                log.error(f"[TELEGRAM] Erro HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            log.error(f"[TELEGRAM] Exceção ao enviar mensagem: {e}")
            return False
    
    def enviar_foto(self, image_path: str, caption: str = "") -> bool:
        """
        Envia foto (gráfico) para o Telegram.
        
        Args:
            image_path: Caminho do arquivo de imagem
            caption: Legenda da foto (suporta HTML)
        
        Returns:
            True se enviou com sucesso
        """
        if not self._is_configured():
            log.warning("[TELEGRAM] Não configurado. Foto não enviada.")
            return False
        
        if not Path(image_path).exists():
            log.error(f"[TELEGRAM] Arquivo não encontrado: {image_path}")
            return False
        
        try:
            log.info(f"[TELEGRAM] Enviando foto: {image_path}")
            
            with open(image_path, "rb") as photo_file:
                files = {"photo": photo_file}
                data = {
                    "chat_id": self.chat_id,
                    "caption": caption,
                    "parse_mode": "HTML",
                }
                
                response = requests.post(
                    self.send_photo_url,
                    data=data,
                    files=files,
                    timeout=30
                )
            
            if response.status_code == 200:
                log.info("[TELEGRAM] Foto enviada com sucesso")
                return True
            else:
                log.error(f"[TELEGRAM] Erro HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            log.error(f"[TELEGRAM] Exceção ao enviar foto: {e}")
            return False
    
    def enviar_documento(self, file_path: str, caption: str = "") -> bool:
        """
        Envia documento (CSV, PDF, etc) para o Telegram.
        
        Args:
            file_path: Caminho do arquivo
            caption: Legenda do documento (suporta HTML)
        
        Returns:
            True se enviou com sucesso
        """
        if not self._is_configured():
            log.warning("[TELEGRAM] Não configurado. Documento não enviado.")
            return False
        
        if not Path(file_path).exists():
            log.error(f"[TELEGRAM] Arquivo não encontrado: {file_path}")
            return False
        
        try:
            log.info(f"[TELEGRAM] Enviando documento: {file_path}")
            
            with open(file_path, "rb") as doc_file:
                files = {"document": doc_file}
                data = {
                    "chat_id": self.chat_id,
                    "caption": caption,
                    "parse_mode": "HTML",
                }
                
                response = requests.post(
                    self.send_document_url,
                    data=data,
                    files=files,
                    timeout=30
                )
            
            if response.status_code == 200:
                log.info("[TELEGRAM] Documento enviado com sucesso")
                return True
            else:
                log.error(f"[TELEGRAM] Erro HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            log.error(f"[TELEGRAM] Exceção ao enviar documento: {e}")
            return False
    
    def enviar_relatorio_sentinela(
        self,
        resultado: dict,
        chart_path: Optional[str] = None,
        table_path: Optional[str] = None
    ) -> bool:
        """
        Envia relatório completo do Sentinela.
        
        Args:
            resultado: Dados estruturados do Sentinela
            chart_path: Caminho do gráfico PNG (opcional)
            table_path: Caminho da tabela CSV (opcional)
        
        Returns:
            True se enviou com sucesso
        """
        if not self._is_configured():
            log.warning("[TELEGRAM] Não configurado. Relatório não enviado.")
            return False
        
        try:
            # 1. Envia mensagem resumida
            mensagem = self._formatar_relatorio_sentinela(resultado)
            success_msg = self.enviar_mensagem(mensagem)
            
            if not success_msg:
                log.warning("[TELEGRAM] Falha ao enviar mensagem do relatório")
            
            # 2. Envia gráfico se disponível
            if chart_path and Path(chart_path).exists():
                caption = "📊 <b>Gráfico de Preços</b>"
                success_chart = self.enviar_foto(chart_path, caption)
                if not success_chart:
                    log.warning("[TELEGRAM] Falha ao enviar gráfico")
            
            # 3. Envia tabela se disponível
            if table_path and Path(table_path).exists():
                caption = "📄 <b>Tabela de Concorrentes</b>"
                success_table = self.enviar_documento(table_path, caption)
                if not success_table:
                    log.warning("[TELEGRAM] Falha ao enviar tabela")
            
            return success_msg
            
        except Exception as e:
            log.error(f"[TELEGRAM] Exceção ao enviar relatório: {e}")
            return False
    
    def _formatar_relatorio_sentinela(self, resultado: dict) -> str:
        """
        Formata resultado do Sentinela em HTML para Telegram.
        
        Args:
            resultado: Dados estruturados do Sentinela
        
        Returns:
            Mensagem formatada em HTML
        """
        # Extrai dados com fallbacks seguros
        loja = html.escape(resultado.get("loja", "N/A"))
        keyword = html.escape(resultado.get("keyword", "N/A"))
        total = resultado.get("total_analisado", 0)
        novos = len(resultado.get("novos_concorrentes", []))
        preco_medio = resultado.get("preco_medio", 0)
        menor_preco = resultado.get("menor_preco", 0)
        maior_preco = resultado.get("maior_preco", 0)
        timestamp = resultado.get("timestamp", "N/A")
        
        # Emoji de status
        if novos > 0:
            emoji = "🚨"
            status = "Novos concorrentes detectados!"
        else:
            emoji = "🛡️"
            status = "Sentinela concluído"
        
        # Monta mensagem
        mensagem = (
            f"{emoji} <b>{status}</b>\n\n"
            f"🏪 <b>Loja:</b> {loja}\n"
            f"🔍 <b>Keyword:</b> {keyword}\n"
            f"📊 <b>Concorrentes analisados:</b> {total}\n"
            f"🆕 <b>Novos concorrentes:</b> {novos}\n\n"
            f"💰 <b>Preço médio:</b> R$ {preco_medio:.2f}\n"
            f"🏷️ <b>Menor preço:</b> R$ {menor_preco:.2f}\n"
            f"📈 <b>Maior preço:</b> R$ {maior_preco:.2f}\n\n"
            f"<i>Monitoramento realizado em {timestamp}</i>"
        )
        
        # Adiciona alerta de preço se necessário
        seu_preco = resultado.get("seu_preco")
        if seu_preco and preco_medio > 0:
            diff_percent = ((seu_preco / preco_medio) - 1) * 100
            if diff_percent > 10:
                mensagem += f"\n\n⚠️ <b>Alerta:</b> Seu produto está {diff_percent:.0f}% acima do preço médio."
            elif diff_percent < -10:
                mensagem += f"\n\n✅ <b>Ótimo:</b> Seu preço está {abs(diff_percent):.0f}% abaixo da média!"
        
        return mensagem
    
    # ── Métodos legados (compatibilidade) ─────────────────────
    
    def enviar_alerta(self, mensagem: str) -> bool:
        """
        Método legado para compatibilidade.
        Usa Markdown e converte para HTML básico.
        """
        # Converte Markdown básico para HTML
        mensagem_html = mensagem.replace("*", "<b>").replace("_", "<i>")
        return self.enviar_mensagem(mensagem_html)
    
    @staticmethod
    def formatar_mudanca_preco(produto: str, preco_antigo: float, preco_novo: float) -> str:
        """
        Formata alerta de mudança de preço (compatibilidade).
        
        Returns:
            Mensagem formatada em HTML
        """
        produto_safe = html.escape(produto[:50])
        emoji = "📉" if preco_novo < preco_antigo else "📈"
        seta = "queda" if preco_novo < preco_antigo else "aumento"
        
        return (
            f"{emoji} <b>ALERTA DE PREÇO</b>\n\n"
            f"<b>Produto:</b> {produto_safe}\n"
            f"Detectamos uma {seta} no seu nicho!\n\n"
            f"💰 <b>Anterior:</b> R$ {preco_antigo:.2f}\n"
            f"🚀 <b>Agora:</b> R$ {preco_novo:.2f}"
        )
    
    @staticmethod
    def formatar_novo_concorrente(produto: str, preco: float, ranking: int) -> str:
        """
        Formata alerta de novo concorrente (compatibilidade).
        
        Returns:
            Mensagem formatada em HTML
        """
        produto_safe = html.escape(produto[:50])
        
        return (
            f"🏆 <b>NOVO CONCORRENTE DETECTADO</b>\n\n"
            f"📦 <b>Produto:</b> {produto_safe}\n"
            f"🔥 <b>Posição Atual:</b> #{ranking}\n"
            f"💸 <b>Preço de Venda:</b> R$ {preco:.2f}\n\n"
            f"Cheque o radar para mais detalhes!"
        )
