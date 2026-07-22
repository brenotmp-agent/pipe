# US-02 — Autenticação Headless das três credenciais

Status: aprovado
Owner: arquitetura
Last updated: 2026-07-22

## 1. Objetivo

Descrever como a esteira, ao rodar em container Docker, realiza a autenticação
das três dependências externas — SSH (git), GitHub CLI (`gh`) e kiro-cli
(agente) — sem nenhuma interação humana durante a execução.

## 2. Escopo

Esta story cobre os mecanismos de autenticação headless:

- Injeção da chave SSH privada via Docker secret ou volume montado.
- Configuração automática do SSH (`~/.ssh/config`, permissões) por `_setup_ssh()`.
- Validação antecipada (preflight) das três credenciais no arranque (ADR-04).
- Copy Docker-aware das mensagens de erro (catálogo M-01…M-07).

**Fora de escopo:** `docker-compose.yml` com declaração de secrets/volumes
(US-03); runbook de operação (US-06).

## 3. Contexto atual

`_validate_env()` em `src/core/config.py` verifica SSH no arranque (fail-fast).
`GH_TOKEN` e `KIRO_API_KEY` são validadas lazily — falham na primeira operação
de board ou agente, não no arranque. Isso produz falha tardia e não
correlacionável em container autônomo (AC-06).

## 4. Requisitos funcionais

| ID | Requisito |
|----|-----------|
| RF-01 | Chave SSH injetada via `PIPE_SSH_KEY_FILE` apontando para o caminho dentro do container. |
| RF-02 | `_validate_env()` falha rápido com mensagem M-01 se `PIPE_SSH_KEY_FILE` ausente. |
| RF-03 | `_validate_env()` falha rápido com mensagem M-02 se arquivo não existir. |
| RF-04 | `_setup_ssh()` configura `~/.ssh/config` com `StrictHostKeyChecking no` para `github.com`. |
| RF-05 | Chave copiada para `~/.ssh/id_pipe` com permissão `0o600`. |
| RF-06 | `GH_TOKEN` como env var é suficiente para `gh auth status` retornar sucesso (sem `gh auth login`). |
| RF-07 | `KIRO_API_KEY` como env var é suficiente para `kiro-cli whoami` confirmar autenticação headless. |
| RF-08 | `preflight()` verifica as três credenciais, agrega resultados e falha com `exit 1` se qualquer obrigatória falhar. |
| RF-09 | Nenhuma credencial embutida na imagem Docker. |

## 5. Mecanismo de injeção da chave SSH

### Opção A — Docker secrets (preferida para produção)

```yaml
services:
  pipe:
    image: pipe:latest
    secrets:
      - ssh_key
    environment:
      PIPE_SSH_KEY_FILE: /run/secrets/ssh_key

secrets:
  ssh_key:
    file: ~/.ssh/id_ed25519
```

Vantagem: secret montado em memória (`tmpfs`), não persiste no filesystem do
container.

### Opção B — Volume bind-mount (aceitável para desenvolvimento)

```yaml
services:
  pipe:
    image: pipe:latest
    volumes:
      - ~/.ssh/id_ed25519:/run/ssh_key:ro
    environment:
      PIPE_SSH_KEY_FILE: /run/ssh_key
```

## 6. Fluxo de arranque com preflight (estado-alvo após implementação)

```
main()
  └─ check_config()         ← _validate_env(): verifica PIPE_SSH_KEY_FILE
       └─ ConfigError (M-01 / M-02) se falhar → SystemExit(1)
  └─ startup(config)
       └─ _setup_ssh()      ← copia chave → ~/.ssh/id_pipe (0o600)
                            ← escreve ~/.ssh/config (Host github.com)
       └─ preflight()       ← verifica SSH + gh + kiro-cli; agrega resultados
                            ← SystemExit(1) se qualquer credencial falhar
  └─ (clone git via SSH)    ← usa ~/.ssh/id_pipe via ~/.ssh/config
  └─ loop principal
```

Sequência de log esperada no happy path (cena A do protótipo):

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

## 7. Mensagens de erro (copy)

Todas as mensagens estão definidas no catálogo canônico:
`doc/stories/rodar-no-docker/ux/error-copy-spec.md` — M-01 a M-07.

O texto das mensagens não deve conter referências a `export` no host nem
caminhos de máquina física.

## 8. Mecanismos headless por credencial

### 8.1 SSH

`PIPE_SSH_KEY_FILE` aponta para o arquivo da chave privada no container.
`_setup_ssh()` copia para `~/.ssh/id_pipe` (nome fixo, permissão `0o600`) e
grava `~/.ssh/config` para que git use essa chave em `github.com`.

### 8.2 GitHub CLI (`gh`)

`GH_TOKEN` no ambiente é o mecanismo oficial de autenticação headless do `gh`.
A variável tem precedência sobre credenciais armazenadas — comportamento correto
para container efêmero. `gh auth status` retorna exit 0 sem `gh auth login`.

Escopos necessários: `repo` e `project` (o `GitHubBoardAdapter` movimenta cards
no GitHub Projects V2).

Extração de identidade da saída de `gh auth status`:
```
  ✓ Logged in to github.com account <user> (...)
```
Regex: `account\s+(\S+)` — captura o grupo 1 como `@user`.

### 8.3 kiro-cli

`KIRO_API_KEY` no ambiente faz o kiro-cli pular o login por browser (Kiro CLI
≥ 2.0). Precedência: (1) sessão de browser — inexistente em container; (2)
`KIRO_API_KEY` — sempre o método ativo aqui; (3) nenhum.

Subcomando de verificação: `kiro-cli whoami` (confirmado na versão instalada).
- Exit 0 com `KIRO_API_KEY` válida: autenticado.
- Exit não-zero: key inválida/revogada/expirada → mensagem M-06.
- `FileNotFoundError`: binário não encontrado → mensagem M-07.

**Nota:** em desenvolvimento com sessão de browser ativa, `kiro-cli whoami`
pode retornar exit 0 mesmo sem `KIRO_API_KEY`. Em container sem sessão de
browser, `KIRO_API_KEY` é o único método — essa é a condição que o preflight
testa.

### 8.4 Continuidade de sessão (R-1 — fechado)

Sessões do kiro-cli são armazenadas em SQLite local em `~/.kiro/` (keyed por
cwd), independente do método de autenticação. `--list-sessions` e `--resume-id`
operam normalmente sob `KIRO_API_KEY`. O mecanismo `SessionIndex` da esteira
funciona integralmente em container — desde que `~/.kiro/` seja volume
persistente (US-03).

## 9. Decisões de design

| Decisão | Justificativa |
|---------|---------------|
| `StrictHostKeyChecking no` | Evita prompt interativo de confirmação de host no primeiro clone. Aceitável pois o repositório é controlado (GitHub). |
| Cópia para `~/.ssh/id_pipe` | Garante nome fixo e permissão correta independente de como o secret foi montado. |
| `_validate_env()` como primeira barreira | Fail-fast com mensagem clara antes do clone; evita erro críptico de SSH. |
| Preflight separado de `_validate_env()` | `preflight()` é autônomo e testável; não chama `_validate_env()` diretamente (evita acoplamento e efeitos colaterais). |
| Preflight + lazy, não só preflight | Mantém a rede de segurança contra expiração/revogação em runtime. |
| Bump de versão MINOR | Adição de comportamento (preflight), não correção; incremento semântico obrigatório. |

## 10. Impacto em código

- **Novo:** `src/core/preflight.py` com a função `preflight()` (issue #34).
- **Alterado:** `src/core/config.py` → copy de `_validate_env()` para M-01/M-02 (issue #33).
- **Alterado:** `src/__main__.py` → chamada de `preflight()` em `startup()` (issue #35).
- **Alterado:** `src/core/version.py` → bump MINOR (issue #36).

## 11. Rastreabilidade de aceitação

| AC | Critério | Issue |
|----|----------|-------|
| AC-01 | SSH: chave montada e `_setup_ssh` copia sem preparação manual | #34, #35 |
| AC-02 | gh: `GH_TOKEN` + `gh auth status` retorna sucesso no container | #34, #35 |
| AC-03 | kiro-cli: `KIRO_API_KEY` + `kiro-cli whoami` confirma método ativo | #34, #35 |
| AC-04 | Continuidade de sessão: `--resume-id` opera sob `KIRO_API_KEY` | documentado; implementado no adapter |
| AC-05 | Nenhuma credencial embutida na imagem | #45 (Dockerfile) |
| AC-06 | Preflight agrega resultados e falha com `exit 1` antes do loop | #34, #35 |
