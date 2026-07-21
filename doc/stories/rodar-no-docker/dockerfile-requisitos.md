# Requisitos Técnicos — Dockerfile (US-01 + AC-04/AC-05 de US-05)

Status: aprovado
Owner: requisitos
Last updated: 2026-07-21
Autora: Rafael Martins — Analista de Requisitos

---

## Escopo

Este documento especifica os requisitos técnicos para a criação/atualização do
`Dockerfile` na raiz do repositório. Cobre:

- **US-01 (#16) completa** — empacotamento da imagem com todos os binários
- **AC-04 da US-05 (#20)** — `PYTHONUNBUFFERED=1` para logs em tempo real
- **AC-05 de US-01** — usuário não-root com `$HOME` gravável (ADR-05)

---

## Diagnóstico do Dockerfile existente

O `Dockerfile` atual **não atende** os seguintes requisitos:

| Requisito | Status atual | Ação necessária |
|-----------|-------------|-----------------|
| `PYTHONUNBUFFERED=1` | Ausente | Adicionar `ENV PYTHONUNBUFFERED=1` |
| Usuário não-root | Roda como `root` | Criar usuário `pipe` (uid 1000) |
| pyyaml versão pinada | `pyyaml` sem versão | Fixar em `pyyaml==6.0.2` |
| git versão pinada | `git` sem versão | Pinado no apt (ver seção abaixo) |
| gh instalado via apt oficial | Tarball direto do GitHub | Manter tarball (ver decisão abaixo) |
| kiro-cli instalado via binário | `COPY kiro-cli` do host | Manter `COPY` (ver decisão abaixo) |
| README.md/CONTEXT.md copiados | Presentes no COPY | Remover (fora de escopo) |
| openssh-client | `ssh` instalado | Renomear para `openssh-client` |
| `jq` | Presente | Verificar necessidade; manter por ora |

---

## Decisões de implementação

### Instalação do gh CLI

O body da issue propõe instalar o `gh` via repositório apt oficial
(`githubcli-archive-keyring.gpg`). No entanto, o método atual via tarball
direto do GitHub Releases **também é válido e mais simples** para pinagem de
versão. A decisão de qual método usar fica a critério do desenvolvedor, desde
que a versão seja pinada.

**Versão mais recente verificada em 2026-07-21:** `2.96.0`
(fonte: https://github.com/cli/cli/releases — versão latest em 2026-07-02)

Ambos os métodos são aceitos:

**Método A — tarball (atual, mais simples):**
```dockerfile
ARG GH_VERSION=2.96.0
RUN curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz" \
    | tar -xz -C /usr/local/bin --strip-components=2 "gh_${GH_VERSION}_linux_amd64/bin/gh" \
    && gh --version
```

**Método B — apt oficial (como especificado no body da issue):**
```dockerfile
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
        https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        gh=2.96.0 \
    && rm -rf /var/lib/apt/lists/*
```

> **Nota:** o apt do GitHub CLI usa versão `2.96.0` (sem sufixo) para pinagem
> via `gh=2.96.0`. Verificar disponibilidade no repositório durante o build.

### Instalação do kiro-cli

**Limitação crítica identificada:** A documentação oficial do kiro-cli
(https://kiro.dev/docs/cli/installation/) **não fornece um instalador com
versão pinada**. Todas as URLs de download usam `latest`:

```
https://desktop-release.q.us-east-1.amazonaws.com/latest/kiro-cli.deb
https://desktop-release.q.us-east-1.amazonaws.com/latest/kirocli-x86_64-linux.zip
```

Isso inviabiliza a pinagem de versão exigida pelo requisito RNF-05.

**Decisão (ADR implícita):** Manter a estratégia atual de **copiar o binário do
host** via `COPY kiro-cli /usr/local/bin/kiro-cli`. Esta abordagem:

- **Vantagem:** versão controlada e reproducível (o binário copiado é exatamente
  o que está no host e foi validado).
- **Desvantagem:** requer que o binário esteja disponível no contexto de build
  (o `prepare-docker.sh` já resolve isso).
- **Risco R-2 (parcialmente mitigado):** o método de instalação está fixo no
  binário do host; a versão não está declarada explicitamente no Dockerfile,
  mas é controlada pelo operador que executa `prepare-docker.sh`.

O body da issue sugere `curl -fsSL https://kiro.dev/install.sh | bash -s -- --version <VERSION>`,
mas esse instalador **não existe na documentação oficial** de kiro.dev (2026-07-21).
O instalador oficial (`https://cli.kiro.dev/install`) não aceita flag `--version`.

**Recomendação para o desenvolvedor:** documentar no `prepare-docker.sh` a
versão do kiro-cli copiado, para rastreabilidade.

### Versão do git

O apt do Debian Bookworm slim disponibiliza `git=1:2.39.*`. A pinagem exata
(`git=1:2.39.5-0+deb12u2`, por exemplo) pode ser frágil e quebrar em diferentes
mirrors. Usar `git=1:2.39.*` como wildcard no apt ou simplesmente `git` sem
versão é aceitável, com a seguinte justificativa documentada:

> O `git` no `python:3.12-slim` é fornecido pelo repositório Debian estável;
> a versão muda apenas em updates de segurança e é previsível. O risco de
> divergência é baixo. Se o projeto exigir pinagem exata, usar `apt-cache policy git`
> para descobrir a versão disponível no momento do build.

### Usuário não-root e volumes do docker-compose

**Atenção para o desenvolvedor:** o `docker-compose.yml` atual monta volumes
em caminhos de `/root/`:

```yaml
- ${SSH_KEY_FILE}:/root/.ssh/id_ed25519:ro
- ${GH_CONFIG_DIR}:/root/.config/gh:ro
```

Com a introdução do usuário `pipe` (uid 1000, home `/home/pipe`), esses
caminhos devem ser **atualizados no docker-compose.yml** (tarefa da issue #41)
para:

```yaml
- ${SSH_KEY_FILE}:/home/pipe/.ssh/id_ed25519:ro
- ${GH_CONFIG_DIR}:/home/pipe/.config/gh:ro
```

E a variável de ambiente:

```yaml
PIPE_SSH_KEY_FILE: /home/pipe/.ssh/id_ed25519
```

> **Escopo:** a atualização do `docker-compose.yml` é de responsabilidade da
> issue #41. O `Dockerfile` (esta task) apenas declara o usuário `pipe`; a
> consistência dos volumes é responsabilidade da task seguinte.

---

## Especificação do Dockerfile

O Dockerfile final deve ter esta estrutura (em ordem):

```
1. FROM python:3.12-slim
2. Dependências apt (git, openssh-client, ca-certificates, curl, gnupg + jq se necessário)
3. gh CLI (versão 2.96.0 — método A ou B)
4. kiro-cli (COPY do contexto de build)
5. pyyaml==6.0.2
6. ENV PYTHONUNBUFFERED=1
7. RUN useradd --create-home --uid 1000 pipe
8. USER pipe
9. WORKDIR /app
10. COPY --chown=pipe:pipe src/ /app/src/
11. ENTRYPOINT ["python", "-m", "src"]
```

### Arquivo completo de referência

```dockerfile
FROM python:3.12-slim

# ── Dependências de sistema ──────────────────────────────────────────────────
# openssh-client: necessário para _setup_ssh configurar ~/.ssh/
# ca-certificates: validação TLS de endpoints GitHub/kiro
# curl, gnupg: bootstrap do repositório do gh CLI (se usar método B)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        openssh-client \
        ca-certificates \
        curl \
        gnupg \
    && rm -rf /var/lib/apt/lists/*

# ── GitHub CLI (versão pinada) ───────────────────────────────────────────────
# Versão verificada em 2026-07-21: 2.96.0
# Método: tarball direto do GitHub Releases (reproducível, versão explícita)
ARG GH_VERSION=2.96.0
RUN curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz" \
    | tar -xz -C /usr/local/bin --strip-components=2 "gh_${GH_VERSION}_linux_amd64/bin/gh" \
    && gh --version

# ── kiro-cli (binário copiado do host via prepare-docker.sh) ────────────────
# Versão: controlada pelo operador via prepare-docker.sh
# Justificativa: kiro.dev não oferece URL de download com versão pinada (2026-07-21)
COPY kiro-cli /usr/local/bin/kiro-cli
RUN chmod +x /usr/local/bin/kiro-cli

# ── Dependências Python ──────────────────────────────────────────────────────
RUN pip install --no-cache-dir pyyaml==6.0.2

# ── Variável crítica para logs em tempo real (AC-04 da US-05, 12-Factor XI) ──
ENV PYTHONUNBUFFERED=1

# ── Usuário não-root com HOME gravável (AC-05 de US-01, ADR-05) ─────────────
# _setup_ssh escreve em ~/.ssh/; kiro-cli persiste estado de sessão sob ~/
RUN useradd --create-home --uid 1000 pipe

USER pipe
WORKDIR /app

# ── Código-fonte (sem segredos, sem pipe.yml, sem contexts/) ─────────────────
# pipe.yml e contexts/ entram por volume em runtime (RF-05, AC-03 de US-01)
COPY --chown=pipe:pipe src/ /app/src/

ENTRYPOINT ["python", "-m", "src"]
```

---

## Critérios de verificação após implementação

```bash
# 1. Build deve concluir sem erro
docker build -t pipe-esteira .

# 2. Binários no PATH
docker run --rm pipe-esteira python --version   # Python 3.12.x
docker run --rm pipe-esteira git --version
docker run --rm pipe-esteira gh --version       # 2.96.0
docker run --rm pipe-esteira kiro-cli --version

# 3. Usuário não-root
docker run --rm pipe-esteira id                 # uid=1000(pipe)
docker run --rm pipe-esteira whoami             # pipe

# 4. PYTHONUNBUFFERED definido (AC-04)
docker run --rm pipe-esteira env | grep PYTHONUNBUFFERED  # PYTHONUNBUFFERED=1

# 5. Fail-fast sem credenciais (AC-07 de US-01 / AC-02 de US-05)
docker run --rm pipe-esteira; echo "Exit: $?"   # deve imprimir Exit: 1

# 6. Nenhum segredo na imagem
docker run --rm pipe-esteira ls /app/           # apenas src/
docker run --rm pipe-esteira test -f /app/pipe.yml && echo "FALHOU" || echo "OK"
```

---

## Riscos identificados

| ID   | Risco | Mitigação |
|------|-------|-----------|
| R-2  | kiro-cli sem versão pinada via URL pública | Copiar binário do host; documentar versão no prepare-docker.sh |
| R-3  | gh CLI versão desatualizada | Verificar https://github.com/cli/cli/releases antes de atualizar ARG |
| R-6  | docker-compose.yml com paths /root/ incompatíveis com usuário pipe | Atualizar no docker-compose.yml (escopo da issue #41) |

---

## Rastreabilidade

US-01 (#16) | AC-04 e AC-05 da US-05 (#20) | RF-01, RNF-01, RNF-02, RNF-05 | ADR-05
