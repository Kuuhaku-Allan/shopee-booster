import requests

class TelegramSentinela:
    def __init__(self, token=None, chat_id=None):
        from sentinela_db import obter_config
        self.token = token or obter_config("telegram_token")
        self.chat_id = chat_id or obter_config("telegram_chat_id")
        # Previne iniciar com os placeholder
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage" if self.token else None

    def testar_conexao(self):
        return self.enviar_alerta("Shopee Booster Online! 🚀\nSentinela ativada e pronta para o monitoramento.")

    def enviar_alerta(self, mensagem):
        if not self.token or not self.chat_id or not self.api_url:
            return False
        
        payload = {
            "chat_id": self.chat_id,
            "text": mensagem,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(self.api_url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception:
            return False

    @staticmethod
    def formatar_mudanca_preco(produto, preco_antigo, preco_novo):
        emoji = "📉" if preco_novo < preco_antigo else "📈"
        seta = "queda" if preco_novo < preco_antigo else "aumento"
        return (
            f"{emoji} *ALERTA DE PREÇO: {produto[:30]}*\n\n"
            f"Detectamos uma {seta} no seu nicho!\n"
            f"💰 *Anterior:* R$ {preco_antigo:.2f}\n"
            f"🚀 *Agora:* R$ {preco_novo:.2f}"
        )

    @staticmethod
    def formatar_novo_concorrente(produto, preco, ranking):
        return (
            f"🏆 *NOVO CONCORRENTE DETECTADO*\n\n"
            f"📦 *Produto:* {produto[:30]}\n"
            f"🔥 *Posição Atual:* #{ranking}\n"
            f"💸 *Preço de Venda:* R$ {preco:.2f}\n"
            f"Cheque o radar para mais detalhes!"
        )
