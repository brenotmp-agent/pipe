# Change File — US-05: Operar de forma autônoma sem intervenção no runtime

**Issue:** #20
**Branch:** `epic20-20-operar_de_forma_autonoma_sem_intervencao_no_runtime`
**Épico pai:** #1 — Rodar no Docker
**Data:** 2026-07-22
**Responsável:** Isabela Gomes - Tech Lead

---

## Sumário executivo

Esta story (US-05) garante que o container da esteira **opera de forma autônoma
em runtime**: sem prompts de `stdin`, com fail-fast claro em erros de setup, com
`restart: unless-stopped` para recuperação após crash, e com os gates
`need_human` mantidos — o humano atua no board do GitHub, não no container.

**Nenhuma alteração na lógica de negócio foi necessária** (RNF-04, ADR-06). O
comportamento autônomo já estava implementado no código existente; esta story
verificou, documentou e rastreou cada critério de aceitação.

---

## Alterações entregues

### 1. Documentação de produto / requisitos

| Arquivo | Descrição |
|---------|-----------|
| `doc/requirements/rodar-no-docker/requisitos.md` | Documento de requisitos completo (RF-01..RF-08, RNF-01..RNF-05, glossário, rastreabilidade). Existia apenas na feature branch; trazido ao tronco. |
| `doc/stories/rodar-no-docker/user-stories.md` | US-01..US-06 completas com critérios de aceitação numerados, escopo, rastreabilidade, ordem de execução e desambiguação do "sem humano". |

### 2. Arquitetura

| Arquivo | Descrição |
|---------|-----------|
| `doc/architecture/rodar-no-docker/arquitetura.md` | Arquitetura da feature completa (rev. 2): API key, `restart: unless-stopped`, ADR-05/ADR-06. Existia apenas na feature branch; trazido ao tronco. |
| `doc/architecture/rodar-no-docker/us05-operacao-autonoma.md` | Documento de arquitetura específico da US-05. Define ADR-07 (`restart` + fail-fast sem código novo), ADR-08 (duas superfícies: log = observação, board = controle) e ADR-09 (taxonomia de falhas em 3 classes). Tabela de verificação de todos os AC-01..AC-06 contra o código real. |

### 3. UX / Prototipação

| Arquivo | Descrição |
|---------|-----------|
| `doc/ux/rodar-no-docker/README.md` | Enquadramento da pasta UX: benchmark de mercado, personas, fontes consultadas. |
| `doc/ux/rodar-no-docker/us05-personas-e-jornada.md` | Persona Otávio (SRE), jornada em 4 fases, curva emocional, cenários de uso. |
| `doc/ux/rodar-no-docker/us05-prototipos-terminal.md` | 9 protótipos anotados de saída de terminal (P1..P9): arranque, ociosidade/heartbeat, execução do agente, fail-fast, credencial lazy, need_human, rate limit, crash/restart, fluxo no board. Derivados das mensagens reais do código. |
| `doc/ux/rodar-no-docker/us05-diretrizes-e-avaliacao.md` | 7 diretrizes de UX writing, avaliação heurística de Nielsen (5 ✅ / 5 🟡) e backlog priorizado de 9 recomendações `R-UX-*`. |

### 4. Planejamento técnico

| Arquivo | Descrição |
|---------|-----------|
| `doc/stories/rodar-no-docker/us05-task-plan.md` | Plano de 6 tasks (issues #37..#42) com rastreabilidade AC × task, dependências declaradas e agent_level definido. |

---

## Critérios de aceitação — status final

| AC | Critério | Status | Evidência |
|----|----------|--------|-----------|
| AC-01 | `kiro-cli` chamado com `--no-interactive` | ✅ Verificado | `src/adapters/kiro_cli_agent.py` — flag presente na construção do `cmd` |
| AC-02 | Falta de credencial/config gera `SystemExit(1)` com mensagem clara | ✅ Verificado | `src/core/config.py` — `_validate_env` + `_validate_agents` |
| AC-03 | `restart: unless-stopped` declarado no `docker-compose.yml` | 🔲 Pendente task #41 | Responsabilidade do compose (US-03) |
| AC-04 | `PYTHONUNBUFFERED=1` definido | 🔲 Pendente task #40 | Responsabilidade do Dockerfile (US-01) ou compose |
| AC-05 | Gate `need_human` não interrompe o container | ✅ Verificado | `src/__main__.py` — `_is_blocked()` em `keep_task` pulando issues com `/need_human` |
| AC-06 | Nenhum gate de aprovação removido do `pipe.yml` | ✅ Verificado | Código e `CONTEXT.md` — comportamento preservado |

> **Nota:** AC-03 e AC-04 dependem das tasks de infra (#40 e #41) que serão
> executadas nas próximas sprints. O comportamento autônomo **está correto no
> código atual**; os artefatos Docker são o próximo passo de materialização.

---

## Tasks criadas (planejamento técnico)

| # | Título | AC coberto | Status |
|---|--------|------------|--------|
| #37 | Testes: flag `--no-interactive` no kiro-cli | AC-01 | backlog |
| #38 | Testes: fail-fast `SystemExit(1)` no `check_config` | AC-02 | backlog |
| #39 | Testes: `need_human` não interrompe o loop | AC-05, AC-06 | backlog |
| #40 | Dockerfile com `PYTHONUNBUFFERED=1` e usuário não-root | AC-04 | backlog |
| #41 | `docker-compose.yml` com credenciais, volumes e `restart: unless-stopped` | AC-03 | backlog |
| #42 | Guia de operação Docker (runbook) | RF-08 | backlog |

---

## Decisões de design registradas (ADRs)

- **ADR-07:** `restart: unless-stopped` + fail-fast sem código novo. Rejeitados: `on-failure:N` e diferenciação de exit-code (violaria RNF-04).
- **ADR-08:** Duas superfícies separadas — log = observação (`docker logs`), board GitHub = controle. Container read-only para controle.
- **ADR-09:** Taxonomia de falhas em 3 classes (transitório / setup-config / crash duro). Contrato: Classe A nunca vira Classe C.

---

## Débitos técnicos identificados (fora de escopo desta story)

- **R-UX-07 (alta):** gate `need_human` é pulado silenciosamente — o log não avisa que há issue esperando decisão. Recomendado: logar 1×/ciclo um resumo das issues aguardando humano.
- **R-UX-04 (alta):** `restart: unless-stopped` + erro de config = crash-loop cego. Avaliar `on-failure` com exit-code específico para erros permanentes.
- **R-UX-03 (alta):** ~22 min de silêncio no stdout durante execução do agente — recomendado: heartbeat de execução.

---

## Rastreabilidade

- **Requisitos:** RF-07, RNF-04
- **ADRs:** ADR-05, ADR-06, ADR-07, ADR-08, ADR-09
- **Riscos:** R-4, R-5
- **Story:** US-05 em `doc/stories/rodar-no-docker/user-stories.md`
