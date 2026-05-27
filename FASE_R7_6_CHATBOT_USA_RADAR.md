# Fase R7.6 - Chatbot usa Radar

**Status:** implementada  
**Base:** R7.5A concluida

## Objetivo

Fazer o Chatbot usar automaticamente a base Radar quando a pergunta depende de
mercado, concorrentes, preco, titulo, descricao, tags, listing, conversao ou
posicionamento.

Perguntas gerais do app continuam leves e nao chamam Radar.

## Quando usa Radar

O novo servico `shopee_core/chatbot_market_context_service.py` detecta intencoes
de mercado com `should_use_market_context_for_chat()`.

Ativa Radar para perguntas sobre:

- preco e faixa competitiva;
- concorrentes e comparacao;
- titulo, descricao, tags e anuncio;
- otimizacao de listing;
- vendas, conversao, posicionamento e diferencial;
- reviews, avaliacoes e imagem quando ligadas ao produto/listing.

Nao ativa Radar para perguntas gerais, como WhatsApp, Sentinela, cadastro,
Docker, Cloudflare ou uso do app.

## Produto ativo

O Chatbot nao inventa produto.

Se a pergunta precisar de mercado e nao houver produto selecionado, ele responde
que consegue usar o Radar, mas precisa saber qual produto sera analisado.

No WhatsApp, a orientacao e usar `/auditar` ou selecionar um produto primeiro.

## Contexto enviado ao prompt

`get_chatbot_radar_context()` reaproveita:

- `get_radar_market_status_for_audit()`;
- `build_radar_audit_context()`;
- quality gate, freshness e contagens efetivas ja usados pela Auditoria.

O bloco do Chatbot e menor que o da Auditoria e inclui:

- confianca Radar;
- concorrentes efetivos;
- faixa de preco;
- termos fortes;
- features recomendadas;
- features fora de nicho/evitar;
- argumentos comerciais;
- avisos, incluindo base vencida.

Features off-niche, como `notebook`, nao entram em features recomendadas.

## Integracao

`backend_core.process_chat_turn()` agora:

1. detecta se o turno precisa de contexto de mercado;
2. busca Radar apenas quando faz sentido;
3. injeta o bloco no prompt do chat geral;
4. passa `radar_context_block` para `generate_full_optimization()` quando a
   intent e `optimize_listing`;
5. retorna metadados:

```python
{
    "market_context_used": True,
    "market_context_source": "radar",
    "radar_confidence": "high",
    "radar_report_uid": "...",
    "warnings": [],
}
```

`shopee_core/chatbot_service.py` preserva esses metadados para API/WhatsApp.

## UI

O Chatbot no Streamlit mostra um badge discreto no turno do assistente:

```text
Base usada: Radar | Confianca: HIGH
```

Warnings aparecem como legenda curta, sem expor JSON ou debug.

## Gemini

O modelo removido `gemini-3.1-flash-lite-preview` foi substituido por
`gemini-3.1-flash-lite`. A cadeia de fallback de texto segue com 3 modelos:

```python
[
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
]
```

## Testes

Validados:

```bash
.\venv\Scripts\python.exe -m py_compile backend_core.py app.py shopee_core/chatbot_service.py shopee_core/chatbot_market_context_service.py
.\venv\Scripts\python.exe -m pytest test_chatbot_market_context_service.py test_chatbot_service.py -q -p no:cacheprovider
```

Coberturas:

- pergunta sobre preco ativa Radar;
- pergunta sobre concorrentes ativa Radar;
- pergunta geral nao ativa Radar;
- sem produto ativo pede selecao;
- Radar high/fresh gera contexto;
- Radar stale gera contexto com warning;
- Radar ausente gera warning amigavel;
- `notebook` nao entra em recommended features;
- Chatbot injeta Radar no prompt quando a pergunta e de mercado;
- Chatbot nao injeta Radar em pergunta geral;
- `optimize_listing` passa `radar_context_block` para o gerador;
- retorno preserva metadados de contexto de mercado;
- fallback Gemini contem 3 modelos atuais.

## Smoke manual esperado

Produto com Radar high:

- Pergunta: `Meu preco esta bom comparado aos concorrentes?`
- Esperado: usa Radar, fala da faixa de preco e nao inventa dados.

Produto com Radar high:

- Pergunta: `Crie um titulo melhor.`
- Esperado: usa termos fortes do Radar e evita off-niche.

Produto sem Radar:

- Pergunta: `Quais concorrentes eu tenho?`
- Esperado: orienta criar base Radar para uma analise precisa.

Pergunta geral:

- Pergunta: `Como conecto o WhatsApp?`
- Esperado: nao usa Radar.
