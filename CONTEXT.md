# Contexto e Decisões — Esteira Agêntica v2

Data: 2026-07-02

## Versionamento

A versão do projeto é definida em `src/core/version.py` (variável `VERSION`).
Segue semântico: `MAJOR.MINOR.PATCH`.

**Regra: toda alteração no código deve incrementar a versão antes do commit.**

- PATCH: correções de bugs, ajustes menores
- MINOR: funcionalidades novas, melhorias compatíveis
- MAJOR: mudanças incompatíveis (breaking changes)

A versão é exibida no log ao iniciar a esteira.

## Changelog

### Preflight de Credenciais (v1.6.0 — US-02)

Adição de comportamento novo: verificação de credenciais antes do startup
principal (preflight). Implementado nas tasks #34 (kiro_cli_agent) e #35
(startup), consolidado nesta task #36 com o bump MINOR correspondente.

- Bump: `1.5.0` → `1.6.0` (MINOR — adição de comportamento, sem breaking change)
- Funcionalidade: `preflight()` verifica SSH, GitHub CLI e permissões do repo
  antes de qualquer operação destrutiva
- Referências: ADR-04, `doc/arch/rodar-no-docker/us-02-autenticacao-headless.md`

## Visão Geral

Esteira automatizada de agentes de IA com arquitetura hexagonal. Reescrita do projeto `oldversion/` para suportar múltiplas plataformas de board (GitHub Projects, ClickUp, etc) e múltiplos adapters de agente (kiro-cli, etc).

## Arquitetura Hexagonal

```
src/
├── core/               # Domínio - regras de negócio
│   ├── log.py          # Logging dual (terminal resumo + arquivo detalhe)
│   ├── config.py       # Validação do pipe.yml + contexts
│   ├── agent.py        # AgentPort + AgentParams + build_prompt
│   ├── board.py        # Board core + BoardPort + ChangeItem + SyncEvent
│   ├── commands.py     # Comandos @--- no body (IssueCommands, parse/serialize)
│   ├── change_queue.py # Fila persistente de sincronismo (at-least-once)
│   ├── snapshot.py     # Snapshot por board
│   ├── session.py      # Índice de sessões do agente (.pipe/sessions.json)
│   └── sync.py         # Sincronização local ↔ board (detect + apply)
├── adapters/           # Implementações de ports
│   ├── github_board.py # Adapter para GitHub Projects V2
│   └── kiro_cli_agent.py # Adapter para execução via kiro-cli
└── __main__.py         # Orquestração
```

### Ports e Adapters

- **BoardPort** — interface abstrata para operações de board
- **Board** — core que usa o port para operações
- **AgentPort** — interface abstrata para execução de agentes
- **KiroCliAgent** — adapter que executa via kiro-cli

## Fluxo Principal

```
main()
├── check_config()         # Valida pipe.yml, SSH, contexts
├── startup()              # Configura SSH, clona repos, limpa fila anterior
├── board_full_sync()      # Sync completo
│   ├── Cria .pipe/boards/<board_id>/<col_id>/
│   ├── Sincroniza snapshot local (mapa de colunas)
│   ├── sync_boards() remoto (com retry de penalty)
│   ├── Recupera issues com status pendente (crash recovery)
│   └── detect_board_changes() por board
│
└── while running:
    ├── board_full_sync()    # Re-executa se mudou o dia (daily full sync)
    ├── sync_board() → bool  # True se houve movimentação (up ou down)
    ├── keep_task() → task | None
    ├── call_agent()         # Resolve adapter, build_prompt, executa
    └── sleep_time()         # Dorme se !had_changes AND task==None
```

### sleep_time

Controle de ociosidade condicional:
- Se `sync_board()` retornou `False` (fila vazia, nenhuma movimentação) **E** `keep_task()` retornou `None` (nenhuma tarefa elegível) → dorme `config["sleep"]` segundos.
- Se houve qualquer atividade → prossegue imediatamente.

O campo `sleep` é obrigatório no `pipe.yml` (número > 0, em segundos).

## Sincronização

### Eventos (SyncEvent)

| Evento | Direção | Significado |
|--------|---------|-------------|
| `create-up` | local → board | Issue criada localmente |
| `create-down` | board → local | Issue criada no board |
| `change-up` | local → board | Issue modificada localmente |
| `change-down` | board → local | Issue modificada no board |
| `delete-up` | local → board | Issue deletada localmente |
| `delete-down` | board → local | Issue deletada no board |

### Regra de conflito

Quando há `change-up` e `change-down` simultâneos, o **board (remoto) vence**. O `detect_local_changes` não enfileira `change-up` se a issue já está com status `change-down`.

### Detecção de mudanças remotas

Gatilhos para `change-down`:
- `updated_at` no board > `updated_at` no snapshot
- Coluna no board ≠ coluna no snapshot

### Fila de mudanças (ChangeQueue)

- Modelo at-least-once: `getNext()` espia sem remover, `remove(uuid)` confirma
- Persistida em `.pipe/changeQueue.json`
- Deduplicação por `event + id + identifier + board`
- Limpa no startup (issues com status pendente são re-enfileiradas do snapshot)

#### Flag `fullsync`

Cada `ChangeItem` tem um booleano `fullsync` (default `False`):
- `fullsync=True` → reconcilia **todas** as propriedades + dependências
  (blocked_by/blocks, que só existem via REST). Usado em todo create e no
  full sync diário.
- `fullsync=False` → apenas a chamada única de propriedades (sem deps). Usado
  em `change-down` incremental.
- **Upgrade (superset)**: se um item equivalente já está na fila sem fullsync
  e um novo full chega, o existente é promovido a `fullsync=True` (não
  duplica). `same_target` ignora `fullsync` na deduplicação.

## Otimização de Sincronização (v1.3.0)

Objetivo: minimizar chamadas ao GitHub por issue. Duas estratégias combinadas.

### Down — chamada única enriquecida

`get_issue(board_id, issue_id, fullsync=False)` traz, numa **única query
GraphQL**: title, body, state, updatedAt, labels, parent, children (subIssues),
coluna (Status) e isArchived (via `projectItems`). As dependências
(blocked_by/blocks) **não existem no GraphQL** (só REST) e só são buscadas
quando `fullsync=True` (2 chamadas REST via `_get_dependencies`).

Em cada evento down, o estado real do board é gravado no snapshot
(`_write_state_from_issue`). Sem fullsync, `blocked_by`/`blocks` são
**preservados** do snapshot (não vêm na chamada única) para não apagar o bloco
`@---` de deps ao reescrever o `-body.md`. A coluna também vem do `get_issue`,
eliminando o `list_issues` (paginação completa) que era feito antes.

### Up — comparar antes de escrever

`Board.apply_commands(board_id, issue_id, cmds, known=None)` compara o estado
desejado (comandos do arquivo) contra o estado conhecido (`known`, do
snapshot) e **só chama o setter do atributo que realmente mudou**. Os setters
(`set_parent/children/blocked_by/blocks`) recebem `known_current`, evitando os
GETs internos de leitura-antes-de-escrita. Retorna deltas
`{rel: {added, removed}}` das relações para o gatilho recíproco.

Sem `known` (reconciliação completa), comporta-se como antes (chama todos os
setters, que descobrem o estado atual sozinhos).

### Gatilho de par recíproco (dependências)

Relações são bidirecionais no GitHub:

| Relação em X | Par recíproco em Y |
|--------------|--------------------|
| `X.parent = Y` | `Y.children ∋ X` |
| `X.children ∋ Y` | `Y.parent = X` |
| `X.blocked_by ∋ Y` | `Y.blocks ∋ X` |
| `X.blocks ∋ Y` | `Y.blocked_by ∋ X` |

Ao detectar relação **adicionada/removida** em X (up ou down),
`_trigger_reciprocal_downs` enfileira um `change-down fullsync` do alvo Y
**apenas se o snapshot de Y estiver inconsistente** com o par recíproco:
- adicionada: enfileira se Y **ainda não** reciproca X;
- removida: enfileira se Y **ainda** reciproca X.

Essa checagem de par (`_reciprocates`) é a **condição de parada**: quando o
alvo já está coerente, nada é enfileirado — evitando reação em cadeia infinita.
O estado desejado/real é sempre gravado no snapshot **antes** de disparar o
gatilho. Alvos não rastreados no snapshot são ignorados.

### Throttle

Toda requisição respeita o throttle. `_get_rate_limit_info` chama
`self._throttle()` diretamente (não pode rotear por `_gh`, pois é invocado de
dentro de `_handle_rate_limit`, que já roda dentro de `_gh`/`_gql` — causaria
recursão). As demais chamadas `subprocess.run` ficam dentro de `_gh`/`_gql`,
sempre após `_throttle()`.

### Detecção de rate limit por transporte (não pelo corpo)

`_handle_rate_limit` decide **exclusivamente** por sinais de transporte:

- `headers["__status__"]` (linha de status HTTP parseada em `_parse_headers`)
  igual a `403`/`429`;
- `stderr` do `gh` mencionando "rate limit";
- `_graphql_rate_limited(output)`, que parseia o JSON e olha apenas
  `data.errors[].type` (`RATE_LIMITED`/`FORBIDDEN`) — a seção estruturada de
  erros da API.

O corpo (`output`/stdout) **nunca** é escaneado por substring. Regressão
corrigida: a versão anterior fazia `combined = f"{output} {error}"` e buscava
"rate limit" no corpo. Uma issue cujo título/body continha "Rate Limit" (ex.:
issue de análise de custo de API) fazia toda `list_issues` (HTTP 200,
`remaining` ~5000) ser classificada como *secondary rate limit*, escalando
throttle até 64s e ativando penalty por horas sem nenhum limite real.
Cobertura em `tests/test_rate_limit_detection.py`.

## Seleção de Tarefas (keep_task)

- Boards ordenados por prioridade (menor = mais prioritário)
- Issues ordenadas por `created_at` / `updated_at` (mais antiga primeiro)
- Auto-advance: coluna `todo` → próxima coluna (apenas move arquivos, sync propaga)
- `parallel: false` → bloqueia auto-advance se issue ativa fora de terminais
- Elegível: `status == "ok"` + coluna com `agent` + coluna com `change.advance`
- Bloqueada: `/need_human` ou `/blocked_by` no body

## Execução de Agentes

### gitevents

| Valor | Blocos no prompt |
|-------|------------------|
| `create` | Git Setup (criar branch) + Commit & Push + Cleanup |
| `use` | Git Setup (checkout existente) + Commit & Push + Cleanup |
| `merge` | Git Setup (checkout existente) + Commit & Push + PR + Cleanup |
| `create-merge` | Git Setup (criar) + Commit & Push + PR + Cleanup |
| `no-branch` | Nenhum bloco de git |

### Substituição de agente por nível (`override-agent`)

A coluna tem um `agent` default. O nível de execução de uma issue é armazenado
como label `agent-level-<nível>` no GitHub (ex.: `agent-level-low`,
`agent-level-medium`, `agent-level-high`). Essa label é sincronizada
nativamente pelo board, eliminando a dependência de estado local.

Se a issue possuir uma label `agent-level-<nível>` e `<nível>` for chave de
`override-agent`, usa o agente do valor; senão, o `agent` default. Como cada
agente carrega o próprio `model`, a troca de agente também troca o model.

Resolvido em `agent.py` (`agent_level` lê `issue["labels"]` diretamente +
`resolve_agent_id`), validado em `config.py`.

No fluxo do planning-poker, o agente escreve `/agent_level <nível>` no bloco
`@---` do body. O sync-up chama `all_labels()` (em `commands.py`), que emite
`agent-level-<nível>` no conjunto de labels efetivas, gravando a label no board
via `apply_commands`. A label `agent-level-*` é tratada como campo especial
(análogo a `need_human`): extraída em `from_issue`, reemitida em `all_labels`,
nunca sobrescrita pelo comando `/labels` do usuário.

Migração de issues legadas: o `board_full_sync` chama
`migrate_agent_level_labels` (em `sync.py`) que, para cada issue com
`/agent_level` no body mas sem label `agent-level-*` no snapshot, enfileira um
`change-up` para que o sync-up grave a label no board.

### Contexto do agente

Cada agente tem um arquivo em `contexts/<plataforma>/<agente>.md` que é enviado
como contexto na execução. Validado no `check_config` (deve existir e não
estar vazio).

O contexto é entregue **concatenado no início do input** do `kiro-cli chat`
(via `_compose_input`: `contexto + "---" + prompt`), não via `--agent`. A
execução usa o `~/.kiro` padrão do kiro-cli — não há `KIRO_HOME` isolado nem
geração de configs de agente nativos.

### Sessão do agente (continuidade entre execuções)

Módulo `src/core/session.py` (`SessionIndex`), índice em `.pipe/sessions.json`.

Objetivo: preservar o raciocínio do agente entre execuções da mesma issue —
quando um agente pausa (ex.: `need_human`/`blocked_by`) e retoma depois, ele
continua de onde parou em vez de recomeçar do zero.

- **Chave por agente**: `<board>/<issue>/<agente>`. O mesmo agente atuando em
  colunas diferentes retoma o próprio raciocínio; agentes distintos nunca
  herdam a sessão um do outro. O agente da chave é o **resolvido**
  (`resolve_agent_id`, considera override por `/agent_level`).
- **Retomar**: antes de executar, se há `session_id` conhecido e ele **ainda
  existe** no kiro-cli (`--list-sessions` do cwd), passa `--resume-id <id>`.
- **Capturar**: após executar, pega o id da sessão mais recente do cwd
  (topo de `--list-sessions`) e grava no índice. Cobre a primeira execução e o
  caso de sessão descartada pelo kiro (que vira sessão nova). O loop é
  sequencial, então a sessão do topo é seguramente a desta execução.
- **Ciclo de vida**: a esteira **não** gerencia as sessões do kiro-cli (não
  apaga, não limpa) — apenas aponta enquanto existirem. Se o `--resume-id`
  referencia uma sessão inexistente, o kiro cria uma nova silenciosamente (sem
  erro) e o índice é atualizado.

Detalhes técnicos verificados no kiro-cli:
- Sessões ficam em `~/.kiro/sessions/cli/{uuid}.json/.jsonl`; o índice é um
  SQLite global (`~/.local/share/kiro-cli/`), **keyed por cwd**. Como cada repo
  tem seu cwd (`repo/<repo_id>`), `--list-sessions` só enxerga as sessões
  daquele repo — pipes diferentes não colidem.
- O `session_id` **não** aparece no stdout headless; só é obtido via
  `--list-sessions`.
- `.pipe/sessions.json` sobrevive a reinícios (o `startup` só limpa a fila de
  mudanças, não o índice de sessões).

### Log de execução

Gerado em `<log.dir>/<issue_id>/<timestamp>.md` com 3 seções:
- **Parâmetros**: plataforma, agente, model, agent_level, board, coluna, issue, context
- **Prompt**: prompt completo montado por `build_prompt`
- **Chat**: diálogo (preenchido durante execução)

Em caso de erro, o log registra o erro na seção Chat antes de propagar a exceção.

## Configuração (pipe.yml)

```yaml
sleep: 60

log:
  dir: logs
  ttl: 10
  level: INFO

git:
  repo:
    <id>: <url-ssh>
  flow:
    base: main
    <id-flow>:
      prefix: <prefix>/
      create: <branch-origem>
      merge: <branch-destino>

agents:
  <id-platform>:
    <id-agent>:
      name: <nome>
      model: <modelo>

boards:
  platform: github
  <id-board>:
    name: <nome>
    todo: <coluna-inicial>
    priority: <n>
    flow: <id-flow>
    parallel: true|false
    columns:
      <id-column>:
        name: <nome>
        agent: <id-agent>
        override-agent: {<nível>: <id-agent>}
        gitevents: create|use|merge|create-merge|no-branch
        prompt: <objetivo da etapa>
        archive: true|false
        on_in: [<token>, ...]
        on_out: [<token>, ...]
        change:
          advance: <id-column>
          <condition>: <id-column>
```

## Arquivos por Issue

| Arquivo | Função |
|---------|--------|
| `<id>-<slug>-body.md` | `# Título\n\n<body>` — leitura e escrita |
| `<id>-<slug>-history.md` | Histórico de comentários — somente leitura |
| `<id>-<slug>-addcomment.md` | Escrever aqui → vira comentário na issue |

### Formato do history

```markdown
## <autor> - <yyyy-MM-dd HH:mm:ss>

<texto do comentário>
---
```

## Comandos no body (`@---`)

Módulo `src/core/commands.py`. O body de uma issue pode terminar com um bloco
de comandos separado por uma linha `@---`.

- `IssueCommands`: dataclass com parent, children[], blocked_by[], blocks[],
  labels[], agent_level, close, archive, need_human.
- `split_body(raw)` → `(body_limpo, IssueCommands)`. Múltiplos `@---`: o último
  vence, anteriores removidos.
- `compose_body(body, cmds)` → body completo com bloco.
- `from_issue(issue)` → IssueCommands (extrai `need_human` e `agent_level` das labels; ambos tratados como campos especiais — não aparecem em `cmds.labels`).
- `annotations_doc()` → documentação compartilhada por prompts e contexts.

Filosofia presença/ausência: o estado escrito é o estado final (SET). Sem
comandos de "remover".

### Fluxo

- **Down** (`_compose_down_body` em sync.py): escreve `# título\n\n{body_limpo}`
  + bloco `@---` reconstruído do estado real da issue (relações via `get_issue`,
  labels, need_human). Limpa qualquer `@---` pré-existente no body remoto.
- **Up** (`_apply_create_up` / `_apply_change_up`): `split_body` separa o body
  limpo (enviado ao board) dos comandos, que são aplicados via
  `Board.apply_commands` (set_labels com all_labels, set_parent, set_children,
  set_blocked_by, set_blocks, archive/unarchive, close).

### Adapter GitHub

- Sub-issues (parent/children): REST `/issues/{n}/sub_issues` (usa
  `fullDatabaseId` no corpo, number no path), `replace_parent=true`.
- Dependências (blocked_by/blocks): REST `/issues/{n}/dependencies/blocked_by`
  e `/blocking`. `set_blocks` escreve no lado blocked_by de cada alvo.
- Labels: PUT `/issues/{n}/labels` (SET); add/remove unitário via POST/DELETE.
- Arquivamento: GraphQL `archiveProjectV2Item` / `unarchiveProjectV2Item`.
- `need_human` é label comum no GitHub, tratada em campo próprio no domínio.

## Eventos de coluna (`on_in` / `on_out`)

Cada coluna pode declarar `on_in` e `on_out` (listas). Em uma mudança de
coluna, dispara o `on_out` da origem e o `on_in` do destino.

Tokens: `close`, `open` (reopen + unarchive), `archive`, `-archive`,
`need_human`, `-need_human`, `<label>` (add), `-<label>` (remove).

Validação em `config.py`: `on_in`/`on_out` devem ser listas se presentes.

### Movimentação local (change-up)

`_apply_change_up` → `_fire_column_events` aplica os eventos diretamente no
board via `Board.apply_column_events`.

### Movimentação manual no board (change-down)

Quando o usuário move a issue manualmente no GitHub, o `_apply_change_down`
detecta a mudança de coluna e, **após salvar o snapshot** (com o `body_mtime`
já registrado), chama `_bake_column_events`: reescreve o arquivo `-body.md`
aplicando `on_out`/`on_in` no bloco `@---` (via `apply_events_to_commands`).

O snapshot **não é alterado** nesse momento. Como a reescrita deixa o arquivo
mais novo que o `body_mtime` salvo, o próximo `sync` detecta modificação local
e dispara um `change-up`, que sobe os status/labels resultantes para o board.
Isso garante que tags e status fiquem sempre sincronizados, mesmo em
movimentações manuais.

## Snapshot por Board

`.pipe/boards/<board_id>/snapshot.json`:
```json
{
  "board": {"<col_id>": "<col_name>"},
  "issues": [
    {
      "id": "1", "column": "...", "body_path": "...", "body_mtime": "...",
      "updated_at": "...", "status": "ok",
      "labels": [], "parent": null, "children": [],
      "blocked_by": [], "blocks": [], "archived": false, "state": "open"
    }
  ],
  "last_sync": null,
  "last_board_update": "..."
}
```

Os campos de estado (`labels`, `parent`, `children`, `blocked_by`, `blocks`,
`archived`, `state`) guardam o **estado conhecido** da issue, usado para o diff
no fluxo up e para a checagem de par recíproco. São gravados em todo evento
up (estado desejado) e down (estado real do board). `status` é o campo de
sincronismo (crash recovery), distinto de `state` (open/closed da issue).

## Pendências

- [ ] Implementar adapter ClickUp
