# Arquitetura — US-04: Persistir estado de runtime entre reinícios

Status: draft
Owner: arquitetura (Lucas Almeida)
Stage: Arquitetura
Last updated: 2026-07-21
Localização: `doc/stories/rodar-no-docker/arquitetura.md` (indexada em
`doc/README.md` e `doc/stories/rodar-no-docker/README.md`)

## Inputs

- doc/stories/rodar-no-docker/user-stories.md (US-04)
- doc/stories/rodar-no-docker/requisitos-decisoes.md (RF-06, D-04, ADR-04)
- doc/stories/rodar-no-docker/ux/us-04-experiencia-persistencia.md (H-1..H-5, R-1..R-5)
- doc/stories/rodar-no-docker/ux/prototipos/ (compose, .env, startup-feedback)
- doc/product/rodar-no-docker/{vision,problem-space,epicos}.md
- CONTEXT.md (arquitetura hexagonal, snapshot, fila, sessões)
- src/__main__.py → `startup()`, `main()` (comportamento real)
- src/core/change_queue.py (`PIPE_DIR`, `QUEUE_FILE`)
- src/core/snapshot.py (`BOARDS_DIR = .pipe/boards`)
- src/core/session.py (`SESSIONS_FILE = .pipe/sessions.json`)
- src/adapters/github_board.py (`_throttle_file = .pipe/throttle`)

---

## 1. Objetivo e escopo

Definir a arquitetura que permite ao container preservar (ou descartar) o
estado de runtime entre reinícios, atendendo RF-06 e D-04 sob a decisão já
tomada na ADR-04 (persistência **opt-in** via volumes).

Esta etapa **não implementa** código nem o `docker-compose.yml`/`Dockerfile`
final. Ela fixa o contrato de volumes, o modelo de ciclo de vida do estado, as
invariantes que o código deve respeitar e as duas decisões de arquitetura novas
que a etapa de engenharia precisa executar (ADR-05, ADR-06).

**Princípio norteador (do enunciado da tarefa):** o simples que funciona.
Nenhum componente novo de infraestrutura (banco, cache, daemon de lock, store
externo), nenhuma dependência nova de biblioteca e nenhuma flag de configuração
nova. A persistência é uma propriedade do **sistema de arquivos + volumes
Docker**, e o modo de operação é **derivado** desse sistema de arquivos, não
declarado.

---

## 2. Contexto arquitetural existente

A esteira é uma aplicação hexagonal de processo único que roda um loop
(`main()` em `src/__main__.py`). Todo o estado durável é gravado em **três
diretórios de caminho relativo**, resolvidos contra o diretório de trabalho do
processo (cwd):

| Diretório | Módulo dono | Constante |
|-----------|-------------|-----------|
| `.pipe/` | change_queue / snapshot / session / adapter | `PIPE_DIR = Path(".pipe")`, `BOARDS_DIR`, `SESSIONS_FILE`, `_throttle_file` |
| `repo/` | `__main__` / agent | `REPO_DIR = Path("repo")` |
| `logs/` | log (via `log.dir` do pipe.yml) | configurável |

Como os caminhos são **relativos**, o cwd do processo é o que "ancora" todo o
estado. Esta é a alavanca arquitetural que torna a containerização trivial: se
o container fixa um `WORKDIR` conhecido e os volumes são montados sobre os três
subdiretórios, a persistência acontece sem qualquer mudança de código
(coerente com ADR-04).

---

## 3. Visão de componentes (persistência)

```
                    HOST                                CONTAINER (WORKDIR=/app)
 ┌───────────────────────────────┐          ┌─────────────────────────────────────┐
 │  ${PIPE_STATE_DIR}  (.pipe)    │◀── bind ─▶│ /app/.pipe                          │
 │    boards/<id>/snapshot.json   │          │   ← baseline do full sync           │
 │    sessions.json               │          │   ← continuidade do agente          │
 │    throttle                    │          │   ← valor de throttle               │
 │    changeQueue.json  (volátil) │          │   ← apagada no startup (sempre)     │
 │                                │          │                                     │
 │  ${PIPE_REPO_DIR}   (repo)     │◀── bind ─▶│ /app/repo/<id>  ← reusa se existe   │
 │                                │          │                                     │
 │  ${PIPE_LOGS_DIR}   (logs)     │◀── bind ─▶│ /app/logs       ← acumula (TTL)     │
 └───────────────────────────────┘          │                                     │
                                             │  esteira (python -m src)            │
   pipe.yml, contexts/  (US-02, :ro) ───────▶│  /app/pipe.yml, /app/contexts       │
   segredos (US-03) ────────────────────────▶│  env + binds :ro                    │
                                             └─────────────────────────────────────┘
```

Config e segredos (US-02/US-03) são montados **read-only** e **não** são estado
de runtime — ficam fora do escopo de persistência desta story, mas aparecem no
diagrama para situar o contrato completo de volumes do container.

---

## 4. Contrato de volumes (D-05)

### D-05 — WORKDIR fixo e mapeamento 1:1 de subdiretórios de estado

O container **deve** declarar `WORKDIR /app` e o processo **deve** iniciar com
cwd = `/app`. Os volumes de estado mapeiam host → container assim:

| Host (parametrizável via `.env`) | Container | Modo | Classe |
|----------------------------------|-----------|------|--------|
| `${PIPE_STATE_DIR:-./.pipe}` | `/app/.pipe` | rw | estado (persistir) |
| `${PIPE_REPO_DIR:-./repo}` | `/app/repo` | rw | estado (persistir) |
| `${PIPE_LOGS_DIR:-./logs}` | `/app/logs` | rw | conveniência |

Regras da decisão:

- O mapeamento é **por subdiretório** (`/app/.pipe`, não `/app`). Montar `/app`
  inteiro sobrescreveria o código da imagem — proibido.
- Os caminhos do host vêm de variáveis `.env` (R-3/R-4 da UX): o operador não
  edita YAML.
- Persistência é o **default** no artefato entregue; efêmero é override
  explícito (`compose.ephemeral.yml` com volumes anônimos) — prevenção de erro
  (H-2).
- Remover/comentar um bind não é erro (D-04): o diretório passa a viver só
  dentro da camada de escrita do container e é descartado no `down`.

**Rastreabilidade:** RF-06; D-04; ADR-04; US-04; UX R-3/R-4/H-2.

---

## 5. Modelo de ciclo de vida do estado

O estado não é homogêneo: cada artefato tem uma política própria. A arquitetura
classifica cada um em **PRESERVAR**, **RECONSTRUIR**, **REUSAR** ou **ACUMULAR**.
Esta tabela é o contrato que o `startup()` já cumpre e que a engenharia deve
manter.

| Artefato | Caminho | Política | Justificativa |
|----------|---------|----------|---------------|
| Snapshot de boards | `.pipe/boards/<id>/snapshot.json` | **PRESERVAR** | Baseline do `board_full_sync`; evita re-sync completo. |
| Índice de sessões | `.pipe/sessions.json` | **PRESERVAR** | Continuidade de raciocínio do agente entre execuções. |
| Throttle | `.pipe/throttle` | **PRESERVAR** (valor) | Evita re-escalar do zero após reinício; retoma o patamar de espera conhecido. |
| Fila de mudanças | `.pipe/changeQueue.json` | **RECONSTRUIR** | Sempre apagada no startup; repovoada pelo `board_full_sync` a partir do snapshot. |
| Clones git | `repo/<id>` | **REUSAR** | Reaproveitado se presente; só clona faltantes e remove extras. |
| Logs | `logs/` | **ACUMULAR** | Histórico; limpeza por `log.ttl` (dias). |

Notas de arquitetura:

- **Fila é intencionalmente volátil.** Ela representa *intenções* de sync de um
  ciclo anterior que pode ter sido interrompido em estado inconsistente. A fonte
  de verdade para reconstruí-la é o snapshot + o estado real do board. Apagá-la
  é higienização, não perda (comunicar como rotina — UX H-3/R-2).
- **Throttle persiste o valor, não o penalty.** `_throttle_file` guarda apenas
  o inteiro de espera; o estado de *penalty* (`_in_penalty`, `_penalty_ttl`) é
  em memória e **reinicia** a cada subida. Consequência aceitável: um reinício
  zera um penalty ativo, mas o valor de throttle restaurado ainda protege
  contra rajada logo após o arranque. Não exige mudança.
- **`repo/` não sofre `git pull` automático** no arranque (fora de escopo,
  US-04): a atualização do código clonado é responsabilidade do agente via
  gitevents.

---

## 6. ADR-05 — Modo de persistência observável a partir do sistema de arquivos

**Contexto:**
A UX identificou o risco central da feature (H-1, Jornada D): hoje o operador
só *infere* se o estado foi preservado pela **ausência** das mensagens
"Clonando…". Isso permite "rodar efêmero por engano", perdendo silenciosamente
a continuidade dos agentes. A recomendação R-1/R-2 pede um resumo de modo no
arranque. É preciso decidir **como** derivar esse modo sem violar a ADR-04
(código não distingue os modos) e sem introduzir complexidade.

**Decisão:**
O "modo" (**persistente com estado herdado** / **persistente primeira vez** /
**efêmero**) é **derivado por observação do sistema de arquivos no arranque**,
não por flag de configuração nem por variável de ambiente nova.

- No **início** de `startup()`, **antes de qualquer mutação** (antes de apagar
  a fila e antes de clonar/remover repos), uma função pura de pré-scan amostra
  sinais de estado herdado, usando apenas a stdlib (`pathlib`):
  - existe `.pipe/boards/<id>/snapshot.json` para algum board?
  - existe `.pipe/sessions.json`?
  - quantos clones já existem em `repo/`?
- Desses sinais deriva-se o rótulo de modo e o `startup()` emite o resumo
  (copy e cenários definidos em `ux/prototipos/startup-feedback.md`, nível INFO):
  - herdou algo → *"Modo persistente: estado anterior encontrado …"*
  - diretórios vazios → *"Modo persistente: nenhum estado anterior — primeira execução"*
  - nada persistido e nada reaproveitável entre subidas → o operador vê o rótulo
    efêmero no reinício seguinte (o pré-scan da 2ª subida encontra tudo zerado).
- A copy de limpeza da fila muda para sinalizar rotina segura (R-2/H-3).

**Consequências:**
- _Positivo:_ zero dependências novas, zero flags — a informação já está no FS.
- _Positivo:_ coerente com ADR-04: o código continua sem *decidir* o modo;
  apenas **relata** o que observou.
- _Positivo:_ transforma a falha silenciosa (Jornada D) em sinal perceptível no
  primeiro reinício (o operador que esperava "persistente" vê "primeira
  execução/efêmero").
- _Restrição de implementação:_ a amostragem **tem de ocorrer antes** de a fila
  ser apagada e dos clones acontecerem, senão o pré-scan mede o estado que ele
  mesmo produziu (falso "primeira vez"). Ordem obrigatória no `startup()`:
  1) pré-scan → 2) relato de modo → 3) higienização da fila → 4) clone/limpeza
  de repos.
- _Limite honesto:_ não há como o container saber que o operador *pretendia*
  persistir mas errou o bind (Cenário 4 da UX). O design só garante que o modo
  real seja **visível**; a intenção não é rastreável sem uma flag — e adicionar
  flag violaria ADR-04. Aceitamos esse limite.

**Alternativas consideradas:**
- _Flag de config `persist: true|false`:_ violaria ADR-04 (código passaria a
  distinguir modos) e permitiria divergência entre a flag e os binds reais
  (a flag diria "persistente" com bind quebrado). Rejeitada.
- _Arquivo-sentinela gravado na 1ª subida:_ estado novo para manter, sem ganho
  sobre observar os artefatos que já existem. Rejeitada (complexidade à toa).
- _Variável de ambiente `PIPE_MODE`:_ mesma divergência potencial da flag, e
  exige o operador declarar algo que o FS já responde. Rejeitada.

**Rastreabilidade:** UX H-1/H-3, R-1/R-2, `startup-feedback.md`; ADR-04;
RF-06; D-04.

---

## 7. ADR-06 — Invariante de instância única sobre os volumes de estado

**Contexto:**
O snapshot e a fila são arquivos JSON reescritos sem lock nem controle de
concorrência (leitura-modificação-escrita simples). Multi-instância está fora de
escopo da US-04, mas o contrato de volumes precisa deixar a suposição explícita
para não ser violada por engano (ex.: escalar `replicas: 2` no compose apontando
para os mesmos binds).

**Decisão:**
Assume-se **instância única** por conjunto de volumes de estado. Um único
processo da esteira pode montar um dado `${PIPE_STATE_DIR}`/`${PIPE_REPO_DIR}`
por vez.

**Consequências:**
- _Positivo:_ mantém o código simples — nenhum mecanismo de lock, lease ou
  coordenação é necessário (evita a "modinha" de orquestração distribuída para
  um problema que não existe aqui).
- _Negativo:_ dois containers sobre os mesmos binds podem corromper
  `snapshot.json`/`changeQueue.json` por escrita concorrente. É um modo de falha
  **de operação**, não suportado.
- _Ação para a engenharia/docs:_ o `docker-compose` final não deve sugerir
  `replicas > 1`; a doc de operação (US-05) deve registrar a invariante.
- _Extensão futura (fora de escopo):_ se multi-instância for exigido, será uma
  decisão de arquitetura própria (lock de arquivo, ou store transacional) — não
  antecipar agora.

**Rastreabilidade:** US-04 (fora de escopo: multi-instância); RF-06.

---

## 8. Propriedades e invariantes (checklist para engenharia)

A implementação (Dockerfile/compose + ajustes de `startup()`) deve preservar:

1. **cwd = `/app`** e volumes por subdiretório (`/app/.pipe`, `/app/repo`,
   `/app/logs`), nunca `/app` inteiro (D-05).
2. **Idempotência do `startup()`** perante estado pré-existente: presença de
   snapshot/sessions/clones nunca causa erro; ausência também não (D-04).
3. **Ordem do `startup()`**: pré-scan de modo → relato → apagar fila → clonar/
   limpar repos (ADR-05).
4. **Fila sempre apagada; snapshot/sessões/throttle nunca apagados** no startup
   (Seção 5).
5. **Sem novas dependências, sem nova flag/env de modo** (ADR-05).
6. **Instância única** por conjunto de volumes; compose não escala replicas
   (ADR-06).
7. **Config/segredos `:ro`** e separados do estado rw (D-05, contexto US-02/03).

---

## 9. Modos de falha e resiliência

| Falha | Comportamento | Mitigação arquitetural |
|-------|---------------|------------------------|
| Bind ausente/quebrado (operador errou o caminho) | Diretório vive só na camada do container; estado some no `down` | Rótulo de modo no arranque expõe (ADR-05); default persistente reduz incidência (H-2) |
| `snapshot.json` corrompido/parcial | Risco de re-sync ou erro de parse no full sync | Fora do escopo desta story reforçar; registrar como risco. Reconstrução via board é sempre possível apagando o snapshot |
| `changeQueue.json` inconsistente do ciclo anterior | Eliminado por design no startup | Política RECONSTRUIR (Seção 5) |
| Penalty ativo perdido no reinício | Throttle escala de novo se o limite persistir | Valor de throttle restaurado amortece a rajada (Seção 5) |
| Dois containers nos mesmos volumes | Corrupção por escrita concorrente | Não suportado — invariante ADR-06 |

---

## 10. O que esta arquitetura NÃO adiciona (anti-over-engineering)

Decisões conscientes de **não** fazer, para manter o simples que funciona:

- ❌ Banco de dados / Redis / store externo para o estado → o FS + volumes já
  resolvem.
- ❌ Named volumes → bind mounts foram escolhidos (ADR-04/UX) porque o operador
  quer **auditar** o estado no host.
- ❌ Lock/lease/coordenação distribuída → instância única (ADR-06).
- ❌ Flag/env de modo de persistência → modo é observável (ADR-05).
- ❌ `git pull` automático de `repo/` no arranque → responsabilidade do agente
  (fora de escopo US-04).
- ❌ Backup/rotação de volumes → fora de escopo (US-04); pode virar story
  própria.

---

## 11. Rastreabilidade consolidada

| Item | Origem | Onde nesta arquitetura |
|------|--------|------------------------|
| RF-06 | requisitos-decisoes.md | Seções 4, 5, 8 |
| D-04 | requisitos-decisoes.md | Seções 4, 8, 9 |
| ADR-04 | requisitos-decisoes.md | Seções 1, 4; premissa das ADR-05/06 |
| H-1, H-3 | ux/us-04 | ADR-05 |
| R-1, R-2 | ux/us-04 | ADR-05 |
| R-3, R-4, H-2 | ux/us-04 | D-05, Seção 4 |
| H-5 | ux/us-04 | vocabulário "persistente/efêmero" em todo o doc |
| Fora de escopo (multi-instância) | US-04 | ADR-06 |
| Fora de escopo (backup, git pull) | US-04 | Seção 10 |

---

## 12. Handoff para engenharia

Escopo derivado desta arquitetura (sugestão de quebra, sem criar issues aqui):

1. **Compose + WORKDIR** (D-05): `Dockerfile` com `WORKDIR /app`; compose com os
   três binds por subdiretório parametrizados por `.env`; override efêmero.
   Materializa os protótipos de UX como artefato final.
2. **Relato de modo no `startup()`** (ADR-05): pré-scan puro (stdlib) + emissão
   das mensagens de modo na ordem correta + nova copy da higienização da fila.
3. **Nota de invariante** (ADR-06) na doc de operação (US-05) e ausência de
   `replicas` no compose.

Os itens 1 e 2 são independentes entre si (podem ir em paralelo); ambos
dependem do compose base da US-03.
