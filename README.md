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
│   ├── agent.py            # AgentPort + build_prompt + PROTECTED_PATHS
│   ├── context_generator.py # Gera CONTEXT.md + agente pipe_context no startup
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
.pipe/CONTEXT.md            # Contexto do sistema gerado no startup (protegido)
.kiro/agents/pipe_context.json  # Agente kiro-cli gerado com o contexto do sistema
contexts/<platform>/<agent>.md  # Contextos dos agentes
repo/                       # Repositórios clonados
logs/                       # Logs diários (JSON) + logs de agente (MD)
pipe.yml                    # Configuração
```

## Loop Principal

```
main()
├── check_config()         # Valida pipe.yml, SSH, contexts
├── startup()              # Configura SSH, gera CONTEXT.md, clona repos
├── board_full_sync()      # Sync completo (estrutura + mudanças remotas)
│
└── while running:
    ├── board_full_sync()  # Re-executa se mudou o dia (daily full sync)
    ├── sync_board()       # Detecta mudanças remotas/locais, aplica fila → bool
    ├── keep_task()        # Seleciona próxima tarefa → task | AUTO_ADVANCED | None
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
- Dentro do board, varre coluna a coluna da última para a primeira (`backlog`/`todo` por último)
- Dentro de cada coluna, pega a issue elegível mais antiga (por data)
- Retorno tri-estado: `task` (executa), `AUTO_ADVANCED` (avançou uma issue do `todo`; loop mantém o board e força novo sync), `None` (nada a fazer; loop avança de board)
- Auto-advance de coluna `todo` para próxima coluna (só ocorre se nenhuma coluna posterior tiver tarefa pronta); move os arquivos, atualiza o snapshot e enfileira o `change-up` para o sync propagar ao board
- `parallel: false` → bloqueia auto-advance se já existe issue ativa
- Issues com `/need_human` ou `/blocked_by` no body são ignoradas

### Resolução automática de bloqueios

Uma issue com `/blocked_by`/`/blocks` no body não avança. Como o GitHub mantém
a dependência mesmo com a bloqueadora fechada — e removê-la no board não altera
o `updated_at` (logo não vira `change-down`) —, bloqueios obsoletos são limpos
automaticamente em três situações:

1. **Ao arquivar** (`/archive` no body ou coluna com `on_in:[archive]`): os
   bloqueios da issue são removidos antes de arquivar, e cada issue vinculada
   recebe um `change-down fullsync` para reconciliar (desbloquear).
2. **Ao deletar** (up ou down): as issues apontadas pela deletada têm o vínculo
   de bloqueio removido no board e recebem `change-down fullsync`.
3. **Na inicialização**: toda mudança detectada/recuperada sobe como fullsync,
   reconciliando as dependências.

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

### Contexto do sistema (`CONTEXT.md` gerado no startup)

No startup, a esteira gera automaticamente um contexto de sistema a partir do
`pipe.yml` e o injeta em toda execução de agente. O objetivo é dar ao agente
instruções explícitas derivadas da configuração real, em vez de deixá-lo
inferir comportamento (origem do incidente "Issue Fantasma").

- `generate_context(config)` (em `src/core/context_generator.py`) roda no
  `startup()` e escreve dois arquivos:
  - `.pipe/CONTEXT.md` — instruções em Markdown.
  - `.kiro/agents/pipe_context.json` — arquivo de agente do kiro-cli com o
    mesmo conteúdo.
- O conteúdo é injetado via `--agent pipe_context` (argumento de CLI), **nunca
  embutido inline no prompt**. O adapter usa `KIRO_HOME` apontando para o
  `.kiro` da esteira para que o kiro-cli encontre o agente gerado.
- **Regeneração:** recria se o arquivo não existir OU se o `pipe.yml` for mais
  novo que o `CONTEXT.md`. Caso contrário, mantém o arquivo atual.

O `CONTEXT.md` gerado contém quatro blocos derivados do `pipe.yml`:

1. **Restrições de sistema** — lista de arquivos de estado interno que o agente
   nunca deve ler ou escrever (ver "Proteção de estado interno" abaixo).
2. **Criação de issues** — obriga o padrão `<slug>-body.md` **sem prefixo
   numérico**. O ID real é atribuído pelo GitHub no sync; antes disso o arquivo
   não tem (e não deve ter) prefixo numérico. Foi justamente o prefixo numérico
   inventado pelo agente que disparou o incidente "Issue Fantasma".
3. **Boards e colunas** — tabela de boards/colunas/agentes configurados.
4. **Git flow e branches** — prefixos de branch por flow e branch base.

> **Atenção:** o `.pipe/CONTEXT.md` gerado é diferente do `CONTEXT.md` da raiz
> do projeto (documentação técnica escrita à mão). O arquivo gerado é protegido
> e **não deve ser editado manualmente** — será sobrescrito no próximo restart.

### Proteção de estado interno

Os arquivos de estado interno da esteira (`snapshot.json`, `changeQueue.json`,
`throttle`) são memória exclusiva do core. O agente **não pode** acessá-los. A
proteção age em duas frentes:

- **No prompt:** `src/core/agent.py` mantém a lista `PROTECTED_PATHS` e a função
  `build_prompt` valida que nenhum desses padrões aparece no prompt enviado ao
  agente. Se aparecer, levanta `ValueError` identificando o arquivo — o path do
  snapshot nunca é entregue ao agente.
- **No contexto:** o `CONTEXT.md` gerado instrui explicitamente o agente a nunca
  ler, escrever, criar ou modificar esses arquivos.

Padrões protegidos (`PROTECTED_PATHS`):

| Padrão | Conteúdo |
|--------|----------|
| `.pipe/boards/*/snapshot.json` | Snapshot interno de cada board |
| `.pipe/changeQueue.json` | Fila persistente de sincronismo |
| `.pipe/throttle.json` | Estado do throttle de rate limit |
| `.pipe/throttle-*.json` | Estado do throttle por escopo |

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

### Issues fantasmas (erro irrecuperável)

Quando o sync tenta aplicar uma mudança (`change-up` ou `delete-up`) sobre uma
issue que **não existe** no GitHub, a API responde com
`Could not resolve to an issue or pull request`. Antes, esse erro era tratado
como transitório e, como a fila é *at-least-once*, o evento voltava a cada
ciclo — travando a esteira num loop (ou, na base atual, num crash-loop). Foi a
causa central do incidente "Issue Fantasma".

Agora `_apply_change_up` e `_apply_delete_up` (em `src/core/sync.py`) tratam
esse erro específico: registram um warning
(`removendo do snapshot (issue fantasma)`), removem a entrada correspondente do
snapshot e **descartam** o evento em vez de re-enfileirá-lo. Qualquer outra
exceção continua propagando normalmente.

### Isolamento de IDs entre boards

O espaço de números de issues do GitHub é **compartilhado** entre todos os
boards de um mesmo repositório (epic, story, task…). Sem validação, uma
operação destrutiva num board poderia fechar/alterar uma issue de outro board
que coincidisse no número — foi o que fechou os épicos #1, #2, #3 no incidente.

Antes de qualquer operação destrutiva (`update_issue`, `close_issue`), o adapter
`github_board.py` valida a pertinência via `_belongs_to_board`: uma query
GraphQL lista os `projectItems` da issue e confirma que o projeto do board alvo
está entre eles. Se não pertencer, a operação é **abortada** com um warning
(`não pertence a este board — operação abortada`).

- **Custo:** +1 chamada GraphQL por operação destrutiva. Em um board ativo
  (~10 closes/min) isso adiciona ~10 chamadas/min — dentro da quota padrão de
  5000 pontos/hora do GraphQL do GitHub.

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
- Sleep antes de cada chamada (em segundos; escala `0, 1, 2, 4, ... 64`)
- Ao receber secondary rate limit, dobra (até 64s); se estiver em `0`, sobe para `1`
- Regride após 1h sem problemas: divide por 2; ao chegar em `1`, cai para `0` (sem espera)

### Penalty
- Ativado quando throttle atinge 64s e ainda falha
- Bloqueia chamadas por N horas (dobra a cada ativação)
- Regride após 1h sem problemas

## Documentação Técnica

Ver [CONTEXT.md](CONTEXT.md) para decisões técnicas e estado do projeto.
