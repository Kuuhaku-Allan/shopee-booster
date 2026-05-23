# Fase R5.1A - Chrome Real Dedicado via CDP

## Objetivo

Adicionar um modo de navegador real dedicado para o Radar Assistido usando Chrome DevTools Protocol (CDP).

Esta fase existe porque a primeira tentativa da R5.1 mostrou verificacao/login no Mercado Livre ao usar uma sessao de navegador automatizada/isolada. O Radar deve funcionar de forma assistida: o usuario abre um Chrome real, faz login manualmente e resolve verificacoes sem bypass.

## Por que nao usar guia anonima

Guia anonima nao resolve o problema. Ela comeca sem cookies, sem login, sem historico e sem sessao persistente, o que tende a aumentar verificacoes.

O caminho recomendado e usar um Chrome real dedicado ao ShopeeBooster, separado do perfil pessoal principal.

## Perfil dedicado

O perfil fica em:

```text
data/chrome_radar_profile/
```

Esse diretorio e ignorado pelo Git. Ele guarda cookies/sessao do Chrome do Radar.

Nao use o perfil pessoal `Default` do Chrome como perfil do Radar, especialmente enquanto o Chrome principal estiver aberto. O Chrome pode bloquear o perfil se duas instancias tentarem usar a mesma pasta.

## Como iniciar o Chrome do Radar

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\local\start-radar-chrome.ps1
```

Opcoes:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\local\start-radar-chrome.ps1 -Marketplace shopee
powershell -ExecutionPolicy Bypass -File .\deploy\local\start-radar-chrome.ps1 -Port 9222
```

Atalho Python:

```bash
python scripts/radar_start_browser_cdp.py
python scripts/radar_start_browser_cdp.py --marketplace shopee
```

Depois de abrir o Chrome, faca login manual no Mercado Livre/Shopee nesse navegador.

## Como rodar coletores com CDP

Coleta por URL:

```bash
python scripts/radar_collect_url.py "URL" --browser-mode cdp
```

Coleta profunda Mercado Livre:

```bash
python scripts/radar_collect_deep_url.py "URL_ML" --save-assets --browser-mode cdp
```

Fila pendente:

```bash
python scripts/radar_collect_pending.py --limit 5 --save-assets --browser-mode cdp
```

Smoke R5.1:

```bash
python scripts/radar_run_full_market_smoke.py --browser-mode cdp --manual-login-check
```

Se o Chrome estiver em outra porta:

```bash
python scripts/radar_run_full_market_smoke.py --browser-mode cdp --cdp-url http://127.0.0.1:9223
```

## Comportamento em login/verificacao

Quando `--browser-mode cdp` detecta login, captcha, verificacao ou tela vazia, o coletor pausa e pede:

```text
Resolva a verificacao/login no Chrome do Radar e pressione ENTER para continuar.
```

Depois disso, ele recarrega a pagina e tenta extrair novamente.

## Limites

- Nao ha bypass de login, captcha ou verificacao.
- Nao ha stealth agressivo.
- Nao ha roubo/copia de cookies do Chrome pessoal.
- O usuario precisa manter o Chrome do Radar aberto enquanto usa `--browser-mode cdp`.
- O smoke R5.1 deve ser repetido depois que o usuario fizer login manual no perfil dedicado.

## Verificacoes

Rodar:

```bash
python test_radar_browser_service.py
python test_radar_service.py
python test_radar_collector.py
python test_radar_assets_service.py
python test_radar_relevance_service.py
python test_radar_patterns_service.py
python -m compileall shopee_core scripts
```

## Conclusao

R5.1A prepara o Radar para validar a R5.1 em um Chrome real dedicado, com sessao persistente autorizada pelo usuario e sem qualquer tentativa de contornar bloqueios.
