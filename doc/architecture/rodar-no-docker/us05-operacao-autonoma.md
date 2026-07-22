# Arquitetura — US-05: Operar de forma autônoma sem intervenção no runtime

Status: ready-for-validation
Owner: architecture (Lucas Almeida)
Last updated: 2026-07-07 (rev. 1 — revisão e verificação contra o código real)
Rastreabilidade: RF-07, RNF-04; ADR-05, ADR-06; riscos R-4, R-5; R-UX-03/04/07
Escopo: story #20 (US-05), sub-issue de #1 "Rodar no Docker"

## Inputs
- doc/architecture/rodar-no-docker/arquitetura.md (feature-level, rev. 2)
- doc/requirements/rodar-no-docker/requisitos.md (RF-07, RNF-04)
- doc/stories/rodar-no-docker/user-stories.md (US-05)
- doc/ux/rodar-no-docker/us05-{personas-e-jornada,prototipos-terminal,diretrizes-e-avaliacao}.md
- Código real:
  - `src/__main__.py` (`main`, loop principal, `check_config`, `keep_task`, `_is_blocked`)
  - `src/core/config.py` (`check_config`, `_validate_env`, `_validate_agents`)
  - `src/adapters/kiro_cli_agent.py` (`_run` — flag `--no-interactive`)
- Semântica das restart policies do Docker Compose (pesquisa nesta etapa;
  ver §5.3)

---

## 1. Resumo executivo

US-05 **não introduz lógica de negócio nova** (RNF-04, ADR-06). É uma story de
**verificação + especificação arquitetural** do comportamento autônomo: garantir
que, uma vez em pé, o container roda o loop principal ininterruptamente, sem
prompts de `stdin`, com falha clara em erro de setup e com recuperação após
crash — sem ninguém logado na máquina hospedeira.

A conclusão da análise é que **o código já entrega o comportamento exigido**;
a arquitetura desta story consiste em (a) nomear o **modelo de operação
autônoma**, (b) definir a **taxonomia de falhas e o modelo de recuperação** e
(c) resolver a única decisão arquitetural genuína que a story levanta: a tensão
entre **fail-fast** (`SystemExit(1)`) e **`restart: unless-stopped`** (ADR-07).

Nenhuma mudança de código é necessária para a story concluir. As melhorias de
observabilidade levantadas na etapa de UX (R-UX-03/04/07) são reconhecidas aqui
como **débito arquitetural com direção recomendada**, mas ficam **fora do
escopo** (exigiriam código; RNF-04).

---

## 2. Modelo de operação autônoma: duas superfícies

O princípio que organiza toda a story:

> Num sistema headless, **percepção e controle vivem em superfícies separadas**.

| Superfície | Meio | Papel | Quem age |
|-----------|------|-------|----------|
| **Observação** | `docker logs` (stdout) | Ver o que a esteira está fazendo | Operador (leitura) |
| **Controle** | Board do GitHub (Projects) | Decidir o que a esteira deve fazer | Humano de negócio |

O container é **read-only do ponto de vista de controle**: ele não recebe
comandos por `stdin`, não expõe API de controle, não tem console interativo.
Toda decisão humana (inclusive resolver um gate `need_human`) acontece **no
board**, e a esteira a percebe no ciclo de sync seguinte.

Isso é **feature, não limitação**: elimina a necessidade de acesso à máquina
hospedeira (o objetivo da story) e mantém uma única fonte de verdade para o
estado do trabalho (o board). Consequência de design: a qualidade da superfície
de **observação** (o log) é o que determina a confiança do operador — daí a
importância das diretrizes de UX writing (doc de UX, D1–D6).

---

## 3. Taxonomia de falhas e modelo de recuperação

O comportamento autônomo depende de classificar corretamente **cada tipo de
falha** e de aplicar a estratégia certa. A esteira já implementa três camadas,
que esta arquitetura torna explícitas:

### Classe A — Erro transitório de runtime (auto-recuperável no loop)

Rede instável, hiccup do board, rate limit, falha pontual de uma chamada `gh`,
erro na execução de um agente.

- **Estratégia:** absorver dentro do loop; **nunca** derrubar o processo.
- **Evidência no código** (`__main__.py`, `main`):
  - `except PenaltyException` → dorme `wait_seconds` e continua.
  - `except Exception as e: log.error(... "Erro no ciclo (não fatal)") ` →
    loga e dorme `sleep`, **sem sair**.
  - `sync_board`/`process_queue` capturam `PenaltyException` internamente e
    apenas registram, sem propagar.
- **Resultado:** o loop é resiliente por construção. O container **não reinicia**
  para esta classe — ele simplesmente segue no próximo ciclo. Atende RF-07
  (nenhum travamento silencioso: sempre há log com horário de retorno).

### Classe B — Erro permanente de setup/config (fail-fast)

`pipe.yml` ausente/inválido, `PIPE_SSH_KEY_FILE` não definida ou apontando para
arquivo inexistente, contexto de agente vazio, plataforma não suportada,
permissões insuficientes no board.

- **Estratégia:** **fail-fast** — abortar o arranque com `SystemExit(1)` e
  mensagem clara (o quê + como corrigir), antes de o loop começar.
- **Evidência no código:**
  - `check_config()` (`__main__.py`) captura `ConfigError` e faz
    `raise SystemExit(1)`.
  - `config.py`: `_validate_env` (SSH), `_validate_agents` (contexts não-vazios),
    `_validate_boards` (agentes/override válidos) levantam `ConfigError` com
    mensagem acionável.
  - `main()`: plataforma não suportada e `BoardAccessError` também → `SystemExit(1)`.
- **Resultado:** exit-code ≠ 0 imediato e visível em `docker logs`. Atende
  RF-07 (AC-02). **Este é o ponto que interage com a restart policy** — ver §5.

### Classe C — Crash duro do processo

Exceção não capturada fora do loop, `OOMKilled`, sinal do host, bug fatal.

- **Estratégia:** deixar o processo morrer e ser **ressuscitado pelo orquestrador**
  (`restart: unless-stopped`). É o padrão "let it crash": o estado durável vive
  fora do processo (`.pipe/` snapshots/fila/sessions, `repo/`), então reiniciar
  do zero reconstrói o contexto no `board_full_sync`.
- **Resultado:** recuperação automática sem intervenção humana. Atende RF-07
  (AC-03).

> Regra de ouro: **Classe A nunca deve virar Classe C.** O `except Exception`
> genérico no loop é o que garante isso. Qualquer código futuro que rode dentro
> do loop deve preservar esse contrato (nada de exceção escapando do ciclo por
> um erro transitório).

---

## 4. Padrões adotados (o simples que funciona)

A story pede explicitamente evitar arquitetura mirabolante. As escolhas seguem
padrões consagrados e **de baixo custo**, todos já compatíveis com o código:

- **Supervisão externa "let it crash" (estilo supervisor OTP), realizada pela
  restart policy nativa do Docker.** Não há supervisor bespoke, nem `systemd`
  dentro do container, nem processo watchdog próprio. O orquestrador é o
  supervisor. Menos código, menos superfície de falha.
- **12-Factor App, fator IX (Disposability):** o processo é descartável e
  reinicializável a qualquer momento; o estado durável está em volumes
  (`.pipe/`, `repo/`), não na memória do processo. `board_full_sync` reconcilia
  no arranque.
- **12-Factor App, fator XI (Logs as event streams):** a aplicação escreve no
  stdout como um stream; quem coleta/roteia é o ambiente (`docker logs`). Isso
  exige `PYTHONUNBUFFERED=1` para que o buffer do Python não atrase as linhas
  (AC-04).
- **Modo não-interativo como contrato (não como opção):** `kiro-cli chat
  --no-interactive` e a validação **síncrona** de `check_config` garantem que
  nenhum ponto do ciclo bloqueia à espera de `stdin` (AC-01).

Padrões **deliberadamente descartados** por serem excessivos para o escopo:
healthcheck HTTP, métricas/alertas, sidecar de observabilidade, orquestração
K8s. Todos estão fora de escopo em RF/requisitos e não agregam ao objetivo
"rodar sozinho sem travar".

---

## 5. Decisão central: fail-fast × restart policy (ADR-07)

### 5.1 O problema

Classe B (§3) aborta com `SystemExit(1)`. A story exige `restart:
unless-stopped` (AC-03) para recuperar de Classe C. Mas `unless-stopped`
reinicia o container em **qualquer** saída não solicitada — inclusive a saída
fail-fast de um erro **permanente** de config.

Consequência: um `pipe.yml` inválido ou uma `KIRO_API_KEY`/SSH ausente produz um
**crash-loop** — o container reinicia, revalida, falha de novo, indefinidamente,
sem humano no runtime para intervir. Foi exatamente o risco **R-UX-04**
levantado na Prototipação ("`restart: unless-stopped` + erro de config =
crash-loop cego").

### 5.2 Alternativas consideradas

| Opção | Prós | Contras |
|-------|------|---------|
| **A. `unless-stopped` + fail-fast (mantém o atual)** | Recupera Classe C; erro de setup fica **ruidoso e repetido** no log (fail-fast é visível); zero código | Crash-loop em erro permanente; consome CPU/log até o operador corrigir |
| **B. `on-failure:N`** | Para de tentar após N falhas de setup | Também desiste de erros de arranque **transitórios** (ex.: DNS/rede ainda não prontos no boot do host) → perde autonomia; container fica *down* e ninguém percebe sem monitorar `docker ps` |
| **C. Distinguir exit-codes + código novo** (setup=`SystemExit(78)` sem retry; runtime=retry) | Semântica precisa | **Viola RNF-04** (muda lógica); Docker não diferencia exit-code em `unless-stopped` (só `on-failure` olha "≠0", sem faixa); ganho não justifica |

### 5.3 Fatos que embasam a decisão

Semântica das restart policies do Docker Compose (documentação/consenso da
comunidade, conteúdo parafraseado para conformidade de licenciamento):

- `unless-stopped` é o default recomendado para serviços de longa duração:
  reinicia em crash e em reboot do host, mas permanece parado quando o operador
  faz `docker stop` deliberadamente. Ver
  [Docker Restart Policies and Health Checks](https://techearl.com/docker-restart-policies-health-checks).
- `on-failure:N` só reinicia em saída ≠ 0 e **desiste após N tentativas** — bom
  para jobs curtos, ruim para um serviço que precisa sobreviver a hiccups de
  arranque. Ver
  [Docker Compose Restart Policy explained](https://reponotes.com/blog/docker-compose-restart-policy/).
- O daemon do Docker aplica **backoff crescente** entre reinícios (o atraso
  dobra a cada tentativa), o que **limita naturalmente** o desperdício de um
  crash-loop — não é um loop apertado infinito, os reinícios se espaçam.

### 5.4 Decisão

**Adotar a Opção A:** manter `restart: unless-stopped` **e** o fail-fast atual,
**sem mudança de código** (RNF-04, ADR-06). Racional:

1. Um erro permanente de config é **erro do operador**, corrigido **redeployando**
   (ajustar `.env`/`pipe.yml`/volume e `docker compose up -d`). O crash-loop com
   mensagem clara repetida é, nesse contexto, o **sinal fail-fast correto** — e o
   backoff nativo do Docker impede que ele vire um loop apertado.
2. A Opção B trocaria "crash-loop visível" por "container silenciosamente
   parado", o que é **pior** para operação autônoma: some do log e só aparece em
   `docker ps`.
3. A Opção C paga custo de código (violando RNF-04) para um ganho marginal.

**Débito documentado (R-UX-04):** para tornar o crash-loop menos "cego" **sem
mudar a lógica**, a etapa de implementação (US-03/US-06) deve:
- Garantir que a mensagem de fail-fast siga a diretriz D1 (o quê + por quê +
  como corrigir) — já é o caso em `_validate_env`.
- Documentar no guia de operação (RF-08) que "container em `Restarting` +
  mensagem `[Config]` repetida = erro de setup a corrigir e redeployar".
- Opcionalmente, avaliar no futuro um exit distinto para setup que permita, em
  ambientes com orquestrador mais rico, uma política diferenciada — registrado
  como possibilidade, **não** como requisito.

---

## 6. Gate `need_human` sob operação autônoma (AC-05)

O gate `need_human` **não** interrompe o container — ele é resolvido na
superfície de **controle** (board), não na de observação (runtime).

- **Evidência:** `keep_task` → `_is_blocked(issue)` retorna `True` quando o body
  tem `/need_human` (ou `/blocked_by`), e a issue é **pulada** (`continue`); o
  loop segue avaliando as demais e outros boards. O humano marca/desmarca no
  board; no ciclo de sync seguinte a esteira re-lê e retoma.
- **Arquitetura:** isto é a materialização do modelo de duas superfícies (§2). O
  container permanece vivo e produtivo em outras tarefas enquanto uma issue
  aguarda decisão humana. Nenhum gate foi removido (AC-06) — o comportamento é
  **verificado e preservado**, não alterado.
- **Débito (R-UX-07):** o skip é **silencioso** no log — o operador não vê pelo
  stdout que há issue esperando decisão no board. Direção recomendada (futuro,
  fora de escopo): logar 1×/ciclo um resumo das issues em `need_human`, ligando
  as duas superfícies. Exige código → backlog.

---

## 7. Conformidade com os critérios de aceitação

| AC | Exigência | Como a arquitetura atende | Evidência |
|----|-----------|---------------------------|-----------|
| AC-01 | Nenhuma etapa espera `stdin`; `--no-interactive` | Modo não-interativo é contrato (§4); validação síncrona | `kiro_cli_agent.py` (`cmd` com `--no-interactive`); `check_config` |
| AC-02 | Falta de credencial/config → `SystemExit(1)` claro | Classe B / fail-fast (§3) | `check_config`, `_validate_env`, `_validate_agents`, `check_access` |
| AC-03 | `restart: unless-stopped` no compose | Classe C / supervisão externa (§3, §5) | ADR-07; compose de referência em `arquitetura.md` §4.3 |
| AC-04 | `PYTHONUNBUFFERED=1`, logs em tempo real | 12-Factor XI (§4) | Ajuste no Dockerfile/compose (US-01/US-03) |
| AC-05 | `need_human` não interrompe o container | Modelo de duas superfícies (§2, §6) | `keep_task` + `_is_blocked` |
| AC-06 | Nenhum gate de aprovação removido | Comportamento preservado, não alterado (RNF-04) | `pipe.yml` inalterado; `_is_blocked` mantido |

Observação: AC-03 e AC-04 são **realizados** no Dockerfile/compose das stories
de implementação (US-01/US-03); esta arquitetura os **especifica e justifica**,
mas não cria os artefatos (nenhum `Dockerfile`/`docker-compose.yml` existe ainda
no repositório — é correto para uma story de arquitetura).

---

## 8. Decisões arquiteturais desta story (ADR)

- **ADR-07 — `restart: unless-stopped` + fail-fast, sem código novo.** Aceita
  crash-loop com backoff nativo como sinal fail-fast correto para erro
  permanente de setup; rejeita `on-failure:N` (esconde falha) e diferenciação
  de exit-code (viola RNF-04). Mitiga R-UX-04 por documentação/UX writing, não
  por lógica. *(§5)*
- **ADR-08 — Modelo de duas superfícies (log = observação, board = controle).**
  Container read-only para controle; toda decisão humana no board; `need_human`
  não trava o runtime. *(§2, §6)*
- **ADR-09 — Taxonomia de falhas em três classes com contrato "A nunca vira C".**
  Transitório absorvido no loop; permanente em fail-fast; crash duro em restart
  externo. *(§3)*

Reafirma as decisões de nível de feature já vigentes: **ADR-05** (usuário
não-root com HOME gravável) e **ADR-06** (zero alteração de lógica de negócio).

---

## 9. Riscos e débitos residuais

| ID | Item | Sev. | Direção (fora de escopo desta story) |
|----|------|------|--------------------------------------|
| R-UX-04 | Crash-loop cego em erro de config | Média | Documentar em RF-08 + mensagem D1; backoff do Docker já mitiga |
| R-UX-07 | Skip silencioso de `need_human` | Média | Log 1×/ciclo das issues aguardando humano (exige código) |
| R-UX-03 | ~silêncio longo durante execução do agente | Média | Heartbeat de execução (exige código) |
| R-4 | Revogação/rotação da `KIRO_API_KEY` | Baixa | Rotação por env + restart (RF-08/US-06); erros visíveis no log |
| R-5 | `StrictHostKeyChecking no` | Baixa | Débito consciente aceito para github.com |

Nenhum é bloqueador. Os três `R-UX-*` exigem código e pertencem a stories
futuras — a story #20 conclui **sem** implementá-los, pois o comportamento atual
já satisfaz AC-01..AC-06 sem alterar a lógica de negócio (RNF-04/ADR-06).

---

## 10. Conclusão

O comportamento autônomo exigido por US-05 **já está presente no código** e é
explicado por três construções arquiteturais: o **modelo de duas superfícies**
(§2), a **taxonomia de falhas** (§3) e a resolução da **tensão fail-fast ×
restart** (§5, ADR-07). A story se resolve por **especificação e verificação**,
sem tocar na lógica de negócio. As lacunas de observabilidade estão nomeadas
como débito com direção recomendada, prontas para virar backlog de stories
futuras.

---

## 11. Verificação desta revisão (rev. 1)

Cada afirmação sobre o código foi conferida contra o fonte real nesta revisão:

| Afirmação da arquitetura | Local no código | Verificado |
|--------------------------|-----------------|-----------|
| `check_config` faz `SystemExit(1)` ao capturar `ConfigError` | `src/__main__.py::check_config` | ✅ |
| SSH validado por `PIPE_SSH_KEY_FILE` (ausente/inexistente → erro) | `src/core/config.py::_validate_env` | ✅ |
| Contexts vazios → `ConfigError` | `src/core/config.py::_validate_agents` | ✅ |
| Plataforma não suportada e `BoardAccessError` → `SystemExit(1)` | `src/__main__.py::main` | ✅ |
| Loop absorve transitório: `except PenaltyException` (sleep+continua) e `except Exception` ("Erro no ciclo (não fatal)") sem sair | `src/__main__.py::main` | ✅ |
| `sync_board`/`process_queue` capturam `PenaltyException` sem propagar | `src/__main__.py` | ✅ |
| `keep_task` pula issue quando `_is_blocked` (need_human/blocked_by) e segue o loop | `src/__main__.py::keep_task`, `_is_blocked` | ✅ |
| Agente chamado com `--no-interactive --trust-all-tools`; retomada via `--resume-id`/`--list-sessions` | `src/adapters/kiro_cli_agent.py` | ✅ |

Consistência documental: alinhado com `arquitetura.md` (feature, rev. 2 — ADR-05,
ADR-06, `restart: unless-stopped` em §4.3), `requisitos.md` (RF-07, RNF-04) e os
achados de UX (R-UX-03/04/07). Nenhuma divergência encontrada.

**Conclusão da revisão:** o documento está correto, completo e sem mudança de
código pendente. Pronto para validação de arquitetura.
