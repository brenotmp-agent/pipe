# US-05 — Protótipos de saída de terminal e fluxo no board

Status: draft
Owner: ux (Talita Souza)
Last updated: 2026-07-07
Rastreabilidade: RF-07, RNF-04; ADR-05, ADR-06; R-4, R-5 · Issue #20

> Num sistema headless, **a "tela" é o log**. Estes protótipos são mockups
> anotados da saída de `docker logs`, o único canal pelo qual o operador percebe
> o estado do sistema. Todos foram derivados das mensagens **reais** emitidas
> pelo código atual (`src/__main__.py`, `src/core/log.py`,
> `src/adapters/kiro_cli_agent.py`) — não são invenção de UX.

## Como ler estes protótipos

- Formato real de cada linha (definido em `log.py`): `HH:MM:SS [Módulo] mensagem`.
- No terminal os `[colchetes]` saem coloridos por nível (INFO negrito, WARNING
  amarelo, ERROR vermelho). Aqui representamos em texto puro.
- Legenda de anotação:
  - `✅` comportamento que já entrega boa experiência (verificação da US-05).
  - `⚠️` ponto de fricção / ambiguidade percebida pelo operador.
  - `💡` oportunidade de melhoria → vira recomendação `R-UX-*` (backlog, fora do escopo desta story).

---

## P1 — Arranque saudável (Fase 1 da jornada: primeiro `up`)

Cenário de referência #1 (feliz). O operador roda `docker compose up -d` e
`docker logs -f esteira`.

```text

 _____ ____ _____ _____ ___ ____      _
| ____/ ___|_   _| ____|_ _|  _ \   / \
|  _| \___ \ | | |  _|  | || |_) | / _ \
| |___ ___) || | | |___ | ||  _ < / ___ \
|_____|____/ |_| |_____|___|_| \_/_/   \_\

13:38:00 [Pipe] Iniciando esteira agêntica v1.4.2
13:38:00 [Config] Validando pipe.yml
13:38:00 [Config] pipe.yml válido
13:38:00 [Startup] Verificando repositórios
13:38:01 [Startup] Clonando main
13:38:07 [Board] Sincronizando estrutura local
13:38:07 [Board] Sincronizando boards remotos
13:38:19 [Board] Detectando mudanças remotas
13:38:19 [Board] Analisando board 'story'
13:38:24 [Board] 3 mudança(s) remota(s) adicionada(s) à fila
13:38:31 [Pipe] Esteira agêntica iniciada
```

Anotações:
- ✅ **Banner + versão logo no topo** — resposta imediata a "subiu?" e "qual
  versão?". Reduz a ansiedade da Fase 1 (curva emocional 😟→🙂).
- ✅ **Sequência legível de fases** (Config → Startup → Board → Pipe): o operador
  acompanha o progresso sem conhecer o código. Mapeia direto ao mental model da
  persona Otávio.
- ✅ **`Esteira agêntica iniciada`** é o marco explícito de "de pé". Bom fecho de
  onboarding.
- 💡 `R-UX-01`: as fases não têm marcador de "passo X de N", então num clone lento
  (`Clonando main`) o operador não sabe quanto falta. Um contexto de duração
  esperada ajudaria (backlog).

---

## P2 — Regime permanente e ociosidade (Fase 2: heartbeat)

Cenário #1 (feliz, continuação). Não há trabalho; a esteira varre os boards e
dorme. **Este é o protótipo mais importante da story**: é o que prova "vivo, não
travado".

```text
13:39:02 [Sleep] Nenhuma atividade - dormindo 60s (retorna às 13:40:02)
13:40:02 [Sleep] Nenhuma atividade - dormindo 60s (retorna às 13:41:02)
13:41:02 [Sleep] Nenhuma atividade - dormindo 60s (retorna às 13:42:02)
```

Anotações:
- ✅ **Heartbeat com horário de retorno** resolve a dor #1 da persona ("está
  travado ou só ocioso?"). O `(retorna às HH:MM:SS)` é um sinal de vida
  previsível — o operador sabe exatamente quando esperar a próxima linha.
- ✅ Combina com a categoria de mercado (GitHub Actions runner "Listening for
  Jobs", schedulers com "tick"): **espera visível**, não silêncio.
- ⚠️ Entre o fim de um ciclo com trabalho e o `Sleep`, se um board é varrido sem
  achar tarefa, **não há linha** dizendo "varri board X, nada aqui". O salto
  direto para `Sleep` é econômico, mas esconde o trabalho de varredura.
- 💡 `R-UX-02`: log opcional de nível DEBUG por board varrido ("board 'story'
  sem tarefa elegível") daria rastreabilidade sem poluir o INFO (backlog).

---

## P3 — Execução de agente (Fase 2: há trabalho)

Cenário #1. Uma tarefa elegível é selecionada e executada.

```text
13:42:05 [KeepTask] [story] auto-advance #20: todo → doing
13:43:07 [KeepTask] [story] #20 selecionada em 'doing'
13:43:07 [Agent] [story] #20 agent='engineering' model='claude-sonnet-4' cwd='repo/main' log='logs/20/2026-07-07_13-43-07.md'
13:43:09 [Agent] [story] #20 retomando sessão 7f3a...e21b
14:05:44 [Agent] [story] #20 execução concluída
```

Anotações:
- ✅ **Linha de contexto rica** (`agent`, `model`, `cwd`, `log`): o operador sabe
  qual agente/model rodou e **onde ler o detalhe** (`log=...`). Excelente para
  auditoria sem parar o container.
- ✅ **`retomando sessão`** torna visível a continuidade de raciocínio entre
  execuções — reforça confiança de que o sistema não "recomeça do zero".
- ⚠️ Entre `agent=...` (13:43) e `execução concluída` (14:05) há **~22 min de
  silêncio** no log da esteira (o diálogo do agente vai para o arquivo `logs/20/...md`,
  não para o stdout). Para quem observa `docker logs`, parece parado.
- 💡 `R-UX-03`: um heartbeat "agente em execução há Xmin" ou o encaminhamento de
  marcos do agente para o stdout eliminaria a ambiguidade do silêncio longo
  (backlog — exige código, fora do escopo RNF-04).

---

## P4 — Fail-fast de setup (Cenários #2 e #3: AC-02)

O momento de maior fricção da jornada. **A qualidade desta mensagem decide se o
operador resolve em 30s ou abre chamado.**

### P4a — Falta `PIPE_SSH_KEY_FILE` (cenário #2)

```text

 _____ ____ _____ _____ ___ ____      _
 ...banner...

13:38:00 [Pipe] Iniciando esteira agêntica v1.4.2
13:38:00 [Config] Validando pipe.yml
13:38:00 [Config] Variável de ambiente 'PIPE_SSH_KEY_FILE' não definida ou vazia. Defina com: export PIPE_SSH_KEY_FILE=~/.ssh/id_ed25519
```
→ processo encerra com **exit-code 1** (`SystemExit(1)` em `check_config`).

### P4b — Contexto de agente vazio (cenário #3)

```text
13:38:00 [Config] Validando pipe.yml
13:38:00 [Config] Arquivos de contexto vazios (preencha antes de executar):
  - contexts/github/engineering.md
  - contexts/github/ux.md
```
→ exit-code 1.

Anotações:
- ✅ **Falha imediata, antes do loop** (validação síncrona em `check_config`):
  atende AC-02 e a dor #2 da persona ("subiu errado e não percebi").
- ✅ **Mensagem já segue boa prática de CLI**: diz *o que* faltou e, no caso do
  SSH, *como corrigir* (`Defina com: export ...`). Alinhado às diretrizes do
  PatternFly/Shopify (o quê + como).
- ✅ **exit-code != 0** permite que o `restart: unless-stopped` **não** entre em
  loop cego? — atenção: com `restart: unless-stopped`, um erro de config faz o
  container reiniciar e falhar de novo. Ver ⚠️ abaixo.
- ⚠️ **Interação restart × fail-fast**: `unless-stopped` reinicia após crash duro
  (bom para AC-03), mas também reinicia após `SystemExit(1)` de config — gerando
  um *crash loop* silencioso se a credencial estiver errada. O operador vê o
  mesmo erro repetindo a cada poucos segundos.
- 💡 `R-UX-04`: distinguir "erro de setup (não adianta reiniciar)" de "crash
  transitório (vale reiniciar)". Opções: (a) documentar que erro de config deve
  ser lido no `docker logs` e corrigido no `.env`; (b) considerar
  `restart: on-failure` com limite, ou um exit-code específico para config.
  **Decisão fica para US-03/Arquitetura** — aqui só registramos o efeito de UX.
- 💡 `R-UX-05`: a linha do erro de config usa o mesmo módulo `[Config]` do
  sucesso. Um prefixo visual de severidade textual (ex.: `ERRO:`) ajudaria quem
  filtra `docker logs` por texto, já que a cor ANSI pode se perder em
  agregadores de log.

---

## P5 — Credencial lazy inválida (Cenário #4: não trava)

`GH_TOKEN`/`KIRO_API_KEY` inválidos passam pelo `check_config` (que só valida
SSH e contexts) e falham na **primeira operação real**.

```text
13:38:31 [Pipe] Esteira agêntica iniciada
13:38:33 [Sync] [story] Penalty no sync remoto
13:38:33 [Pipe] Erro no ciclo (não fatal): <detalhe da falha de credencial>
13:39:33 [Sleep] Nenhuma atividade - dormindo 60s (retorna às 13:40:33)
```

Anotações:
- ✅ **O loop não morre**: `except Exception ... Erro no ciclo (não fatal)` mantém
  o container vivo e tenta de novo no próximo ciclo. Coerente com "operação
  autônoma".
- ⚠️ **A causa raiz fica genérica**: `Erro no ciclo (não fatal): {e}` não deixa
  óbvio que é *credencial inválida* vs. *erro de rede* vs. *bug*. O operador
  precisa abrir o log de arquivo (JSON) para o traceback.
- 💡 `R-UX-06`: para falhas de autenticação, uma mensagem categorizada
  ("credencial do GitHub rejeitada — verifique GH_TOKEN") encurtaria o
  diagnóstico. Liga-se ao risco R-4 (rotação de `KIRO_API_KEY`). Backlog.

---

## P6 — Gate `need_human` (Cenário #5: AC-05, o container NÃO para)

Uma issue tem `/need_human` no body. A esteira a ignora (`_is_blocked` em
`keep_task`) e segue.

```text
13:45:07 [KeepTask] [story] #18 selecionada em 'doing'
13:45:07 [Agent] [story] #18 agent='engineering' model='claude-sonnet-4' cwd='repo/main' log='logs/18/...md'
14:02:11 [Agent] [story] #18 execução concluída
14:02:12 [Sleep] Nenhuma atividade - dormindo 60s (retorna às 14:03:12)
```
(A issue #20, marcada `/need_human`, simplesmente **não aparece** — foi pulada
em silêncio; o operador a vê parada **no board do GitHub**.)

Anotações:
- ✅ **Comportamento correto e verificado** (AC-05): o gate humano não interrompe
  o runtime. A ação humana acontece no board; no ciclo seguinte ao movimento, o
  sync retoma. Confirma a decisão de produto ("container nunca é ponto de
  intervenção").
- ⚠️ **Invisibilidade do gate no log** é a maior fricção da Fase 3: uma issue
  `need_human` é pulada *silenciosamente*. Do ponto de vista do `docker logs`,
  não há como saber que "existe algo esperando um humano no board". O operador
  pode achar que está tudo ocioso quando na verdade há decisão pendente.
- 💡 `R-UX-07` (prioridade alta no backlog): logar, uma vez por ciclo, um resumo
  do tipo `N issue(s) aguardando humano no board (ex.: #20)`. Isso conecta as
  duas superfícies (log ↔ board) sem violar RNF-04 de forma invasiva — é
  observabilidade, não mudança de fluxo. **Registrar como issue separada.**

---

## P7 — Rate limit (Cenário #6: throttle/penalty visível)

```text
13:50:02 [Board] Rate limit em 'story' - retorna às 13:51:06
13:51:06 [Board] Analisando board 'story' - tentativa 2
...
14:10:00 [Pipe] Penalty - aguardando até 15:10:00
```

Anotações:
- ✅ **Throttle e penalty são explícitos e com horário de retorno** — mesma boa
  prática do heartbeat de sleep: espera previsível, não silêncio. O operador
  entende que é o GitHub limitando, não um bug.
- ✅ **`tentativa 2`** mostra que há retry automático — recuperação sem
  intervenção.
- ⚠️ Um `Penalty - aguardando até 15:10:00` (1h) pode assustar quem não conhece o
  mecanismo (parece "travado por 1h"). É esperado, mas não óbvio.
- 💡 `R-UX-08`: documentar no guia de operação (US-06) o que significam
  throttle/penalty, para o operador não confundir com falha. Doc, não código.

---

## P8 — Crash duro e restart (Cenário #7: AC-03)

Processo morre (OOM, kill, bug fatal). Com `restart: unless-stopped`, o Docker
sobe de novo. O estado persistido (`.pipe/`) evita recomeço do zero.

```text
14:20:00 [Agent] [story] #22 agent='engineering' ...
--- container morre (sem linha de log; visível em `docker ps` / exit-code) ---
--- docker reinicia o container (restart: unless-stopped) ---

 ...banner novamente...
14:20:45 [Pipe] Iniciando esteira agêntica v1.4.2
14:20:45 [Config] pipe.yml válido
14:20:46 [Startup] Verificando repositórios
14:20:46 [Startup] Removendo fila de mudanças anterior
14:20:52 [Board] Sincronizando estrutura local
...
14:21:10 [Pipe] Esteira agêntica iniciada
```

Anotações:
- ✅ **O banner reaparecendo é o sinal de "reiniciei"** — o operador reconhece o
  restart pelo re-arranque. Curva emocional 😰→😌.
- ✅ **Estado preservado**: `.pipe/` (snapshots, sessões) sobrevive via volume
  (RF-06); a issue em andamento retoma via `--resume-id`. A fila (`QUEUE_FILE`) é
  intencionalmente limpa no startup e reconstruída pelo sync — comportamento
  correto, não perda de dados.
- ⚠️ **Não há linha explícita "reiniciando após queda"** — o operador infere pelo
  banner repetido. Para quem não acompanhou o momento da queda, dois banners no
  histórico de log podem confundir a linha do tempo.
- 💡 `R-UX-09`: uma linha de boot indicando uptime/contagem de reinícios (se
  disponível via env do Docker) daria contexto. Backlog / observabilidade.

---

## P9 — Fluxo humano no board (a "outra tela")

A segunda superfície de UX. Não é terminal — é o board do GitHub. Fluxo da
persona secundária (Renata) e da Fase 3 de Otávio.

```text
┌─────────────────────────────────────────────────────────────────┐
│  Board do GitHub (navegador) — plano de controle                  │
│                                                                   │
│   [To Do]        [Doing]         [Aguarda Humano]     [Done]      │
│                                   ┌───────────┐                   │
│                                   │  #20      │  ← card parado    │
│                                   │ need_human│    aqui           │
│                                   └───────────┘                   │
│                                        │                          │
│              Renata revisa e ARRASTA o card ─┐                    │
│                                              ▼                    │
│   [To Do]        [Doing]         [Aguarda Humano]     [Aprovado]  │
│                                                        ┌────────┐ │
│                                                        │  #20   │ │
│                                                        └────────┘ │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼  (no ciclo seguinte, sem tocar no container)
14:35:07 [Board] Analisando board 'story'
14:35:11 [Board] 1 mudança(s) remota(s) adicionada(s) à fila
14:35:14 [KeepTask] [story] #20 selecionada em 'aprovado'
```

Anotações:
- ✅ **Separação percepção/ação respeitada**: o humano só arrasta o card no
  board; o container detecta a mudança no sync e retoma sozinho. Nenhum acesso
  à máquina. É o coração da US-05 e está funcionando.
- ✅ Alinha com o padrão de mercado (schedulers cujo controle vive numa UI de
  board/DAG separada do worker).
- 💡 `R-UX-07` (mesma de P6) fecha o ciclo: se o log avisasse "#20 aguardando
  humano", Otávio saberia ir ao board sem precisar descobrir por conta própria.

---

## Síntese dos protótipos → verificação da US-05

| Protótipo | AC coberto | Veredito de UX |
|-----------|------------|----------------|
| P1 Arranque | RF-07 | ✅ Onboarding claro; banner+versão+fases |
| P2 Ociosidade | AC-04, RF-07 | ✅ Heartbeat com horário resolve "vivo vs. travado" |
| P3 Agente | AC-01 | ✅ Contexto rico; ⚠️ silêncio longo durante execução |
| P4 Fail-fast | AC-02 | ✅ Falha imediata e explicada; ⚠️ crash loop c/ restart |
| P5 Cred. lazy | RF-07 | ✅ Não trava; ⚠️ causa raiz genérica |
| P6 need_human | AC-05 | ✅ Não interrompe; ⚠️ gate invisível no log |
| P7 Rate limit | — | ✅ Explícito com horário de retorno |
| P8 Crash/restart | AC-03 | ✅ Recupera sozinho + estado preservado |
| P9 Board | AC-05, AC-06 | ✅ Ação humana fora do container |

**Conclusão:** o comportamento atual **já entrega uma boa experiência autônoma**
e satisfaz os critérios de aceitação da US-05 sem alteração de lógica (RNF-04).
As fricções (⚠️) viram recomendações `R-UX-*` no
[`us05-diretrizes-e-avaliacao.md`](us05-diretrizes-e-avaliacao.md) — backlog de
observabilidade, **fora do escopo** desta story.
