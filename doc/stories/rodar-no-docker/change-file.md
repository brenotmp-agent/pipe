# Change File — US-04: Persistir estado de runtime entre reinícios

**Issue:** #19  
**Branch:** `epic19-19-persistir_estado_de_runtime_entre_reinicios`  
**Data de encerramento:** 2026-07-22  
**Rastreabilidade:** RF-06, D-04, D-05, ADR-04, ADR-05, ADR-06  

---

## Resumo

Esta story cobriu as etapas de **requisitos, prototipação UX e arquitetura** da
feature de persistência de estado entre reinícios do container. A implementação
efetiva (compose, código Python, documentação de operação e validação
end-to-end) foi planejada e decomposta em tasks filhas, que estão registradas no
board `task` e aguardam execução.

---

## Alterações entregues

### 1. Documentação de requisitos

**Arquivo:** `doc/stories/rodar-no-docker/user-stories.md`  
**Commit:** `52eca38`

- User story US-04 detalhada com tabela dos 3 diretórios de runtime
  (`.pipe/`, `logs/`, `repo/`) e o impacto de cada um se perdido.
- Comportamento explícito do `startup()` com volumes pré-existentes:
  - `changeQueue.json` é **sempre apagada** (intencional — fila anterior pode
    estar inconsistente; `board_full_sync` repovoará a partir do snapshot).
  - `sessions.json` é **preservado** (continuidade de raciocínio do agente).
  - `repo/<id>` é **reutilizado** se já existe (sem re-clone).
  - `logs/` acumula entre reinícios.
- Critérios de aceitação para modo persistente e modo efêmero (sem volumes,
  sem erro).
- Fora de escopo explícito: backup de volumes, multi-instância, `git pull`
  automático.

**Arquivo:** `doc/stories/rodar-no-docker/requisitos-decisoes.md`  
**Commit:** `52eca38`

- RF-06: requisito funcional de preservação de estado entre reinícios.
- D-04: decisão de design — modo efêmero sem volumes deve funcionar sem erro.
- ADR-04: registro de decisão arquitetural — persistência como opt-in via
  volumes (com contexto, decisão, consequências e alternativas consideradas).

---

### 2. Prototipação UX

**Diretório:** `doc/stories/rodar-no-docker/ux/`  
**Commit:** `0d641d4`

- `us-04-experiencia-persistencia.md`: persona (Operador Diego / CI Camila),
  4 jornadas, avaliação heurística (H-1..H-5), recomendações (R-1..R-5),
  entrevista e referências de mercado/UX.
- `prototipos/docker-compose.prototipo.yml`: persistência por default
  (prevenção de erro), caminhos via `.env`, cada diretório comentado com
  "o que se perde".
- `prototipos/compose.ephemeral.prototipo.yml`: override explícito para modo
  efêmero.
- `prototipos/.env.prototipo`: caminhos de estado parametrizados.
- `prototipos/startup-feedback.md`: wireframe da copy de arranque nos 4
  cenários (persistente novo, persistente retomada, efêmero, bind quebrado).
- `ux/README.md`: índice da documentação de UX.

**Achado principal:** o `startup()` atual não informa se está em modo
persistente ou efêmero — violação da Heurística #1 de Nielsen. Risco: o
operador pode rodar efêmero por engano, perdendo a continuidade de raciocínio
dos agentes sem aviso. Mitigação planejada nas tasks de engenharia (R-1/R-2).

---

### 3. Arquitetura

**Arquivo:** `doc/stories/rodar-no-docker/arquitetura.md`  
**Commits:** `0f75f53`, `51c419e`

- **D-05**: WORKDIR fixo (`/app`) e bind mounts por subdiretório
  (`/app/.pipe`, `/app/repo`, `/app/logs`) — nunca `/app` inteiro.
- **Modelo de ciclo de vida do estado**: cada artefato classificado em
  PRESERVAR / RECONSTRUIR / REUSAR / ACUMULAR.
- **ADR-05**: modo de persistência observável a partir do FS (não por flag),
  com ordem obrigatória no `startup()`: pré-scan → relato de modo → apagar
  fila → clonar/limpar repos.
- **ADR-06**: invariante de instância única sobre os volumes — multi-instância
  não suportada e fora de escopo.
- Checklist de invariantes para engenharia e handoff de quebra em subtasks.

---

### 4. Indexação da documentação

**Arquivos:** `doc/README.md`, `doc/stories/rodar-no-docker/README.md`  
**Commit:** `51c419e`

- `doc/README.md`: índice geral da documentação, com link direto para a
  documentação arquitetural do épico.
- `doc/stories/rodar-no-docker/README.md`: índice por fase (requisitos → UX
  → arquitetura) com destaque para `arquitetura.md`.
- Breadcrumb de localização adicionado ao cabeçalho de `arquitetura.md`.

---

### 5. Planejamento técnico (tasks filhas criadas)

**Commit:** `7044383`  
**Tasks criadas no board `task` (coluna `todo`):**

| # | Task | Bloqueada por | Labels |
|---|------|--------------|--------|
| — | `adicionar-volumes-de-estado-no-compose` | `criar-docker-compose-env-example` | docker, infra |
| — | `implementar-pre-scan-modo-startup` | task acima | backend, docker |
| — | `registrar-invariante-instancia-unica` | `adicionar-volumes-de-estado-no-compose` | docker, infra, docs |
| — | `validacao-end-to-end-persistencia` | tasks 2 e 3 | docker, infra, qa (`/need_human`) |

Todas as tasks têm `/parent #19` e respeitam a ordem de execução definida na
arquitetura (D-05 / ADR-05 / ADR-06).

---

## O que NÃO foi entregue nesta story (fora de escopo ou tasks filhas)

- Implementação do `docker-compose.yml` com volumes de estado → task filha
  `adicionar-volumes-de-estado-no-compose`.
- Relato de modo no `startup()` (`_scan_runtime_state` / `_log_startup_mode`)
  → task filha `implementar-pre-scan-modo-startup`.
- Anotação de invariante de instância única no compose e `operacao.md`
  → task filha `registrar-invariante-instancia-unica`.
- Validação end-to-end com Docker → task filha `validacao-end-to-end-persistencia`
  (requer Docker no host, marcada `/need_human`).
- Estratégia de backup dos volumes e suporte multi-instância — fora de escopo
  (ADR-04 / ADR-06).

---

## Estado do épico pai (#1 — Rodar no Docker)

O épico #1 está bloqueado por `#16`, `#17` e `#19`. Situação atual:

| Story | Coluna | Estado |
|-------|--------|--------|
| #16 — Empacotar a esteira em imagem Docker | `change-file` | Bloqueada por tasks #40, #43, #44, #45 |
| #17 — Autenticar dependências externas em modo headless | `aguardando-tasks` | Bloqueada por tasks #34, #33, #35, #36 |
| #19 — Persistir estado de runtime entre reinícios | `change-file` | Tasks filhas em `todo` (esta story) |

**Conclusão:** o épico #1 ainda não pode avançar — os três bloqueadores
(`#16`, `#17`, `#19`) permanecem abertos com tasks pendentes.
