# ShopeeBooster v4.2.0 - Radar Automatico, Auditoria Inteligente e Sentinela com Radar

Data: 2026-05-27

Esta release consolida o Radar como base local de inteligencia competitiva do ShopeeBooster. O objetivo da versao v4.2.0 e entregar um executavel validado com Radar Automatico, Renovacao, Auditoria, Chatbot e Sentinela integrados sem depender de selecao manual de base de mercado pelo usuario.

## Principais novidades

### Radar Automatico de Concorrentes

- Descoberta automatica de concorrentes no Mercado Livre.
- Cadastro de candidatos, coleta, classificacao e relatorio de padroes em ciclo automatico.
- Quality Gate para evitar confianca alta falsa.
- Agrupamento de variacoes e duplicatas em concorrentes efetivos.
- Renovacao semanal e manual da base Radar.

### Auditoria Pro com Radar automatico

- A Auditoria escolhe automaticamente a melhor base de mercado.
- Usa Radar quando scraping falha ou quando a base Radar e mais confiavel.
- Mostra a fonte usada sem expor debug interno.
- Mantem o fluxo antigo quando o scraping em tempo real esta suficiente.

### Chatbot com contexto de mercado

- O Chatbot usa Radar em perguntas sobre preco, concorrentes, titulo, descricao, tags, listing e vendas.
- Perguntas gerais nao acionam Radar.
- O Chatbot respeita o produto ativo e nao inventa concorrentes quando nao ha base.

### Sentinela com fallback Radar

- A Sentinela pode usar Radar como fonte de concorrentes quando a fonte normal falha ou retorna poucos dados.
- Integracao protegida pela flag `SHOPEE_SENTINEL_USE_RADAR=1`.
- Trigger, lock, scheduler e estado da Sentinela foram preservados.
- O caminho local do executavel tambem passa pela selecao de fonte sem alterar o gatilho.

### Build `.exe` validado

- Executavel final validado em `dist\ShopeeBooster\ShopeeBooster.exe`.
- Launcher escolhe uma porta livre automaticamente quando `8501` esta indisponivel.
- Workers do Radar incluidos no build:
  - `scripts/radar_discover_worker.py`
  - `scripts/radar_collect_linked_worker.py`
- O build retorna erro real quando o PyInstaller falha.
- `version.txt` e `release_meta.py` atualizados para `4.2.0`.

## Validacoes executadas

- `py_compile app.py backend_core.py api_server.py`: OK.
- `compileall shopee_core`: OK.
- Auditoria: 28 testes passando.
- Chatbot: 15 testes passando.
- Sentinela: 15 testes passando.
- Radar: 101 testes passando.
- Build PyInstaller: OK.

## Smoke test do executavel

Validado no `.exe`:

- App abriu em `http://127.0.0.1:8597`.
- Espelho da Loja carregou `totalmenteseu` com 6 produtos.
- Radar abriu e exibiu base/relatorio para `Mochila Infantil Princesa Rosa`.
- Auditoria carregou produto pelo Espelho e detectou Radar automaticamente.
- Chatbot usou Radar em pergunta de preco e mostrou `Base usada: Radar`.
- Sentinela caiu no fallback Radar quando a Shopee retornou 0 concorrentes.
- Sentinela processou resultados e nao ficou presa.
- Debug de workers ficou oculto por padrao, atras de `SHOPEE_DEV_DEBUG_RADAR=1`.

## Atualizacao de versao

- Versao da release: `v4.2.0`.
- `version.txt`: `4.2.0`.
- `release_meta.DEFAULT_VERSION`: `4.2.0`.
- O updater consulta `https://api.github.com/repos/Kuuhaku-Allan/shopee-booster/releases/latest`.
- O updater baixa o primeiro asset `.zip` da release mais recente.
- O comparador de versao trata `4.2` e `4.2.0` como equivalentes para evitar update repetido.
- Durante a aplicacao da atualizacao, o updater preserva:
  - `data`
  - `logs`
  - `pw-browsers`
  - `.shopee_config`

## Como habilitar Radar na Sentinela

Defina a variavel de ambiente:

```powershell
$env:SHOPEE_SENTINEL_USE_RADAR="1"
```

Sem essa flag, o fluxo antigo da Sentinela continua preservado.

## Limitacoes conhecidas

- Shopee e Mercado Livre podem exibir bloqueios, login, captcha ou verificacoes.
- O Radar depende do Chrome local com CDP.
- Shopee segue mais instavel que Mercado Livre para scraping em tempo real.
- A Sentinela com Radar requer `SHOPEE_SENTINEL_USE_RADAR=1`.
- O Radar precisa ter base construida ou renovada por produto para maxima qualidade.
- Se o Radar estiver vencido, Auditoria/Chatbot/Sentinela podem usar a base com aviso ou preferir outra fonte.

## Troubleshooting rapido

### Chrome/CDP nao abre

- Verifique se `http://127.0.0.1:9222/json/version` responde.
- Use o Chrome do Radar, nao o perfil pessoal.
- O perfil oficial e `data/chrome_radar_profile`.
- Se houver PID antigo, feche o Chrome Radar e tente novamente.

### Auditoria nao usa Radar

- Verifique se o produto tem base Radar.
- Verifique se a base esta renovada.
- Verifique o nivel de confianca do Radar.
- Se scraping estiver bom e Radar estiver vencido, a Auditoria pode preferir scraping.

### Chatbot nao usa Radar

- Confirme que ha produto ativo ou selecionado.
- Perguntas gerais nao acionam Radar.
- Perguntas de preco, concorrentes, titulo, descricao, tags, listing e vendas acionam Radar quando ha base.

### Sentinela nao usa Radar

- Confirme `SHOPEE_SENTINEL_USE_RADAR=1`.
- Confirme que ha base Radar para o produto ou nicho monitorado.
- Se a fonte atual retornar concorrentes suficientes, a Sentinela pode manter a fonte atual.

## Assets da GitHub Release

Anexar na release:

- `release\ShopeeBooster-v4.2.0-win-x64.zip`
- `release\ShopeeBooster-v4.2.0-win-x64.sha256.txt`

Nao commitar `dist/`, `.exe`, `.zip`, bancos locais, QR codes, `.env.local` ou dados pessoais no Git.
