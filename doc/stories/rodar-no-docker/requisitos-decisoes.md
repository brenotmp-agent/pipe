# Requisitos e Decisões — Rodar no Docker

Status: draft
Owner: product
Last updated: 2026-07-07

## Inputs
- doc/product/rodar-no-docker/epicos.md
- doc/product/rodar-no-docker/vision.md
- doc/stories/rodar-no-docker/user-stories.md
- README.md (.gitignore: .pipe/, logs/, contexts/, repo/ são excluídos do versionamento)
- src/__main__.py (startup, REPO_DIR)
- src/core/change_queue.py (QUEUE_FILE)
- src/core/session.py (SessionIndex)

---

## Requisitos Funcionais

### RF-06 — Preservação de estado entre reinícios

A esteira deve suportar operação com estado persistido entre reinícios do
container. Quando os diretórios de runtime (`.pipe/`, `logs/`, `repo/`) são
montados como volumes externos:

- O snapshot de boards (`.pipe/boards/<id>/snapshot.json`) é preservado e
  usado como baseline no arranque, evitando re-sync completo.
- O índice de sessões (`.pipe/sessions.json`) é preservado, permitindo que o
  agente retome o raciocínio de execuções anteriores.
- Os clones de repositório (`repo/<id>`) são reutilizados sem re-clone.
- Os logs (`logs/`) são acumulados entre reinícios.

**Rastreabilidade:** US-04.

---

## Decisões de Design

### D-04 — Modo efêmero sem volumes deve funcionar sem erro

A ausência de volumes (bind mounts não configurados) não é uma condição de
erro. A esteira deve subir normalmente em modo efêmero:

- Estado zerado a cada `docker compose up`.
- Re-sync completo do board no arranque.
- Re-clone de todos os repositórios configurados.
- Sessões de agente iniciam do zero.

Casos de uso: ambientes de CI, testes isolados, demonstrações.

**Rastreabilidade:** US-04; ADR-04.

---

## Registros de Decisão de Arquitetura (ADR)

### ADR-04 — Persistência de estado como opt-in via volumes

**Contexto:**
A esteira acumula estado de runtime em `.pipe/`, `logs/` e `repo/`. Ao
containerizar, é necessário decidir se esse estado deve ser persistido por
padrão ou sob demanda.

**Decisão:**
A persistência é **opt-in**: o compose declara bind mounts para os três
diretórios, mas o operador escolhe se os configura ou não. A imagem e o código
não distinguem entre operação com ou sem volumes.

**Consequências:**
- _Positivo:_ flexibilidade — o mesmo compose pode ser usado em modo persistente
  (produção, uso contínuo) ou efêmero (CI, testes).
- _Positivo:_ simplicidade de código — o `startup()` já lida corretamente com
  estado pré-existente ou ausente sem ramificação extra.
- _Positivo:_ nenhum segredo de estado fica embutido na imagem.
- _Negativo:_ operador precisa configurar bind mounts conscientemente para
  persistir estado; ausência inadvertida resulta em perda de estado a cada
  reinício.

**Alternativas consideradas:**
- _Sempre efêmero:_ simples, mas impede continuidade de raciocínio do agente e
  exige re-clone e re-sync completo a cada reinício — custo desnecessário em
  uso contínuo.
- _Sempre persistente (volume nomeado obrigatório):_ reduz a flexibilidade;
  dificulta uso em CI sem limpeza explícita entre execuções.

**Rastreabilidade:** RF-06; D-04; US-04.
