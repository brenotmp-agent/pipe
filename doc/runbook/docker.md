# Runbook — Operação Docker da Esteira Agêntica

> Status: **estável** — validado contra Dockerfile e docker-compose.yml reais (v0.1.0)
>
> US-06 (#21) | RF-08 | D-04 | R-3, R-4

---

## Antes de começar — Checklist de pré-requisitos

Antes de executar qualquer comando, confirme que você tem:

| Pré-requisito | Como verificar |
|---------------|----------------|
| **Docker Engine** com **Docker Compose V2** (comando `docker compose`, sem hífen) | `docker compose version` → deve mostrar v2.x ou superior |
| **Chave SSH** (`~/.ssh/id_ed25519` ou equivalente) registrada no GitHub | `ssh -T git@github.com` → `Hi <usuário>!` |
| **GH_TOKEN** — token do GitHub com escopos `repo` e `project` | [github.com/settings/tokens](https://github.com/settings/tokens) |
| **KIRO_API_KEY** — chave de API do kiro-cli | Obtida junto ao time ou painel de administração do kiro-cli |

> **Segurança:** o arquivo `.env` contém segredos e já está no `.gitignore` — **nunca o versione**.

---

## Quickstart (TL;DR)

Para quem já tem todos os pré-requisitos atendidos:

```bash
# 1. Clonar o repositório
git clone git@github.com:<org>/pipe.git && cd pipe

# 2. Criar o .env a partir do exemplo
cp .env.example .env
# Edite .env e preencha: GH_TOKEN, KIRO_API_KEY, SSH_KEY_FILE_HOST (e as demais variáveis)

# 3. Criar o pipe.yml com a configuração da esteira
cp pipe.yml.example pipe.yml  # ou criar manualmente conforme README

# 4. Construir a imagem
docker compose build

# 5. Subir a esteira em background
docker compose up -d
```

Após o `up`, verifique os logs conforme a [seção de verificação](#verificação-de-saúde).

---

## Passo a passo detalhado

### Passo 1 — Clonar o repositório

```bash
git clone git@github.com:<org>/pipe.git
cd pipe
```

A chave SSH deve estar registrada no GitHub e acessível em `~/.ssh/id_ed25519`
(ou no caminho que você configurará em `SSH_KEY_FILE_HOST`).

---

### Passo 2 — Criar o arquivo `.env`

Copie o arquivo de exemplo e preencha os valores:

```bash
cp .env.example .env
```

Conteúdo mínimo obrigatório (consulte `.env.example` para comentários completos):

```dotenv
# Token do GitHub (escopos: repo, project)
GH_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Caminho absoluto da chave SSH no host (para operações git)
SSH_KEY_FILE=~/.ssh/id_ed25519

# Diretório de configuração do gh CLI no host
GH_CONFIG_DIR=~/.config/gh

# Diretórios de estado da esteira no host (defaults ao lado do compose)
PIPE_STATE_DIR=./.pipe
PIPE_REPO_DIR=./repo
PIPE_LOGS_DIR=./logs

# Caminho da chave SSH no HOST — alimenta o Docker secret (montada em /run/secrets/ssh_key)
SSH_KEY_FILE_HOST=~/.ssh/id_ed25519

# Chave de API do kiro-cli
KIRO_API_KEY=
```

> **Nota:** `PIPE_SSH_KEY_FILE` é definido fixamente pelo compose como
> `/run/secrets/ssh_key` — não defina essa variável no `.env`.
>
> **Segurança:** `.env` está no `.gitignore` e nunca deve ser versionado.

---

### Passo 3 — Criar o `pipe.yml`

A esteira precisa de um `pipe.yml` configurado na raiz do repositório. Consulte o
`README.md` para a estrutura completa. O arquivo é montado como volume somente-leitura
no container — alterar o `pipe.yml` no host e executar `docker compose up -d` aplica
a nova configuração **sem necessidade de rebuild da imagem**.

---

### Passo 4 — Construir a imagem

O Dockerfile usa **BuildKit** com a instrução `--secret` para passar a chave SSH
durante o build sem gravá-la na imagem:

```bash
docker compose build
```

O `docker compose build` ativa o BuildKit automaticamente e passa o Docker secret
configurado no `docker-compose.yml`. A chave SSH nunca persiste em nenhuma camada
da imagem.

Para build manual (fora do compose), o comando equivalente é:

```bash
DOCKER_BUILDKIT=1 docker build \
  --secret id=ssh_key,src="$PIPE_SSH_KEY_FILE" \
  --build-arg PIPE_REF=main \
  -t esteira .
```

---

### Passo 5 — Subir a esteira

```bash
docker compose up -d
```

O container sobe em background. O serviço se chama `pipe` conforme declarado no
`docker-compose.yml`. A política `restart: unless-stopped` faz com que o container
**reinicie automaticamente** após crash ou reboot do host, parando apenas com um
`docker compose stop` ou `docker compose down` explícito.

---

## Verificação de saúde

Após o `docker compose up -d`, confirme que a esteira iniciou corretamente:

```bash
docker compose logs pipe -f
```

Saída esperada no arranque bem-sucedido (em ordem cronológica):

```
[Config]   Validando pipe.yml
[Config]   pipe.yml válido
[Startup]  Verificando repositórios
[Startup]  Clonando <repo_id>
[Board]    Sincronizando estrutura local
[Board]    Sincronizando boards remotos
[Board]    Detectando mudanças remotas
[Sleep]    Nenhuma atividade - dormindo 60s (retorna às ...)
```

Se o `.env` estiver incompleto (ex.: `GH_TOKEN` vazio), a esteira termina com
erro descritivo em `[Config]` — nunca trava silenciosamente.

Para ver os últimos 50 registros sem seguir o stream:

```bash
docker compose logs pipe --tail=50
```

Para ver o estado atual do container:

```bash
docker compose ps
```

---

## Estrutura do compose — O que cada parte faz

O `docker-compose.yml` organiza a esteira com os seguintes elementos:

### Serviço `pipe`

- **`env_file: .env`** — todas as variáveis do `.env` são injetadas no container.
- **`environment: PIPE_SSH_KEY_FILE=/run/secrets/ssh_key`** — o caminho interno da chave
  SSH é fixo (determinado pelo compose, não pelo operador). O operador configura apenas
  `SSH_KEY_FILE_HOST` no `.env`.
- **`restart: unless-stopped`** — reinício automático após crash ou reboot do host;
  para com `docker compose stop` ou `docker compose down`.

### Volumes nomeados (persistência de estado)

| Volume | O que armazena | Impacto de perder |
|--------|----------------|-------------------|
| `pipe-state` | Snapshots de boards, sessões de agente, throttle (`.pipe/`) | Re-sync completo + perda de raciocínio contínuo dos agentes |
| `pipe-repo` | Clones git dos repositórios configurados (`repo/`) | Re-clone de todos os repositórios |
| `pipe-logs` | Histórico de execução (`logs/`) | Só perde histórico; operação segue normal |
| `kiro-home` | Configuração do kiro-cli (`~/.kiro/`) | Re-autenticação / re-configuração do kiro-cli |
| `kiro-local` | Dados locais do kiro-cli (`~/.local/share/kiro-cli/`) | Regenerados automaticamente |

### Docker secret SSH

```yaml
secrets:
  ssh_key:
    file: ${SSH_KEY_FILE_HOST}   # caminho NO HOST, fornecido via .env
```

A chave SSH é montada em `/run/secrets/ssh_key` dentro do container (modo `0400`).
O `PIPE_SSH_KEY_FILE` no container aponta fixamente para esse caminho.

---

## Parar, reiniciar e gerenciar o container

### Parar temporariamente (preserva o estado)

```bash
docker compose stop
```

Para o container **sem remover** os volumes nomeados. Todos os dados de estado
(`pipe-state`, `pipe-repo`, `pipe-logs`) são preservados. Para retomar:

```bash
docker compose start
```

Ou para recriar e reiniciar:

```bash
docker compose up -d
```

### Reiniciar o container

```bash
docker compose restart
```

Reinicia o serviço `pipe` sem destruir o estado.

### Parar e remover containers (preserva volumes)

```bash
docker compose down
```

Remove o container e a rede, mas **mantém todos os volumes nomeados**. O estado
da esteira (sessões de agente, snapshots, logs) fica intacto. `docker compose up -d`
na próxima vez retoma de onde parou.

### Parar e destruir tudo (incluindo estado)

```bash
docker compose down -v
```

Remove o container, a rede **e todos os volumes nomeados** (`pipe-state`, `pipe-repo`,
`pipe-logs`, `kiro-home`, `kiro-local`). Use apenas quando quiser um recomeço
completamente limpo — **toda a continuidade de raciocínio dos agentes, snapshots
e histórico de logs serão perdidos**.

---

## Rotação da `KIRO_API_KEY`

Quando a chave de API do kiro-cli expirar ou precisar ser trocada:

1. **Obtenha a nova chave** junto ao time ou painel de administração.

2. **Edite o `.env`** na raiz do repositório e substitua o valor de `KIRO_API_KEY`:

   ```bash
   # Abra o .env com seu editor preferido e atualize:
   KIRO_API_KEY=<nova_chave>
   ```

3. **Reinicie o container** para aplicar a nova chave (a variável de ambiente é
   lida na inicialização):

   ```bash
   docker compose restart
   ```

   Ou, para garantir recreação completa do container:

   ```bash
   docker compose up -d
   ```

4. **Confirme** que a esteira voltou a operar normalmente verificando os logs:

   ```bash
   docker compose logs pipe --tail=20
   ```

   A saída esperada é o fluxo normal de `[Config]` → `[Startup]` → `[Board]`.

---

## Referências

- `Dockerfile` — imagem da esteira (BuildKit secret, usuário `pipe`, PYTHONUNBUFFERED)
- `docker-compose.yml` — serviço `pipe`, volumes nomeados, Docker secret SSH
- `.env.example` — modelo de variáveis de ambiente com comentários detalhados
- `docker/versions.env` — versões pinadas dos pacotes (ADR-04)
- `README.md` — estrutura da esteira e configuração do `pipe.yml`
- `doc/product/rodar-no-docker/` — decisões de produto e arquitetura (US-03 a US-06)
- `CONTEXT.md` — decisões técnicas e estado atual do projeto
