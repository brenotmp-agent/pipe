# US-02 — Autenticar dependências externas em modo headless

Status: in-progress
Owner: produto/arquitetura
Last updated: 2026-07-22
Rastreabilidade: RF-02, RF-03, RF-04, D-01, D-03; ADR-01, ADR-02, ADR-03, ADR-04

## User story

**Como** operador, **quero** fornecer as credenciais das três dependências
externas (SSH, GitHub, kiro-cli) por fora do container, **para** que a esteira
autentique e opere sem qualquer interação manual.

## Contexto técnico

São três credenciais que a esteira precisa no arranque:

| # | Credencial | Mecanismo | Verificação |
|---|-----------|-----------|-------------|
| 1 | SSH (git clone) | `PIPE_SSH_KEY_FILE` + volume read-only | `_setup_ssh()` copia para `~/.ssh/id_pipe` |
| 2 | GitHub (`gh` CLI) | `GH_TOKEN` (env var) | `gh auth status` exit 0 |
| 3 | kiro-cli (agente) | `KIRO_API_KEY` (env var) | `kiro-cli whoami` exit 0 |

### §1 — SSH

O mecanismo já existe: `_setup_ssh()` em `src/__main__.py` copia a chave
apontada por `PIPE_SSH_KEY_FILE` para `~/.ssh/id_pipe` e configura
`~/.ssh/config` para usar essa chave no `github.com`. A validação de presença
do arquivo ocorre em `check_config()` via `_validate_env()`.

**Confirmado:** o mecanismo funciona em container; não requer alteração.

### §2 — GitHub CLI (`GH_TOKEN`)

O `gh` CLI respeita `GH_TOKEN`: quando a variável está definida, ele a usa
como token de autenticação **sem** necessidade de `gh auth login`.

`gh auth status` com `GH_TOKEN` válido retorna exit 0 e exibe o usuário
autenticado. Com `GH_TOKEN` inválido ou ausente, retorna exit 1.

**Confirmado via teste (2026-07-22):** comportamento verificado no ambiente de
execução.

**Nota de parsing:** quando `GH_TOKEN` é inválido mas há uma conta no keyring,
`gh auth status` retorna exit 1 e lista **ambas** as contas (a do GH_TOKEN com
`X Failed` e a do keyring). O preflight deve interpretar exit code ≠ 0 como
falha, independentemente do conteúdo da saída.

### §3 — kiro-cli (`KIRO_API_KEY`)

O kiro-cli autentica em modo headless via `KIRO_API_KEY` (ADR-01). O
subcomando de verificação é `kiro-cli whoami`.

**Confirmado via teste (2026-07-22):**
- `kiro-cli whoami` existe, retorna exit 0 e exibe `Logged in with GitHub` +
  email do usuário.
- `kiro-cli whoami --format json` também disponível para parsing estruturado.
- Não existe `kiro-cli auth status`; usar exclusivamente `whoami`.

### §4 — Posição no boot

Ver ADR-04. A sequência correta é:

```
check_config() → _setup_ssh() → preflight() → [clone] → loop
```

`preflight()` deve ser chamado dentro de `startup()`, após `_setup_ssh()` e
antes de qualquer `git clone` ou acesso ao board.

### §5 — Fail-fast agregado

O preflight verifica as três credenciais antes de abortar. Se mais de uma
falhar, o operador vê todas as pendências de uma vez. Ver terminal-prototypes
cena F para o formato de saída esperado.

### §6 — Integração ao boot (`src/__main__.py`)

```python
from src.core.preflight import preflight

def startup(config: dict):
    log.info("Startup", "Verificando repositórios")
    _setup_ssh()
    preflight()          # ← posição correta
    REPO_DIR.mkdir(exist_ok=True)
    # ... resto inalterado
```

### §7 — Propagação do `SystemExit`

O `SystemExit(1)` levantado pelo `preflight()` não é capturado pelo loop
`while running` em `main()`, pois o loop usa `except Exception` — e
`SystemExit` herda de `BaseException`, não de `Exception`. A propagação é
correta e natural.

**Verificado no código atual de `src/__main__.py`:** não há `except
BaseException` nem `except:` bare que engoliriam o `SystemExit`.

### §8 — Testes de integração do boot

`tests/test_startup.py` deve cobrir:

- Happy path: `startup()` retorna normalmente quando preflight passa.
- Falha de GH_TOKEN: `startup()` levanta `SystemExit(1)`.
- Falha de KIRO_API_KEY: `startup()` levanta `SystemExit(1)`.
- Falha de `_setup_ssh()`: preflight não é chamado.

### §9 — Sequência de log esperada (happy path)

```
[Config]    Validando pipe.yml
[Config]    pipe.yml válido
[Startup]   Verificando repositórios
[Preflight] Verificando credenciais das dependências externas...
[Preflight] ✓ SSH       chave carregada de <caminho> → ~/.ssh/id_pipe
[Preflight] ✓ GitHub    gh autenticado como @<user> (via GH_TOKEN)
[Preflight] ✓ kiro-cli  método ativo: API key (via KIRO_API_KEY)
[Preflight] 3/3 credenciais OK — modo headless pronto
[Startup]   Clonando main
```

## Critérios de aceitação

- **AC-01 (SSH):** chave privada montada por volume read-only e
  `PIPE_SSH_KEY_FILE` apontando para o caminho interno; `_setup_ssh()` copia
  para `~/.ssh/id_pipe` sem preparação manual do host.
- **AC-02 (gh):** com `GH_TOKEN` válido por env, `gh auth status` retorna
  success dentro do container sem `gh auth login`.
- **AC-03 (kiro-cli):** com `KIRO_API_KEY` por env, `kiro-cli whoami` confirma
  o método ativo.
- **AC-04 (preflight integrado):** `preflight()` é chamado em `startup()` após
  `_setup_ssh()` e antes do clone; com qualquer credencial ausente, o processo
  encerra com exit 1 antes de qualquer clone.
- **AC-05 (fail-fast agregado):** múltiplas credenciais ausentes são todas
  reportadas antes de abortar.
- **AC-06 (SystemExit propagado):** `SystemExit(1)` não é engolido por nenhum
  `except` no código existente.
- **AC-07 (testes):** `tests/test_preflight.py` e `tests/test_startup.py`
  existem e todos os testes passam.

## Dúvidas resolvidas

| # | Dúvida | Resolução |
|---|--------|-----------|
| D-01 | kiro-cli autentica em headless? | Sim, via KIRO_API_KEY (ADR-01) |
| D-02 | Qual subcomando do kiro-cli para verificar? | `kiro-cli whoami` (confirmado 2026-07-22) |
| D-03 | gh respeita GH_TOKEN sem login? | Sim (confirmado 2026-07-22) |
| D-04 | gh auth status com GH_TOKEN inválido retorna o quê? | exit 1, msg "X Failed to log in … token is invalid" |
| D-05 | SystemExit propagado corretamente? | Sim — except Exception no loop não captura BaseException |

## Dependências de implementação

| Task | O que implementa | Status |
|------|-----------------|--------|
| #34 | `src/core/preflight.py` (função isolada) | backlog |
| #35 | Integração de `preflight()` em `startup()` + `tests/test_startup.py` | backlog |

## Referências

- `src/__main__.py` — `startup()`, `main()`
- `src/core/config.py` — `_validate_env()`
- `doc/arch/rodar-no-docker/decisions/adr-04-preflight-credenciais.md`
- `doc/stories/rodar-no-docker/ux/terminal-prototypes.md`
- `doc/stories/rodar-no-docker/ux/error-copy-spec.md`
