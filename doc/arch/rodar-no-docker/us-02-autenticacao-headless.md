# US-02 — Autenticação Headless (SSH + GitHub CLI)

Status: aprovado
Owner: arquitetura
Last updated: 2026-07-22

## 1. Objetivo

Descrever como a esteira, ao rodar em container Docker, realiza a autenticação
via SSH (para operações Git) e via GitHub CLI (`gh`) sem nenhuma interação
humana durante a execução — sem prompts, sem browser, sem `ssh-agent` manual.

## 2. Escopo

Esta user story cobre exclusivamente os mecanismos de autenticação headless:

- Injeção da chave SSH privada no container via Docker secrets ou volume montado.
- Configuração automática do SSH (`~/.ssh/config`, permissões) feita pela função
  `_setup_ssh()` em `src/__main__.py`.
- Validação antecipada (preflight) da presença e acessibilidade da chave SSH,
  feita por `_validate_env()` em `src/core/config.py`.

**Fora de escopo:** autenticação do `kiro-cli` (tratada em US-03), criação da
imagem Docker (tratada em US-01), documentação de operação para o usuário final
(tratada em US-04).

## 3. Contexto atual

`src/__main__.py` → `_setup_ssh()` copia o arquivo apontado por
`PIPE_SSH_KEY_FILE` para `~/.ssh/id_pipe` e grava um bloco em `~/.ssh/config`
que instrui o SSH a usar essa chave para `github.com` com
`StrictHostKeyChecking no`.

`src/core/config.py` → `_validate_env()` verifica, no arranque, se
`PIPE_SSH_KEY_FILE` está definida e se o arquivo existe — falhando com
`ConfigError` e mensagem clara antes de qualquer tentativa de clone.

## 4. Requisitos funcionais

| ID  | Requisito |
|-----|-----------|
| RF-01 | A chave SSH deve ser injetada **exclusivamente** via variável de ambiente `PIPE_SSH_KEY_FILE` apontando para o caminho do arquivo dentro do container. |
| RF-02 | `_validate_env()` deve falhar de forma rápida (antes do clone) se `PIPE_SSH_KEY_FILE` não estiver definida, com mensagem M-01 do catálogo `error-copy-spec.md`. |
| RF-03 | `_validate_env()` deve falhar de forma rápida se o arquivo apontado por `PIPE_SSH_KEY_FILE` não existir no container, com mensagem M-02 do catálogo. |
| RF-04 | `_setup_ssh()` deve configurar `~/.ssh/config` com `StrictHostKeyChecking no` para `github.com`, eliminando prompts interativos de verificação de host. |
| RF-05 | A chave SSH copiada para `~/.ssh/id_pipe` deve ter permissão `0o600`. |
| RF-06 | Nenhum segredo deve estar embutido na imagem Docker — toda credencial é fornecida em tempo de execução. |

## 5. Mecanismo recomendado de injeção da chave

### Opção A — Docker secrets (preferida para produção)

```yaml
# docker-compose.yml
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

Vantagem: o secret é montado em memória (`tmpfs`), não fica no filesystem
persistente do container.

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

## 6. Fluxo de autenticação no arranque

```
main()
  └─ check_config()         ← _validate_env(): verifica PIPE_SSH_KEY_FILE
       └─ ConfigError (M-01 / M-02) se falhar → SystemExit(1)
  └─ startup(config)
       └─ _setup_ssh()      ← copia chave → ~/.ssh/id_pipe (0o600)
                            ← escreve ~/.ssh/config (Host github.com / id_pipe)
  └─ (clone git via SSH)    ← usa ~/.ssh/id_pipe via ~/.ssh/config
```

## 7. Mensagens de erro (copy)

As mensagens de erro de SSH estão definidas no catálogo canônico:

- `doc/stories/rodar-no-docker/ux/error-copy-spec.md` — seções M-01 e M-02.

O texto das mensagens **não deve** conter referências a `export` no host nem
caminhos de máquina física. Deve guiar o operador a configurar o Docker secret
ou volume correto.

## 8. Decisões de design

| Decisão | Justificativa |
|---------|---------------|
| `StrictHostKeyChecking no` | Evita prompt interativo de confirmação de host em primeiro clone. Aceitável pois o repositório é controlado (GitHub). |
| Cópia para `~/.ssh/id_pipe` em vez de usar diretamente o path original | Garante nome fixo e permissão correta independente de como o secret foi montado. |
| Falha antecipada em `_validate_env()` antes do clone | Fail-fast com mensagem clara; evita erro críptico de SSH no meio do clone. |

## 9. Testes relevantes

Não há testes automatizados de `_validate_env()` na suite atual. A task que
implementa as novas mensagens (issue #33) deve garantir que os testes existentes
continuem passando; testes específicos de `_validate_env()` podem ser adicionados
em task futura se necessário.
