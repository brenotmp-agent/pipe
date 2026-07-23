# Arquitetura — US-02: Autenticar dependências externas em modo headless

Status: draft
Owner: arquitetura (Lucas Almeida)
Story: #17 — épico "Rodar no Docker"
Last updated: 2026-07-07

Rastreabilidade: RF-02, RF-03, RF-04, RNF-01, RNF-03, D-01, D-03; ADR-01,
ADR-02, ADR-03, ADR-04; riscos R-1, R-3.

## 1. Problema arquitetural

A esteira depende de três autenticações externas que hoje são feitas **à mão**
no host: chave SSH (git), `gh` (board GitHub Projects) e `kiro-cli` (agente).
Para operar em container sem toque humano, cada uma precisa de um mecanismo
headless — credencial injetada **por fora** da imagem — e de um ponto claro
onde a esteira verifica que autenticou.

O desafio não é técnico-complexo; é de **desenho de contrato**: quais variáveis
e volumes cada dependência exige, onde a esteira as consome, e como falhar de
forma legível quando falta uma. A US-02 produz esse contrato — que a US-03
(compose) e a US-06 (runbook) consomem.

## 2. Restrições e diretrizes

- **Mecanismos oficiais apenas.** Nada de wrappers de login, expect-scripts ou
  gestão de segredos custom. Cada dependência tem suporte headless documentado
  pelo fornecedor; usamos exatamente isso (ADR-01/02/03).
- **Zero segredo na imagem e no log** (RNF-01). Credenciais entram em runtime;
  logs mostram identidade/método/caminho, nunca o valor.
- **Menor mudança de código possível.** `_setup_ssh` e o adapter do kiro-cli já
  operam headless; o `gh` já usa o ambiente. A única adição arquitetural é o
  preflight (ADR-04).
- **Escopo:** o mecanismo e a validação da autenticação. O `docker-compose.yml`
  que declara tudo isso é da US-03; o runbook, da US-06.

## 3. Visão de componentes

```
                         ┌─────────────────── container ───────────────────┐
  host (.env/secret)     │                                                  │
  ─────────────────      │   python -m src                                  │
  PIPE_SSH_KEY_FILE ─────┼─► check_config()  ── valida presença + arquivo   │
  ssh_key (volume ro) ───┼─► _setup_ssh()    ── copia p/ ~/.ssh/id_pipe 0600 │
  GH_TOKEN (env) ────────┼─► preflight()     ── gh auth status              │
  KIRO_API_KEY (env) ────┼─►                    kiro-cli whoami             │
                         │        │                                         │
                         │        ▼                                         │
                         │   startup() ── git clone (SSH) ──► repo/<id>      │
                         │        │                                         │
                         │        ▼                                         │
                         │   loop ── Board(gh) + Agent(kiro-cli)             │
                         └──────────────────────────────────────────────────┘
```

Três superfícies de credencial, três mecanismos, um ponto de verificação
agregada (preflight).

## 4. Desenho por dependência

### 4.1 SSH / git (RF-02 · ADR-03)

- A chave privada é montada **read-only** como Docker secret/volume (ex.:
  `/run/secrets/ssh_key`). `PIPE_SSH_KEY_FILE` aponta para esse caminho.
- `_setup_ssh()` (já existente) copia a chave para `~/.ssh/id_pipe` (`0600`) e
  escreve `~/.ssh/config` com `IdentityFile ~/.ssh/id_pipe` e
  `StrictHostKeyChecking no` para `github.com`. A cópia é necessária porque a
  origem é read-only e o SSH exige permissão restrita no arquivo de chave.
- O clone SSH em `startup()` é o que **exercita** a credencial: se a chave é
  inválida, o `git clone` falha no arranque (fail-fast natural). Não é preciso
  um teste SSH extra.
- **Já validado em `check_config` → `_validate_env`:** presença da env e
  existência do arquivo. É a única credencial validada hoje no arranque.

### 4.2 gh CLI / board (RF-03 · D-03 · ADR-02)

- `GH_TOKEN` (PAT com escopos `repo` + `project`) definido no ambiente. O `gh`
  o consome automaticamente; `gh auth status` retorna sucesso **sem** nunca
  executar `gh auth login`. `GH_TOKEN` tem precedência sobre credenciais
  armazenadas — o comportamento correto para um container efêmero.
- Escopo `project` é obrigatório porque o `GitHubBoardAdapter` movimenta cards
  no GitHub Projects V2; `repo` cobre issues/PRs.
- **Consumo lazy hoje:** sem preflight, a ausência/insuficiência do token só
  falha na primeira operação de board, no meio do loop (ver §6).

### 4.3 kiro-cli / agente (RF-04 · D-01 · ADR-01 · R-3)

- `KIRO_API_KEY` no ambiente faz o kiro-cli **pular o login por browser
  inteiramente** (Kiro CLI ≥ 2.0). O adapter já invoca `kiro-cli chat
  --no-interactive --trust-all-tools`, que é o modo headless oficial.
- Precedência de autenticação: (1) sessão de browser — inexistente em
  container; (2) `KIRO_API_KEY` — **sempre o método ativo aqui**; (3) nenhum.
  `kiro-cli whoami` (ou o subcomando de status equivalente da versão instalada)
  confirma o método sem imprimir a key.
- **R-3 (pré-requisito operacional):** `KIRO_API_KEY` exige assinatura Kiro Pro
  ou superior; em contas gerenciadas por admin, a geração de keys precisa estar
  habilitada na governança. Documentar no runbook (US-06). Não é decisão de
  arquitetura, é pré-condição de ambiente.

## 5. Continuidade de sessão (R-1 — fechado)

O armazenamento de sessões do kiro-cli é SQLite local em `~/.kiro/` (índice em
`~/.local/share/kiro-cli/`), **keyed por cwd** e **independente do método de
autenticação**. Logo, `--list-sessions` e `--resume-id` operam normalmente sob
`KIRO_API_KEY`, e o mecanismo `SessionIndex` + `.pipe/sessions.json` da esteira
funciona integralmente em container — desde que esses diretórios sejam volumes
persistentes (responsabilidade da US-03).

**Degradação graciosa (contrato de robustez, não débito planejado):** se, em
teste real, `--resume-id` sob API key falhar, o adapter deve executar sem
`--resume-id` (nova sessão), atualizar o índice e registrar como débito. O loop
**nunca** é interrompido por falha de retomada. O código atual já se aproxima
disso: `_run` só adiciona `--resume-id` quando `_session_exists` confirma a
sessão; caso contrário cria uma nova sem erro.

## 6. Decisão-chave: onde validar as credenciais (ADR-04)

Hoje a validação é **assimétrica**: SSH falha no arranque (bom), mas `GH_TOKEN`
e `KIRO_API_KEY` falham **lazy**, tarde, no meio do loop — o operador não
correlaciona o erro com a causa. A prototipação de UX identificou isto como o
pior ponto da jornada (descobertas 1 e 2 do pacote UX).

**Decisão (ADR-04):** adotar um **preflight de credenciais** no `startup()` que
verifica as três de uma vez, **antes do primeiro ciclo**, e falha rápido
(`exit 1`) com um resumo único e legível se qualquer obrigatória faltar. O
preflight **complementa**, não substitui, a validação lazy — esta permanece como
rede de segurança para expiração/revogação em runtime.

Contrato do preflight (o *quê*, não o *como* — implementação é da Engenharia):

| Credencial | Verificação | Falta → |
|---|---|---|
| SSH | presença + arquivo (já em `_validate_env`) | `exit 1` no arranque |
| gh | `gh auth status` (exit code + identidade) | `exit 1` no arranque |
| kiro-cli | `kiro-cli whoami` / status (método = API key) | `exit 1` no arranque |

- Agrega **todas** as pendências num relatório único (não uma-a-uma).
- Emite confirmação positiva no caminho feliz (`3/3 credenciais OK`).
- **Nunca** imprime valor de segredo — só identidade/método/caminho.
- Copy conforme `ux/error-copy-spec.md` (Docker-aware, template causa/ação/onde).
- A degradação de sessão (§5) permanece no loop, **fora** do preflight.

Consequências e alternativas descartadas: ver
[`decisions/adr-04-preflight-credenciais.md`](decisions/adr-04-preflight-credenciais.md).

## 7. Modelo de segurança (RNF-01, RNF-03)

- **Imagem:** nenhuma das três credenciais é copiada ou embutida (verificável
  por `docker history`/`docker inspect`). Herda ADR-06.
- **Runtime:** `GH_TOKEN` e `KIRO_API_KEY` entram por env a partir do `.env` do
  host (fora do git); a chave SSH entra por Docker secret montado read-only.
- **Logs:** superfície de vazamento mais provável. Regra dura: o preflight e as
  mensagens de erro referenciam credenciais por **nome da variável, identidade
  (`@user`) ou método**, jamais pelo conteúdo — nem mascarado.
- **Permissões:** a chave original permanece read-only no ponto de montagem;
  apenas a cópia `~/.ssh/id_pipe` recebe escrita/`0600`.

## 8. Fronteiras de escopo (o que esta arquitetura NÃO decide)

| Fora de escopo | Dona |
|---|---|
| `docker-compose.yml`, `.env.example`, declaração de secrets/volumes | US-03 (#—) |
| Runbook, pré-requisitos, governança de API key (R-3) | US-06 (#—) |
| Imagem base, usuário não-root, HOME gravável (ADR-05/06) | US-01 (#16) |
| Implementação concreta do preflight em `src/` | Engenharia (estágio seguinte) |

## 9. Impacto em código (previsão para a Engenharia)

Mudança mínima. Um único ponto novo:

- **Novo:** função `preflight()` (candidata a `src/__main__.py` ou
  `src/core/`), chamada entre `check_config()`/`_setup_ssh()` e o loop. Consome
  `gh auth status` e o status do kiro-cli; agrega e decide `exit 1`.
- **Inalterado:** `_setup_ssh`, `_validate_env`, `_run` do adapter já operam
  headless. Ajustes só de **copy** de mensagens (ver `ux/error-copy-spec.md`).

Não há mudança de contrato dos ports nem da arquitetura hexagonal. Por ser
adição de comportamento (não correção), a Engenharia deve incrementar a versão
(MINOR) conforme a regra do `CONTEXT.md` ao implementar.

## 10. Rastreabilidade de aceitação

Os critérios AC-01…AC-06 da US-02 (ver `user-stories.md`) são satisfeitos por:
AC-01→§4.1/ADR-03; AC-02→§4.2/ADR-02; AC-03→§4.3/ADR-01; AC-04→§5; AC-05→§7;
AC-06→§6/ADR-04 (que evolui a assimetria documentada para fail-fast agregado,
mantendo o lazy como salvaguarda).

## Fontes (verificação documental)

- kiro-cli headless / `KIRO_API_KEY`: [kiro.dev/docs/cli/headless](https://kiro.dev/docs/cli/headless/),
  [kiro.dev/changelog/cli/2-0](https://kiro.dev/changelog/cli/2-0/)
- gh `GH_TOKEN`: [cli.github.com/manual/gh_help_environment](https://cli.github.com/manual/gh_help_environment),
  [cli.github.com/manual/gh_auth_login](https://cli.github.com/manual/gh_auth_login)

Conteúdo das fontes foi reescrito para conformidade com licenciamento.
