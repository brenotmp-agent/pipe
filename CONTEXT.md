# Contexto e Decisões — Esteira Agêntica v2

Data: 2026-06-28

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

### Override de model/effort

Precedência: agente (default) < coluna (`effort`) < tag `/effort` no body (se `allow-overwrite: true`)

### Contexto do agente

Cada agente tem um arquivo em `contexts/<plataforma>/<agente>.md` que é enviado como contexto na execução. Validado no `check_config` (deve existir e não estar vazio).

### Log de execução

Gerado em `<log.dir>/<issue_id>/<timestamp>.md` com 3 seções:
- **Parâmetros**: plataforma, agente, model, effort, board, coluna, issue, context
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
        effort: low|medium|high
        gitevents: create|use|merge|create-merge|no-branch
        target-prompt: <objetivo da etapa>
        allow-overwrite: true|false
        archive: true|false
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
  labels[], effort, close, archive, need_human.
- `split_body(raw)` → `(body_limpo, IssueCommands)`. Múltiplos `@---`: o último
  vence, anteriores removidos.
- `compose_body(body, cmds)` → body completo com bloco.
- `from_issue(issue)` → IssueCommands (extrai need_human das labels).
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
    {"id": "1", "column": "...", "body_path": "...", "body_mtime": "...", "updated_at": "...", "status": "ok"}
  ],
  "last_sync": null,
  "last_board_update": "..."
}
```

## Pendências

- [ ] Implementar adapter ClickUp
