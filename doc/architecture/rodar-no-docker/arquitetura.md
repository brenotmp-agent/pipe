# Arquitetura — Rodar no Docker

Status: draft
Owner: architecture
Last updated: 2026-07-02

## Inputs
- doc/product/rodar-no-docker/{vision,problem-space,epicos}.md
- doc/requirements/rodar-no-docker/requisitos.md (RF-01..08, RNF-01..05, D-01..04)
- src/__main__.py (`startup`, `_setup_ssh`), src/core/config.py
- src/adapters/kiro_cli_agent.py, src/adapters/github_board.py
- Investigação do runtime `kiro-cli` 2.4.2 (feita nesta etapa)

---

## 1. Resumo executivo

A esteira já é uma aplicação Python autocontida (`python -m src`, única
dependência `pyyaml`). O esforço de containerização é essencialmente de
**empacotamento + injeção de credenciais por fora**, sem tocar na lógica de
negócio (RNF-04).

O único risco potencialmente bloqueador levantado pelas etapas anteriores —
**D-01 / RF-04: autenticação headless do `kiro-cli`** — foi investigado nesta
etapa e está **RESOLVIDO**. Não há bloqueio técnico. A feature é viável com
Docker + docker-compose.

---

## 2. Resolução do risco D-01 (autenticação headless do kiro-cli)

### 2.1 Investigação

Ambiente inspecionado: `kiro-cli 2.4.2` (via PATH em `~/.local/bin/kiro-cli`).

Descobertas:

- O `kiro-cli` persiste o token de autenticação em
  **`~/.aws/sso/cache/kiro-auth-token-cli.json`**.
- Estrutura do arquivo (chaves, sem valores):
  `accessToken`, `refreshToken`, `expiresAt`, `authMethod`, `provider`,
  `profileArn`.
- O login corrente usa `authMethod=social`, `provider=github`, e **possui
  `refreshToken`**.
- Estado da aplicação (sessões, sqlite) fica em `~/.local/share/kiro-cli/`
  (`data.sqlite3`, `bun`, `tui.js`) e as conversas em `~/.kiro/sessions/cli/`.
- Subcomandos de auth: `login`, `logout`, `whoami`, `profile`, `user`.
- `kiro-cli login` só opera de forma interativa (redirect de browser ou
  `--use-device-flow`, ambos exigindo ação humana). **Não** serve para o
  container.

### 2.2 Decisão

**Não autenticar dentro do container.** A autenticação é feita **uma vez no
host** (`kiro-cli login`), e o **arquivo de token já autenticado é injetado no
container** via volume. Como o arquivo contém `refreshToken`, o `kiro-cli`
renova o `accessToken` sozinho enquanto o refresh token for válido — operação
100% autônoma (RF-04, RF-07).

Requisito de escrita: o `kiro-cli` **reescreve** o arquivo de token ao renovar.
Portanto o cache SSO **deve ser montado como volume read-write** (não como
Docker secret read-only), para que a renovação persista entre ciclos e
reinícios.

### 2.3 Consequências e limites operacionais

- Quando o `refreshToken` expira/é revogado, o container passa a falhar nas
  chamadas do agente. A recuperação é: rodar `kiro-cli login` no host e
  re-injetar o arquivo (documentar em RF-08). Isso **não** é intervenção na
  máquina hospedeira do container — é regeneração de credencial, equivalente ao
  ciclo de vida de qualquer segredo.
- Nenhuma alteração de código é necessária em `kiro_cli_agent.py` — o adapter já
  invoca `kiro-cli chat --no-interactive --trust-all-tools`. RNF-04 preservado.

---

## 3. Estratégia de credenciais (as três dependências)

| Credencial | Mecanismo host→container | Montagem | Consumo no runtime |
|-----------|--------------------------|----------|--------------------|
| **SSH** (git) | Arquivo de chave privada montado como volume; `PIPE_SSH_KEY_FILE` aponta para o caminho interno | volume **ro** | `_setup_ssh` copia para `~/.ssh/id_pipe` e escreve `~/.ssh/config` |
| **gh CLI** (board) | Token via variável de ambiente `GH_TOKEN` (suportado nativamente pelo `gh`) | env | `gh api` lê `GH_TOKEN` automaticamente — sem `gh auth login` |
| **kiro-cli** (agente) | Diretório `~/.aws/sso/cache/` (token pré-autenticado no host) | volume **rw** | `kiro-cli` lê/renova o token sozinho |

Notas:
- A chave SSH pode ser **ro**: `_setup_ssh` faz uma cópia interna para
  `~/.ssh/id_pipe` e ajusta permissões (`0600`); não escreve no arquivo de
  origem.
- O cache SSO precisa ser **rw** (justificativa em §2.2).
- `GH_TOKEN` é preferível a montar `~/.config/gh/hosts.yml` por ser mais simples
  e explícito no compose (RF-05); atende RF-03 e RNF-01 (nada embutido na
  imagem).

---

## 4. Arquitetura de container

### 4.1 Visão de componentes

```
┌──────────────────────── HOST ────────────────────────┐
│  segredos (nunca na imagem):                          │
│   - id_ed25519            (chave SSH)                 │
│   - GH_TOKEN              (env / .env)                │
│   - ~/.aws/sso/cache/     (token kiro-cli, pós-login) │
│  config:                                              │
│   - pipe.yml   - contexts/                            │
│  estado (opcional, persistente):                      │
│   - .pipe/     - logs/     - repo/                    │
└───────────────┬───────────────────────────────────────┘
                │ volumes + env (docker-compose)
┌───────────────▼──────────── CONTAINER ───────────────┐
│  Imagem: python:3.12-slim + git + gh + kiro-cli + src │
│  Entrypoint: python -m src                            │
│   ├─ check_config()  → valida pipe.yml/SSH/contexts   │
│   ├─ startup()       → _setup_ssh, clona repos        │
│   └─ loop: sync_board → keep_task → call_agent        │
│                              └─ kiro-cli chat (headless)│
└───────────────────────────────────────────────────────┘
```

### 4.2 Imagem (Dockerfile — design de referência)

Decisões:
- Base **`python:3.12-slim`** (RNF-02): atende Python 3.12+, imagem enxuta.
- Instalar `git`, `ca-certificates`, `openssh-client` via apt (pin de versão na
  etapa de implementação — RNF-05).
- Instalar `gh` a partir do repositório apt oficial do GitHub CLI (versão
  pinada).
- Instalar `kiro-cli` via instalador oficial, **versão pinada** (D-02). O
  binário usa `bun`/`tui.js` em `~/.local/share/kiro-cli`; o instalador cuida
  disso.
- `pip install --no-cache-dir pyyaml==<pin>` (RNF-05).
- **Nenhum segredo** copiado para a imagem (RNF-01). Só o código-fonte `src/`.
- Rodar como usuário não-root com `$HOME` gravável (necessário para
  `_setup_ssh` escrever `~/.ssh` e para o `kiro-cli` renovar o token).

```dockerfile
FROM python:3.12-slim

# Dependências de sistema (pinar versões na implementação)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates openssh-client curl gnupg \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI (repo oficial) e kiro-cli via instalador oficial (pinar versões)
# ... (detalhamento fica para a etapa de implementação)

# Dependência Python
RUN pip install --no-cache-dir pyyaml==6.0.2

# Usuário não-root com HOME gravável
RUN useradd --create-home --uid 1000 pipe
USER pipe
WORKDIR /app

COPY --chown=pipe:pipe src/ /app/src/

ENTRYPOINT ["python", "-m", "src"]
```

> O `pipe.yml` e `contexts/` **não** são copiados para a imagem — entram por
> volume em runtime (RF-05), permitindo trocar configuração sem rebuild.

### 4.3 Orquestração (docker-compose — design de referência)

```yaml
services:
  esteira:
    build: .
    environment:
      # Autenticação do gh CLI (RF-03) — sem gh auth login
      GH_TOKEN: ${GH_TOKEN:?defina GH_TOKEN no .env}
      # Aponta para a chave SSH montada dentro do container (RF-02)
      PIPE_SSH_KEY_FILE: /run/secrets/ssh_key
    volumes:
      # Configuração (RF-05)
      - ./pipe.yml:/app/pipe.yml:ro
      - ./contexts:/app/contexts:ro
      # Credenciais (RF-02 / RF-04)
      - ${SSH_KEY_PATH:?defina SSH_KEY_PATH}:/run/secrets/ssh_key:ro
      - ${KIRO_SSO_CACHE:-~/.aws/sso/cache}:/home/pipe/.aws/sso/cache:rw
      # Estado persistente (RF-06) — remover se efêmero for aceitável
      - ./.pipe:/app/.pipe
      - ./logs:/app/logs
      - ./repo:/app/repo
    restart: unless-stopped
```

Racional das decisões de compose:
- `restart: unless-stopped` → operação autônoma contínua (RF-07); o loop já
  trata exceções não-fatais internamente, o restart cobre crashes duros.
- Persistência (RF-06 / D-04) é **opcional por design**: os três binds de
  estado podem ser removidos para operação efêmera. Recomendação de arquitetura:
  **persistir** `.pipe/` (snapshots/fila/sessions evitam re-sync completo e
  preservam continuidade de raciocínio do agente) e `repo/` (evita re-clone);
  `logs/` é conveniência.
- Um serviço = uma instância da esteira (fora de escopo: multi-repo no mesmo
  serviço).

---

## 5. Operação autônoma e fail-fast (RF-07)

O código já é adequado à operação headless; a arquitetura apenas o aproveita:

- `check_config()` valida `pipe.yml`, presença/existência da chave SSH
  (`PIPE_SSH_KEY_FILE`) e contexts não-vazios; em erro faz `SystemExit(1)` →
  **fail-fast com exit-code != 0** no arranque (atende critério de RF-07).
- Falta de credencial `gh`/`kiro-cli` não trava com prompt: o `gh` falha na
  chamada e o adapter do agente captura `returncode`/erros e loga; o loop trata
  como erro não-fatal.
- Nenhum ponto do ciclo lê `stdin` — `kiro-cli` é chamado com
  `--no-interactive`.

Ajuste recomendado (não-bloqueante, para a etapa de implementação): garantir
`PYTHONUNBUFFERED=1` na imagem para que os logs apareçam em tempo real em
`docker logs`.

---

## 6. Conformidade com os requisitos

| Req | Como a arquitetura atende |
|-----|---------------------------|
| RF-01 | Imagem `python:3.12-slim` + git + gh + kiro-cli + `src/` + pyyaml |
| RF-02 | Chave SSH via volume ro; `PIPE_SSH_KEY_FILE` aponta para o caminho interno |
| RF-03 | `GH_TOKEN` por env (suporte nativo do `gh`) |
| RF-04 | **Injeção do token pré-autenticado** do `kiro-cli` (§2) — sem login no container |
| RF-05 | `pipe.yml`, `contexts/` e credenciais todos declarados no compose |
| RF-06 | Binds opcionais de `.pipe/`, `logs/`, `repo/` |
| RF-07 | `check_config` fail-fast; nenhum prompt; `restart: unless-stopped` |
| RF-08 | Guia de operação — detalhado na etapa de implementação/doc |
| RNF-01 | Nenhum segredo na imagem; tudo por env/volume |
| RNF-02 | Base slim oficial, deps mínimas |
| RNF-03 | Compose no formato `docker compose` V2 |
| RNF-04 | Zero alteração de lógica de negócio (adapter já é headless) |
| RNF-05 | Versões pinadas (apt, gh, kiro-cli, pyyaml) na implementação |

---

## 7. Decisões arquiteturais (ADR resumido)

- **ADR-01 — Credencial do kiro-cli por injeção de token, não por login no
  container.** Login é interativo; o token tem refresh próprio. Montar o cache
  SSO como volume rw. *(resolve D-01)*
- **ADR-02 — `gh` via `GH_TOKEN`.** Mais simples e explícito que montar config
  do gh; suporte nativo. *(RF-03)*
- **ADR-03 — Chave SSH read-only + cópia interna.** `_setup_ssh` já copia e
  ajusta permissões; origem não precisa ser gravável. *(RF-02)*
- **ADR-04 — Persistência opcional, com recomendação de persistir `.pipe/` e
  `repo/`.** Evita re-sync/re-clone e preserva continuidade de sessão. *(RF-06)*
- **ADR-05 — Usuário não-root com HOME gravável.** Necessário para `~/.ssh` e
  renovação do token do kiro-cli. *(segurança + funcionamento)*
- **ADR-06 — Sem alteração de código da esteira.** Toda adaptação via
  Dockerfile/compose/env. *(RNF-04)*

---

## 8. Riscos residuais para as próximas etapas

| ID | Risco | Severidade | Ação sugerida |
|----|-------|-----------|---------------|
| R-1 | Expiração/revogação do `refreshToken` do kiro-cli interrompe a operação | Média | Documentar em RF-08 o procedimento de re-login no host + re-injeção; monitorar erros do agente nos logs |
| R-2 | Método/versão de instalação do `kiro-cli` no Dockerfile (D-02) | Média | Fixar versão e validar instalador headless na implementação |
| R-3 | Permissões do bind do cache SSO entre host e usuário `pipe` (uid 1000) | Baixa | Alinhar uid/gid ou ajustar ownership do volume na implementação |
| R-4 | `StrictHostKeyChecking no` no `_setup_ssh` (aceita host key sem verificação) | Baixa | Aceitável para github.com; registrar como decisão consciente |

Nenhum risco residual é bloqueador para prosseguir. A implementação
(Dockerfile/compose reais + guia RF-08) pode seguir com base neste desenho.
