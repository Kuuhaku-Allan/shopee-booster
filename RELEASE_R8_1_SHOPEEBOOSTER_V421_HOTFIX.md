# ShopeeBooster v4.2.1 - Hotfix Loja e Sentinela Radar Automatica

Data: 2026-05-27

Esta hotfix substitui a v4.2.0 para corrigir o fluxo de instalacao limpa.
A v4.2.0 continua publicada, mas deve ser considerada supersedida.

## Correcoes principais

### Loja conectada

- A interface agora usa o nome simples `Loja`.
- A loja ativa fica salva localmente e e reutilizada por Auditoria, Chatbot e Radar.
- A Loja pode ser conectada a partir do link da Shopee.
- O espelho local e construido/reconstruido pelo navegador quando o scraping normal retorna 0 produtos.
- Produtos salvos na Loja viram produtos proprios elegiveis ao Radar de Concorrentes.

### Sentinela com Radar automatico

- A Sentinela usa Radar automaticamente como fallback quando houver base disponivel.
- O usuario final nao precisa definir variavel de ambiente.
- Para desativar em modo avancado/dev, defina:

```powershell
$env:SHOPEE_SENTINEL_USE_RADAR="0"
```

### Interface simplificada

- `Auditoria Pro` agora aparece como `Auditoria`.
- `Chatbot Concierge` agora aparece como `Chatbot`.
- `Espelho da Loja` agora aparece como `Loja`.
- `Radar Assistido` agora aparece como `Radar de Concorrentes`.
- `Sentinela` foi mantido.

## Validacoes automatizadas

- Loja conectada: 4 testes passando.
- Builder da Loja: 4 testes passando.
- Sentinela/Radar: 16 testes passando.
- Chatbot/Radar: 16 testes passando.
- Auditoria/Radar/Loja: 61 testes passando.
- Radar core: 101 testes passando.
- `py_compile`: OK.

## Smoke esperado em instalacao limpa

1. Abrir o `.exe`.
2. Ir em `Loja`.
3. Informar `https://shopee.com.br/totalmenteseu`.
4. Clicar em `Conectar e construir Loja`.
5. Confirmar produtos salvos.
6. Abrir `Auditoria` e confirmar que a loja conectada aparece.
7. Abrir `Radar de Concorrentes` e confirmar que os produtos proprios aparecem.
8. Abrir `Chatbot` e perguntar sobre preco/listing do produto selecionado.
9. Rodar Sentinela sem definir `SHOPEE_SENTINEL_USE_RADAR`; Radar deve funcionar como fallback.

## Limites conhecidos

- Shopee e Mercado Livre ainda podem exibir bloqueios, login, captcha ou verificacoes.
- A construcao da Loja pelo navegador depende do Chrome do Radar/CDP.
- Se a Loja tiver muitos produtos, a primeira construcao pode demorar.
- Radar de Concorrentes ainda precisa de base criada/renovada por produto para oferecer maxima qualidade.

## Arquivos de release

- `ShopeeBooster-v4.2.1-win-x64.zip`
- `ShopeeBooster-v4.2.1-win-x64.sha256.txt`
