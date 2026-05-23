# Fase R2.2 - Validacao Shopee com Perfil Persistente Logado

Data de preparacao: 2026-05-23

## Objetivo

Validar se o coletor R2 consegue extrair dados da Shopee quando o usuario esta logado
manualmente no perfil persistente do navegador:

```text
data/browser_profile/
```

Esta fase nao implementa bypass de login, bypass de captcha, automacao de senha,
stealth agressivo, download profundo de midias, IA, Bot WhatsApp, Auditoria ou Sentinela.

## Scripts Criados/Ajustados

### Abrir perfil persistente

Arquivo:

```text
scripts/radar_open_browser_profile.py
```

Uso principal:

```powershell
python scripts/radar_open_browser_profile.py --marketplace shopee
```

Comportamento:

- abre Chromium visivel;
- usa o mesmo perfil persistente do coletor;
- abre `https://shopee.com.br/`;
- imprime instrucao para login/verificacao manual;
- mantem o navegador aberto ate o usuario fechar o navegador ou pressionar ENTER no terminal.

Opcional para teste tecnico rapido:

```powershell
python scripts/radar_open_browser_profile.py --marketplace shopee --auto-close-seconds 5
```

### Coletor interativo

Arquivo ajustado:

```text
scripts/radar_collect_url.py
```

Uso:

```powershell
python scripts/radar_collect_url.py "https://shopee.com.br/Mochila-Notebook-Grande-15-6-I-Connect-Sestini--i.833275000.58209898331" --save --interactive
```

Opcional para ambientes onde o terminal nao recebe ENTER facilmente:

```powershell
python scripts/radar_collect_url.py "https://shopee.com.br/Mochila-Notebook-Grande-15-6-I-Connect-Sestini--i.833275000.58209898331" --save --interactive --interactive-wait-seconds 90
```

Comportamento:

- abre a URL no navegador visivel;
- se detectar login/verificacao, pausa para intervencao manual;
- se campos essenciais vierem vazios, pausa e tenta extrair novamente;
- salva produto, `raw_json`, assets e marca o job como `done` quando `--save` e usado.

## URL de Smoke Shopee

```text
https://shopee.com.br/Mochila-Notebook-Grande-15-6-I-Connect-Sestini--i.833275000.58209898331
```

## Procedimento de Validacao

1. Abrir o navegador persistente:

```powershell
python scripts/radar_open_browser_profile.py --marketplace shopee
```

Se o login via Google mostrar a mensagem `Esse navegador ou app pode nao ser seguro`,
isso e um bloqueio do provedor contra navegadores controlados por automacao. Nao tentar
burlar. Use uma destas alternativas seguras:

- Entrar na Shopee por telefone/e-mail/senha ou QR Code, se disponivel.
- Abrir com Chrome ou Edge instalado, mantendo o mesmo perfil persistente:

```powershell
python scripts/radar_open_browser_profile.py --marketplace shopee --browser-channel chrome
```

ou:

```powershell
python scripts/radar_open_browser_profile.py --marketplace shopee --browser-channel msedge
```

2. Fazer login/verificacao manualmente na Shopee.

3. Fechar o navegador ou pressionar ENTER no terminal.

4. Rodar coleta interativa com save:

```powershell
python scripts/radar_collect_url.py "https://shopee.com.br/Mochila-Notebook-Grande-15-6-I-Connect-Sestini--i.833275000.58209898331" --save --interactive --interactive-wait-seconds 90
```

Se o login foi feito usando Chrome ou Edge, usar o mesmo canal tambem na coleta:

```powershell
python scripts/radar_collect_url.py "https://shopee.com.br/Mochila-Notebook-Grande-15-6-I-Connect-Sestini--i.833275000.58209898331" --save --interactive --interactive-wait-seconds 90 --browser-channel chrome
```

5. Inspecionar o banco:

```powershell
python scripts/radar_inspect_db.py
```

## Resultado da Tentativa de Login Manual

O usuario tentou login manual no perfil persistente com:

- Chromium padrao do Playwright;
- Chrome instalado com `--browser-channel chrome`;
- Microsoft Edge instalado com `--browser-channel msedge`;
- fluxo por telefone.

Resultados reportados:

```text
Nao foi possivel fazer o login
Esse navegador ou app pode nao ser seguro.
Tente usar outro navegador.
```

No fluxo por telefone:

```text
Erro de Carregamento
Desculpe, estamos enfrentando alguns problemas ao carregar, por favor, tente novamente.
```

Interpretacao:

A Shopee/login associado esta bloqueando ou quebrando o fluxo dentro do navegador controlado,
mesmo quando o canal usa Chrome ou Edge instalados. O Radar nao deve tentar burlar esse
bloqueio.

## Status Nesta Sessao

O codigo da R2.2 foi preparado e testado. A validacao autenticada completa da Shopee foi
tentada manualmente, mas continuou bloqueada pelo provedor.

Validacao tecnica executada:

```powershell
python scripts/radar_open_browser_profile.py --marketplace shopee --auto-close-seconds 5
```

Resultado: o Chromium abriu usando `data/browser_profile/` e fechou automaticamente apos o
tempo configurado.

Resultado conhecido:

- o perfil persistente existe e e usado pelo coletor;
- a Shopee abre em navegador visivel;
- Chrome e Edge instalados tambem recebem bloqueio de login nesse fluxo;
- o fluxo por telefone retorna erro de carregamento;
- sem login/verificacao concluido, a Shopee retorna pagina de bloqueio/login ou erro;
- o coletor salva a tentativa em `radar.db` sem tentar bypass;
- Mercado Livre ja foi aprovado com coleta real completa.

## Campos a Conferir Apos Login

Obrigatorios para considerar Shopee aprovado:

- `status=collected`
- `marketplace=shopee`
- `title` do produto preenchido
- `raw_json` preenchido

Desejaveis:

- `price`
- `shop_name`
- `description`
- `image_urls`
- registros em `radar_assets`

## Conclusao

Conclusao atual: **C) Shopee ainda bloqueado mesmo com tentativa de perfil persistente logado.**

Decisao recomendada:

- R3 pode seguir primeiro para Mercado Livre, que ja passou no smoke real.
- Shopee deve ficar marcada como modo assistido limitado/manual.
- Antes de insistir em Shopee, testar um fluxo fora do Playwright, como usuario abrir a pagina
  no navegador normal e o Radar receber HTML/arquivo/exportacao manual em uma fase propria.
- Nao implementar bypass, stealth agressivo ou automacao de login.
