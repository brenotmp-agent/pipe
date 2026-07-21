# Esteira Agêntica

Esteira automatizada de agentes de IA com arquitetura hexagonal.

## Requisitos

- Python 3.12+
- Git
- GitHub CLI (`gh`) autenticado
- Chave SSH configurada no GitHub

## Instalação

```bash
pip install pyyaml
```

## Configuração

### 1. Variável de ambiente SSH

```bash
export PIPE_SSH_KEY_FILE=~/.ssh/id_ed25519
```

### 2. Arquivo pipe.yml

```yaml
sleep: 60

log:
  dir: logs
  ttl: 10
  level: INFO

git:
  repo:
    main: git@github.com:user/repo.git
  flow:
    base: main
    feature:
      prefix: feature/
      create: main
      merge: main

agents:
  kiro-cli:
    dev:
      name: engineering
      model: claude-sonnet-4-20250514

boards:
  platform: github
  backlog:
    name: Backlog
    priority: 0
    flow: feature
    columns:
      todo:
        name: To Do
      doing:
        name: Doing
        agent: dev
        gitevents: create
        target-prompt: Execute a tarefa
        change:
          advance: done
      done:
        name: Done
        archive: true
```

### 3. Contextos de agentes

Cada agente precisa de um arquivo de contexto em `contexts/<plataforma>/<agente>.md`.
Ao executar, o sistema cria arquivos vazios automaticamente e exige preenchimento.

## Uso

### Execução local (Python)

```bash
python -m src
```

### Execução via Docker Compose (recomendado para produção)

**Pré-requisitos:**
- Docker e Docker Compose instalados
- `gh auth login` executado no host (gera `~/.config/gh/`)
- Chave SSH configurada no GitHub (`~/.ssh/id_ed25519`)
- Token do GitHub com escopos `repo` e `project`

**1. Preparar o contexto de build (copia o binário kiro-cli):**

```bash
./prepare-docker.sh
```

**2. Criar o arquivo `.env` com o token do GitHub:**

```bash
cp .env.example .env
# Editar .env e preencher GH_TOKEN (e opcionalmente SSH_KEY_FILE, GH_CONFIG_DIR)
```

**3. Garantir que o `pipe.yml` existe na raiz do projeto:**

```bash
# pipe.yml não é versionado — deve ser criado/copiado manualmente
# Ver seção "Configuração → Arquivo pipe.yml" abaixo para o formato
```

**4. Build e execução:**

```bash
docker compose build
docker compose up
```

**5. Para rodar em background:**

```bash
docker compose up -d
docker compose logs -f   # acompanhar logs
```

**6. Para parar:**

```bash
docker compose down
```

**Volumes persistidos entre reinícios:**

| Volume | Caminho no container | Conteúdo |
|--------|---------------------|----------|
| `pipe_state` | `/app/.pipe` | Snapshots, fila de mudanças, índice de sessões |
| `pipe_repos` | `/app/repo` | Clones dos repositórios git |
| `pipe_logs` | `/app/logs` | Logs de execução |

Os volumes são criados automaticamente pelo Docker na primeira execução.
Para limpar o estado interno (forçar re-sync completo), remova os volumes:

```bash
docker compose down -v
```

## Estrutura

```
src/
├── core/                   # Domínio
│   ├── log.py              # Logging dual (terminal + arquivo)
│   ├── config.py           # Validação do pipe.yml
│   ├── agent.py            # AgentPort + build_prompt
│   ├── board.py            # Board core + BoardPort + ChangeItem
│   ├── commands.py         # Comandos @--- no body (parse/serialize)
│   ├── change_queue.py     # Fila persistente de sincronismo
│   ├── snapshot.py         # Snapshot por board
│   ├── session.py          # Índice de sessões do agente
│   └── sync.py             # Sincronização local ↔ board
├── adapters/               # Implementações
│   ├── github_board.py     # Adapter para GitHub Projects V2
│   └── kiro_cli_agent.py   # Adapter para execução via kiro-cli
└── __main__.py             # Entrada principal (orquestração)

.pipe/boards/<id>/          # Diretórios de boards e snapshots
.pipe/sessions.json         # Índice (board/issue/agente) → session_id
contexts/<platform>/<agent>.md  # Contextos dos agentes
repo/                       # Repositórios clonados
logs/                       # Logs diários (JSON) + logs de agente (MD)
pipe.yml                    # Configuração
```

## Loop Principal

```
main()
├── check_config()         # Valida pipe.yml, SSH, contexts
├── startup()              # Configura SSH, clona repos
├── board_full_sync()      # Sync completo (estrutura + mudanças remotas)
│
└── while running:
    ├── board_full_sync()  # Re-executa se mudou o dia (daily full sync)
    ├── sync_board()       # Detecta mudanças remotas/locais, aplica fila → bool
    ├── keep_task()        # Seleciona próxima tarefa elegível → task | None
    ├── call_agent()       # Executa agente com prompt construído
    └── sleep_time()       # Intervalo entre ciclos (condicional)
```

### sleep_time (controle de ociosidade)

Ativado apenas quando **ambas** as condições são verdadeiras:
- `sync_board()` retornou `False` (nenhuma movimentação up ou down)
- `keep_task()` retornou `None` (nenhuma tarefa elegível)

Quando ativado, dorme pelo tempo definido em `sleep` no `pipe.yml` (em segundos).
Se houve qualquer atividade (sync movimentou algo OU existe tarefa para executar), o loop prossegue imediatamente sem pausa.

## Seleção de Tarefas (keep_task)

- Boards ordenados por prioridade (menor = mais prioritário)
- Issues ordenadas por data (mais antiga primeiro)
- Auto-advance de coluna `todo` para próxima coluna
- `parallel: false` → bloqueia auto-advance se já existe issue ativa
- Issues com `/need_human` ou `/blocked_by` no body são ignoradas

## Execução de Agentes

### gitevents (controle de branches)

| Valor | Comportamento |
|-------|--------------|
| `create` | Cria branch a partir da origem |
| `use` | Usa branch existente |
| `merge` | Usa branch existente + cria PR |
| `create-merge` | Cria branch + cria PR |
| `no-branch` | Sem operações de git |

### Substituição de agente por nível (`override-agent`)

Cada coluna define um agente default no atributo `agent`. Se a issue tiver uma
tag `/agent_level <nível>` no bloco `@---` e esse `<nível>` for uma chave do
mapa `override-agent` da coluna, a esteira usa o agente indicado no valor. Se
não houver `/agent_level`, ou o nível não estiver mapeado, usa o `agent`
default.

Como cada agente carrega o próprio `model`, trocar o agente por nível troca
também o model efetivo da execução.

```yaml
columns:
  desenvolvimento:
    agent: engineering          # default
    override-agent:
      low: generic              # /agent_level low  -> generic
      high: senior-engineering  # /agent_level high -> senior-engineering
```

Validação (`config.py`): `override-agent` deve ser um mapa `<nível>: <agente>`,
a coluna precisa ter um `agent` default, e todo agente referenciado deve existir
em `agents`.

### Log de execução

Cada execução gera um arquivo em `logs/<issue_id>/<timestamp>.md` com:
- **Parâmetros**: plataforma, agente, model, agent_level, board, coluna, issue
- **Prompt**: prompt completo enviado ao agente
- **Chat**: diálogo da execução (preenchido pelo adapter)

### Continuidade de sessão

A esteira mantém a continuidade do raciocínio do agente entre execuções da
mesma issue. Quando um agente pausa (ex.: `/need_human` ou `/blocked_by`) e a
tarefa retorna depois, ele retoma de onde parou em vez de recomeçar.

- Índice em `.pipe/sessions.json` mapeia `<board>/<issue>/<agente>` →
  `session_id` do kiro-cli (chave **por agente**: agentes distintos não herdam
  a sessão um do outro; o mesmo agente reusado retoma o próprio raciocínio).
- Antes de executar, se a sessão ainda existir, retoma via `--resume-id`.
- Após executar, captura o id da sessão (mais recente do cwd) e atualiza o
  índice.
- A esteira **não** gerencia o ciclo de vida das sessões do kiro-cli — apenas
  aponta enquanto existirem. Sessão inexistente vira sessão nova sem erro.

## Anotações no body (comandos `@---`)

O body de cada issue pode conter um bloco de comandos no final, separado do
conteúdo real por uma linha contendo apenas `@---`. O core lê esse bloco e
aplica as relações/atributos no board; o body enviado ao board é sempre limpo
(sem o bloco). No fluxo down, o core reescreve o bloco a partir do estado real
da issue no board.

Desambiguação: se houver mais de um `@---`, o último vence e os anteriores são
removidos.

Filosofia presença/ausência: o que estiver escrito é o estado final. Comando
presente garante a relação/atributo; ausente, remove. Não há comandos de
"remover".

| Comando | Efeito |
|---------|--------|
| `/parent #N` | esta issue é sub-issue (filha) de N |
| `/children #N, #M` | N e M são sub-issues desta |
| `/blocked_by #N, #M` | esta issue está bloqueada por N e M |
| `/blocks #N, #M` | esta issue bloqueia N e M |
| `/labels a, b, c` | define (SET) as labels da issue |
| `/agent_level low\|medium\|high` | nível de agente (chave de `override-agent`) |
| `/need_human` | marca intervenção humana (label especial) |
| `/close [completed\|not_planned]` | fecha a issue |
| `/reopen` | reabre a issue |
| `/archive` | arquiva a issue no board |

A label `need_human` é especial: é tratada em campo próprio e não aparece em
`/labels`, embora no board seja uma label comum.

Exemplo de body completo:

```markdown
# Implementar login

Validar credenciais e retornar JWT.

@---
/parent #10
/blocked_by #42, #58
/labels backend, security
/agent_level high
```

## Eventos de coluna (`on_in` / `on_out`)

Cada coluna pode declarar arrays `on_in` (disparado ao entrar) e `on_out`
(disparado ao sair). Quando uma issue muda de coluna, o core dispara o
`on_out` da coluna de origem e o `on_in` da coluna de destino.

```yaml
columns:
  concluido:
    name: Concluído
    on_in:
      - close
      - done
    on_out:
      - -done
```

Tokens suportados:

| Token | Efeito |
|-------|--------|
| `close` | fecha a issue |
| `open` | reabre (se fechada) e desarquiva (se arquivada) |
| `archive` | arquiva o item no board |
| `-archive` | desarquiva o item no board |
| `need_human` | adiciona a label `need_human` |
| `-need_human` | remove a label `need_human` |
| `<label>` | adiciona a label |
| `-<label>` | remove a label |

Os eventos disparam tanto em movimentação local quanto manual no board. Numa
movimentação manual no GitHub, o sync reescreve o `-body.md` aplicando os
eventos no bloco `@---` (sem tocar no snapshot); como o arquivo fica mais novo
que o `body_mtime` salvo, o ciclo seguinte gera um `change-up` que sobe os
status/labels resultantes — mantendo tudo sincronizado.

## Otimização de Sincronização

Para reduzir o número de requisições ao board por issue, o sync combina duas
estratégias:

- **Down (chamada única):** `get_issue` traz numa só query GraphQL título,
  body, estado, labels, parent, filhos, coluna e arquivamento. As dependências
  (`blocked_by`/`blocks`) só existem via REST e são buscadas apenas quando o
  item da fila está marcado como `fullsync`.
- **Up (comparar antes de escrever):** o estado desejado (comandos do arquivo)
  é comparado com o estado conhecido no snapshot; só a diferença gera chamada.
  Um `change-up` de "só body" cai de ~12 requisições para 1.

### fullsync

Cada item da fila tem um booleano `fullsync`. É `True` em todo create e no
full sync diário (reconcilia propriedades + dependências); `False` em
mudanças incrementais. Se um item full e um parcial coincidem no mesmo alvo,
a fila promove o existente para full (sem duplicar).

### Gatilho de par recíproco

Relações são bidirecionais (`parent`↔`children`, `blocked_by`↔`blocks`). Ao
detectar uma relação adicionada/removida numa issue, o sync enfileira um
`change-down fullsync` do alvo **apenas se o snapshot do alvo ainda não
refletir o par recíproco**. Essa checagem é a condição de parada e evita
reação em cadeia infinita.

## Rate Limit (GitHub)

Toda requisição respeita o throttle, inclusive dentro de loops de
sincronização.

### Detecção

O rate limit é detectado **apenas por sinais de transporte**, nunca pelo corpo
da resposta:

- **Status HTTP** `403`/`429` (linha de status capturada via `gh api -i`).
- **stderr** do `gh` mencionando rate limit.
- **GraphQL**: resposta `200` com `errors[].type == RATE_LIMITED` (a seção
  estruturada de erros, não o conteúdo das issues).

O corpo da resposta **não** é escaneado em busca da expressão "rate limit". Se
fosse, o título/body de uma issue contendo esse texto (ex.: uma issue sobre
custo de API) provocaria falso-positivo em toda listagem, escalando throttle e
penalty indevidamente.

### Throttle
- Sleep antes de cada chamada (inicia em 16s)
- Dobra ao receber secondary rate limit (até 64s)
- Regride após 1h sem problemas

### Penalty
- Ativado quando throttle atinge 64s e ainda falha
- Bloqueia chamadas por N horas (dobra a cada ativação)
- Regride após 1h sem problemas

## Documentação Técnica

Ver [CONTEXT.md](CONTEXT.md) para decisões técnicas e estado do projeto.
