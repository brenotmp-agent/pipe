# Arquitetura — Rodar no Docker

Status: draft
Owner: architecture
Last updated: 2026-07-02 (rev. 2 — autenticação por API key)

## Inputs
- doc/product/rodar-no-docker/{vision,problem-space,epicos}.md
- doc/requirements/rodar-no-docker/requisitos.md (RF-01..08, RNF-01..05, D-01..04)
- src/__main__.py (`startup`, `_setup_ssh`), src/core/config.py
- src/adapters/kiro_cli_agent.py, src/adapters/github_board.py
- Investigação do runtime `kiro-cli` 2.4.2 (feita nesta etapa)
- Documentação oficial do Kiro CLI:
  - Headless mode — https://kiro.dev/docs/cli/headless/
  - Authentication (Authenticate with an API key) —
    https://kiro.dev/docs/cli/authentication

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

O Kiro CLI oferece **modo headless oficial** para automação/CI/CD
(https://kiro.dev/docs/cli/headless/). A autenticação nesse modo é feita por
**API key** via a variável de ambiente **`KIRO_API_KEY`**
(https://kiro.dev/docs/cli/authentication#authenticate-with-an-api-key-headless-mode).

Fatos relevantes da documentação oficial:

- Basta exportar `KIRO_API_KEY` e rodar `kiro-cli chat --no-interactive` — sem
  qualquer login interativo. É exatamente o cenário de container/CI.
- A key é gerada **uma vez** no portal (app.kiro.dev → seção **API Keys**); o
  valor só é exibido no momento da criação. É uma credencial **long-lived**.
- **Precedência de credenciais**: (1) sessão de browser ativa
  (`kiro-cli login`), (2) `KIRO_API_KEY`, (3) sem credencial → o CLI pede
  login. Dentro do container não haverá sessão de browser, então a `KIRO_API_KEY`
  é a credencial efetiva.
- Verificação do método ativo: `kiro-cli whoami`.
- Os créditos consumidos com a API key são debitados da assinatura do usuário.

Investigação complementar do runtime local (`kiro-cli 2.4.2`): o adapter
(`src/adapters/kiro_cli_agent.py`) já invoca
`kiro-cli chat --no-interactive --trust-all-tools [--model ...]` e usa
`--list-sessions`/`--resume-id` para continuidade de raciocínio. Nada disso é
interativo, portanto é compatível com a autenticação por API key.

### 2.2 Decisão

**Autenticar o `kiro-cli` por API key**, injetando `KIRO_API_KEY` como variável
de ambiente (mesmo mecanismo do `GH_TOKEN`). Não se faz `kiro-cli login` no
container e **não** é necessário montar o cache SSO (`~/.aws/sso/cache/`) como
volume. A operação é 100% autônoma e usa o caminho oficialmente suportado para
headless (RF-04, RF-07, RNF-01).

Esta decisão **substitui** a abordagem anterior (rev. 1), que injetava o arquivo
de token pré-autenticado via volume rw. A injeção por env é mais simples, não
depende do ciclo de renovação do `refreshToken` e não exige volume gravável para
o cache SSO.

**Pré-requisito de assinatura:** a autenticação por API key só está disponível
para assinantes **Kiro Pro, Pro+, Pro Max ou Power**. Se a conta for gerenciada
por um administrador, é preciso que o admin habilite a geração de API keys
(governança). Este é o único pré-requisito externo e deve constar em RF-08.

### 2.3 Consequências e limites operacionais

- A `KIRO_API_KEY` é uma credencial de longa duração: deve ser armazenada como
  segredo (`.env`/secret manager), **nunca** embutida na imagem nem versionada
  (RNF-01), e rotacionada conforme a política de credenciais. Se comprometida,
  revogar imediatamente no portal e gerar nova.
- Quando a key é revogada/rotacionada, basta atualizar a variável de ambiente e
  reiniciar o container — sem re-login interativo. Recuperação simples, a
  documentar em RF-08.
- Nenhuma alteração de código é necessária em `kiro_cli_agent.py` — o adapter já
  é headless. RNF-04 preservado.
- A continuidade de sessão (`--list-sessions`/`--resume-id`) e o consumo de
  créditos ocorrem sob a identidade da API key; validar na implementação que a
  listagem/retomada de sessões opera normalmente sob esse método (ver R-1).

---

## 3. Estratégia de credenciais (as três dependências)

| Credencial | Mecanismo host→container | Montagem | Consumo no runtime |
|-----------|--------------------------|----------|--------------------|
| **SSH** (git) | Arquivo de chave privada montado como volume; `PIPE_SSH_KEY_FILE` aponta para o caminho interno | volume **ro** | `_setup_ssh` copia para `~/.ssh/id_pipe` e escreve `~/.ssh/config` |
| **gh CLI** (board) | Token via variável de ambiente `GH_TOKEN` (suportado nativamente pelo `gh`) | env | `gh api` lê `GH_TOKEN` automaticamente — sem `gh auth login` |
| **kiro-cli** (agente) | API key via variável de ambiente `KIRO_API_KEY` (modo headless oficial) | env | `kiro-cli chat --no-interactive` autentica pela `KIRO_API_KEY` — sem login |

Notas:
- A chave SSH pode ser **ro**: `_setup_ssh` faz uma cópia interna para
  `~/.ssh/id_pipe` e ajusta permissões (`0600`); não escreve no arquivo de
  origem.
- As **três** credenciais externas agora entram por env/volume declarados no
  compose (RF-05), nenhuma embutida na imagem (RNF-01). Duas delas (`gh` e
  `kiro-cli`) são apenas variáveis de ambiente — não há mais necessidade de
  montar diretório de cache gravável para o `kiro-cli`.
- `GH_TOKEN` é preferível a montar `~/.config/gh/hosts.yml` por ser mais simples
  e explícito no compose; atende RF-03.
- `KIRO_API_KEY` exige assinatura Kiro Pro/Pro+/Pro Max/Power (§2.2).

---

## 4. Arquitetura de container

### 4.1 Visão de componentes

```
┌──────────────────────── HOST ────────────────────────┐
│  segredos (nunca na imagem):                          │
│   - id_ed25519            (chave SSH, volume ro)      │
│   - GH_TOKEN              (env / .env)                │
│   - KIRO_API_KEY          (env / .env, kiro-cli)      │
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
  `_setup_ssh` escrever `~/.ssh`; o `kiro-cli` também pode gravar estado de
  sessão sob `$HOME`).

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
      # Autenticação headless do kiro-cli (RF-04) — sem login interativo
      KIRO_API_KEY: ${KIRO_API_KEY:?defina KIRO_API_KEY no .env}
      # Aponta para a chave SSH montada dentro do container (RF-02)
      PIPE_SSH_KEY_FILE: /run/secrets/ssh_key
    volumes:
      # Configuração (RF-05)
      - ./pipe.yml:/app/pipe.yml:ro
      - ./contexts:/app/contexts:ro
      # Credencial SSH (RF-02) — read-only, cópia interna feita por _setup_ssh
      - ${SSH_KEY_PATH:?defina SSH_KEY_PATH}:/run/secrets/ssh_key:ro
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
| RF-04 | **API key `KIRO_API_KEY`** por env — modo headless oficial do kiro-cli, sem login no container (§2) |
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

- **ADR-01 — Credencial do kiro-cli por API key (`KIRO_API_KEY`), não por login
  no container.** Modo headless oficialmente suportado; a key é injetada por env
  como o `GH_TOKEN`. Sem volume de cache SSO, sem dependência de renovação de
  refresh token. Requer assinatura Pro/Pro+/Pro Max/Power. *(resolve D-01)*
- **ADR-02 — `gh` via `GH_TOKEN`.** Mais simples e explícito que montar config
  do gh; suporte nativo. *(RF-03)*
- **ADR-03 — Chave SSH read-only + cópia interna.** `_setup_ssh` já copia e
  ajusta permissões; origem não precisa ser gravável. *(RF-02)*
- **ADR-04 — Persistência opcional, com recomendação de persistir `.pipe/` e
  `repo/`.** Evita re-sync/re-clone e preserva continuidade de sessão. *(RF-06)*
- **ADR-05 — Usuário não-root com HOME gravável.** Necessário para `~/.ssh` e
  para o estado de sessão do kiro-cli sob `$HOME`. *(segurança + funcionamento)*
- **ADR-06 — Sem alteração de código da esteira.** Toda adaptação via
  Dockerfile/compose/env. *(RNF-04)*

---

## 8. Riscos residuais para as próximas etapas

| ID | Risco | Severidade | Ação sugerida |
|----|-------|-----------|---------------|
| R-1 | Continuidade de sessão (`--list-sessions`/`--resume-id`) sob autenticação por API key não verificada no runtime | Média | Validar na implementação que a listagem/retomada de sessões funciona com `KIRO_API_KEY`; se não, degradar para execução sem retomada (sem quebrar o loop) |
| R-2 | Método/versão de instalação do `kiro-cli` no Dockerfile (D-02) | Média | Fixar versão e validar `--no-interactive` na implementação |
| R-3 | Assinatura sem direito a API key (não é Pro/Pro+/Pro Max/Power) ou governança de admin bloqueando geração | Média | Documentar pré-requisito em RF-08; validar com `kiro-cli whoami` no arranque |
| R-4 | Revogação/rotação/expiração da `KIRO_API_KEY` interrompe as chamadas do agente | Baixa | Documentar em RF-08 o procedimento de rotação (atualizar env + restart); monitorar erros do agente nos logs |
| R-5 | `StrictHostKeyChecking no` no `_setup_ssh` (aceita host key sem verificação) | Baixa | Aceitável para github.com; registrar como decisão consciente |

Nenhum risco residual é bloqueador para prosseguir. A implementação
(Dockerfile/compose reais + guia RF-08) pode seguir com base neste desenho.
