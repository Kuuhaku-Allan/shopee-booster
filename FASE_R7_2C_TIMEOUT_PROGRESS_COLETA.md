# Fase R7.2C — Timeout, Progresso e Resiliência da Coleta no Radar

Esta documentação descreve as causas de travamentos detectados na coleta de concorrentes vinculados sob o modo CDP e as soluções implementadas para tornar o processo resiliente e transparente.

---

## 1. Por que a Coleta Travava?

Anteriormente, o processo de coleta podia ficar travado indefinidamente no Streamlit ("Coletando concorrentes vinculados...") por dois motivos principais:
1. **Espera Manual por Captcha/Login Indefinida**: A função `_wait_for_manual_confirmation` do coletor esperava pela entrada do usuário no console (`input()`). Como o Streamlit executa a coleta em um subprocesso não interativo em segundo plano, essa thread ficava bloqueada esperando um input que nunca viria. Além disso, por padrão o timeout da espera manual era nulo, gerando um loop infinito.
2. **Ausência de Timeouts Estritos no Playwright**: Algumas requisições ou carregamentos podiam demorar muito por rede lenta ou páginas que mantinham conexões HTTP abertas em segundo plano (comum em marketplaces como Shopee/Mercado Livre).

---

## 2. Soluções e Melhorias da R7.2C

### A. Timeouts Nativos e Estritos no Playwright
Abandonamos a abordagem de tentar interromper threads do Python (que pode corromper recursos do navegador e Playwright). Em vez disso, configuramos limites nativos diretamente no objeto `page` do Playwright:
* **Interaction Timeout**: `page.set_default_timeout(10000)` (10 segundos para cliques, scroll, etc.)
* **Navigation Timeout**: `page.set_default_navigation_timeout(30000)` (30 segundos para carregamento)
* **Goto Timeout**: Limite máximo de `30000` (30 segundos) no `page.goto` com fallback rápido.

### B. Detecção Multi-Estágio de Bloqueio/Login
O coletor agora realiza uma verificação preventiva de bloqueio (presença de captcha, login obrigatório, access denied, etc.) em 4 fases distintas do carregamento e coleta:
1. **Logo após o evento `domcontentloaded`**.
2. **Antes de iniciar o scroll da página**.
3. **Logo após o scroll**.
4. **Após a extração dos dados (se vierem vazios)**.

Se qualquer verificação acusar bloqueio, a coleta da URL é abortada imediatamente com `RuntimeError("blocked_or_login_required")`, evitando interagir ou esperar.

### C. Captura Best-Effort de Screenshots em Falha
Ao capturar uma falha na coleta (timeout, bloqueio, etc.), a aplicação faz uma tentativa rápida (máximo 5 segundos) de tirar um screenshot da janela do navegador antes de fechar a página.
* **Caminho**: `data/radar_debug/screenshots/{candidate_uid}_{job_uid}_{timestamp}.png`
* O caminho da screenshot é atrelado como um atributo `screenshot_path` na exceção levantada e propagado até a UI.
* Se a captura falhar (por ex. navegador desconectado), o erro original **não é ocultado** e a execução segue normalmente.

### D. Recuperação de Jobs Travados (`stale running`)
Se a coleta for cancelada pelo usuário, a aplicação fechar de forma abrupta, ou houver crash de energia, alguns jobs podem ficar presos no status `running`.
* Adicionamos a função `mark_stale_running_jobs_as_pending_or_failed(max_age_minutes=10)`.
* Jobs marcados como `running` com mais de 10 minutos são redefinidos para `failed` com erro `"stale_running_job_recovered"`.
* Se o candidato correspondente não possuir dados básicos (`title` e `price` nulos), ele volta para o status `'pending'` permitindo nova tentativa limpa.

### E. Progresso em Tempo Real na UI e Cancelamento
* O subprocesso roda em modo unbuffered (flag `-u` do python) e emite logs formatados com o prefixo `[R7.2C]`.
* O Streamlit consome a saída em tempo real e exibe:
  * URL atual sendo processada.
  * Índice do progresso (ex: `"Coletando 2/5"`).
  * Barra de progresso visual.
  * Etapa atual (`OPENING`, `SCROLLING`, `EXTRACTING`, etc.).
* O botão **Cancelar após URL atual** escreve uma flag no disco (`data/radar_stop_collection.flag`). O loop de coleta verifica o flag entre cada URL e marca os jobs restantes como `skipped` (não falhos).

---

## 3. Tipos de Erros na Coleta

1. **Erro de Ambiente (`environment_error`)**: Ocorre quando a porta CDP (9222) ou navegador do Radar não respondem ou falham ao iniciar. **Não consome tentativas de coleta, não falha jobs e mantém candidatos pendentes**.
2. **Erro de Bloqueio (`blocked_or_login_required`)**: Ocorre quando caímos em captcha ou login obrigatório. Marca o job como `failed` e anexa o screenshot correspondente.
3. **Erro Real de Coleta / Timeout**: Ocorre quando a página demora mais que 30s ou estoura outros timeouts nativos. Marca como `failed` com o log da falha e screenshot.

---

## 4. Onde ficam os Screenshots e logs de Depuração?

* **Screenshots**: Salvas na pasta local `data/radar_debug/screenshots/`. A UI Streamlit exibe a imagem automaticamente dentro do expander de falhas para facilitar o diagnóstico de captchas.
* **Ferramenta de Diagnóstico**: Execute o script a partir do console para inspecionar o status de jobs pendentes/rodando, idades dos jobs e caminhos de screenshots:
  ```bash
  venv\Scripts\python scripts/radar_debug_linked_jobs.py OWN_PRODUCT_UID
  ```
