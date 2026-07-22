# Arquitetura — Rodar no Docker

Status: em andamento
Owner: engenharia
Last updated: 2026-07-22

## Referências

- `doc/product/rodar-no-docker/vision.md`
- `doc/stories/rodar-no-docker/user-stories.md`
- `doc/stories/rodar-no-docker/ux/prototipos/docker-compose.prototipo.yml`
- `doc/stories/rodar-no-docker/ux/prototipos/.env.prototipo`

---

## §1 — Visão geral

A esteira é empacotada numa imagem Docker com todas as dependências de runtime
(Python, Git, `gh` CLI, `kiro-cli`). A configuração e os segredos são injetados
por fora, via docker-compose, sem reconstrução da imagem. O estado de runtime
é persistido em bind mounts no host, auditáveis pelo operador.

---

## §2 — Dependências da imagem

| Dependência | Versão | Origem |
|-------------|--------|--------|
| Python | 3.12-slim | imagem base |
| Git | sistema | `apt` |
| GitHub CLI (`gh`) | 2.94.0 | binário oficial |
| `kiro-cli` | nativo do host | `prepare-docker.sh` |
| `pyyaml` | `pip` | requisito da esteira |

---

## §3 — Diagrama de volumes

```
HOST                              CONTAINER (/app)
─────────────────────────────     ──────────────────────────────
./pipe.yml          ────────────► /app/pipe.yml        (ro)
./contexts/         ────────────► /app/contexts/       (rw)
~/.ssh/id_ed25519   ────────────► /root/.ssh/id_ed25519 (ro)
~/.config/gh/       ────────────► /root/.config/gh/   (ro)

${PIPE_STATE_DIR:-./.pipe}  ────► /app/.pipe           (rw)  ← D-05
${PIPE_REPO_DIR:-./repo}    ────► /app/repo            (rw)  ← D-05
${PIPE_LOGS_DIR:-./logs}    ────► /app/logs            (rw)  ← D-05
```

Os três últimos volumes (marcados `← D-05`) são o contrato de estado desta
arquitetura. Ver §4 para a decisão de design.

---

## §4 — Modelo de estado (D-05)

### Decisão: bind mounts em vez de named volumes para o estado de runtime

**Contexto:** o estado de runtime da esteira (`.pipe/`, `repo/`, `logs/`)
precisa sobreviver a reinícios do container. Há duas abordagens possíveis:
named volumes gerenciados pelo Docker, ou bind mounts para diretórios no host.

**Decisão (ADR-04):** usar **bind mounts** para os três diretórios de estado.

**Motivos:**

1. **Auditabilidade:** o operador pode inspecionar, fazer backup e restaurar o
   estado diretamente no host, sem `docker cp` ou volumes-ls.
2. **Portabilidade:** o estado pode ser movido entre hosts com `rsync` ou `cp`.
3. **Configurabilidade:** o operador pode apontar `PIPE_STATE_DIR` para um
   volume NFS, SSD externo ou diretório customizado.
4. **Sem surpresas:** `docker compose down -v` não apaga o estado (ao contrário
   de named volumes, que são destruídos com `-v`).

**Consequência:** o operador é responsável pelo ciclo de vida dos diretórios
no host. Para reset completo, deve apagar manualmente os diretórios.

### Regra D-05: nunca montar `/app` inteiro

Montar `/app` como bind mount sobrescreveria o código da imagem com o
conteúdo do host. Os volumes de estado mapeiam **sempre subdiretórios**:
`/app/.pipe`, `/app/repo`, `/app/logs` — nunca `/app`.

### Defaults inline (H-2 — prevenção de erro)

As variáveis de ambiente têm valores padrão inline no compose:

```yaml
- ${PIPE_STATE_DIR:-./.pipe}:/app/.pipe
- ${PIPE_REPO_DIR:-./repo}:/app/repo
- ${PIPE_LOGS_DIR:-./logs}:/app/logs
```

Isso garante que o compose funciona mesmo sem `.env` (modo persistente por
default). O default "efêmero por engano" seria o pior caso — H-2 evita isso.

### Modo efêmero (opt-in)

Para CI ou testes isolados, `compose.ephemeral.yml` substitui os bind mounts
por volumes anônimos. O efêmero é **sempre explícito** — nunca o padrão.

---

## §5 — ADRs

### ADR-01 — Python 3.12-slim como base

Escolhida para imagem mínima (slim) com Python 3.12 correspondente ao requisito
da esteira. Sem `alpine` para evitar problemas de compatibilidade com `pyyaml`
e bibliotecas nativas.

### ADR-02 — Binário `gh` instalado na imagem

O `gh` CLI é baixado durante o build como binário oficial para a versão fixa
declarada. Evita dependência de repositório externo em runtime.

### ADR-03 — Chave SSH como arquivo montado (bind mount read-only)

A chave SSH é montada como arquivo read-only no container. Não é Docker secret
(formato Swarm) por simplicidade e compatibilidade com Compose standalone.
`PIPE_SSH_KEY_FILE` é declarado no `environment:` do compose (não no `.env`)
porque é um caminho interno determinado pela estrutura de montagem.

### ADR-04 — Bind mounts para estado de runtime

Ver §4. Named volumes foram considerados mas descartados por falta de
auditabilidade e risco de perda acidental com `down -v`.

### ADR-05 — `kiro-cli` copiado via `prepare-docker.sh`

O `kiro-cli` não é distribuído via repositório público. O script
`prepare-docker.sh` copia o binário do host para o contexto de build antes
do `docker build`.

---

## §6 — Variáveis de ambiente

| Variável | Obrigatória | Declarada em | Descrição |
|----------|-------------|-------------|-----------|
| `GH_TOKEN` | Sim | `.env` | Token de acesso ao GitHub |
| `PIPE_SSH_KEY_FILE` | Sim | `environment:` do compose | Caminho interno da chave SSH |
| `SSH_KEY_FILE` | Sim | `.env` | Caminho da chave SSH no host |
| `GH_CONFIG_DIR` | Não | `.env` | Diretório config do `gh` no host (default: `~/.config/gh`) |
| `PIPE_STATE_DIR` | Não | `.env` | Diretório de estado `.pipe/` no host (default: `./.pipe`) |
| `PIPE_REPO_DIR` | Não | `.env` | Diretório de clones `repo/` no host (default: `./repo`) |
| `PIPE_LOGS_DIR` | Não | `.env` | Diretório de logs no host (default: `./logs`) |
| `TZ` | Não | `environment:` | Fuso horário (default: `America/Sao_Paulo`) |
| `KIRO_LOG_NO_COLOR` | Não | `environment:` | Desabilita cor nos logs do kiro-cli |

---

## §7 — Segurança

- Nenhum segredo embutido na imagem ou no `docker-compose.yml`.
- `GH_TOKEN` e `SSH_KEY_FILE` lidos exclusivamente do `.env` (não versionado).
- `.env` listado no `.gitignore`.
- Chave SSH montada como read-only.
- Configuração do `gh` montada como read-only.

---

## §8 — Checklist de implementação (D-05)

- [ ] `docker-compose.yml` usa `${PIPE_STATE_DIR:-./.pipe}:/app/.pipe`
- [ ] `docker-compose.yml` usa `${PIPE_REPO_DIR:-./repo}:/app/repo`
- [ ] `docker-compose.yml` usa `${PIPE_LOGS_DIR:-./logs}:/app/logs`
- [ ] Named volumes `pipe_state`, `pipe_repos`, `pipe_logs` removidos
- [ ] Seção `volumes:` top-level do compose sem entradas para estado de runtime
- [ ] `.env.example` documenta `PIPE_STATE_DIR`, `PIPE_REPO_DIR`, `PIPE_LOGS_DIR`
- [ ] `compose.ephemeral.yml` criado com volumes anônimos
- [ ] `.gitignore` não bloqueia versionamento dos diretórios de estado (apenas os exclui do repositório da esteira)
- [ ] `docker compose config` valida sem erro com e sem `.env`
- [ ] `Dockerfile` declara `WORKDIR /app`
