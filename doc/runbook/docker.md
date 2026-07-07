# Runbook — Rodar a esteira em Docker

> **Público:** analista/operador sem conhecimento prévio do código.
> Seguindo este guia do início ao fim você coloca a esteira funcionando
> em qualquer host com Docker.
>
> ⏱ **Tempo estimado:** ~15 minutos (fora o tempo de build da imagem, que
> acontece uma única vez).

---

## Conteúdo

1. [Antes de começar](#antes-de-começar) — pré-requisitos e credenciais a reunir
2. [Quickstart (TL;DR)](#quickstart-tldr) — para quem já tem as credenciais
3. [Passo a passo de subida](#passo-a-passo-de-subida)
4. [Como verificar que está rodando](#como-verificar-que-está-rodando)
5. [Parar e reiniciar](#parar-a-esteira)
6. [Rotação da KIRO_API_KEY](#rotação-da-kiro_api_key)
7. [Referências](#referências)

---

## Antes de começar

### O que você precisa saber

Este guia assume que você sabe abrir um terminal, editar um arquivo de texto e
rodar comandos. **Não** exige conhecimento do código da esteira nem de
arquitetura Docker — cada passo traz o comando exato e o resultado esperado.

### Pré-requisitos no host

| Requisito | Verificação |
|-----------|-------------|
| Docker Engine + plugin `docker compose` V2 | `docker compose version` → `Docker Compose version v2.x` |
| Git | `git --version` |

> **Nota:** o comando é `docker compose` (com espaço, plugin V2), não
> `docker-compose` (com hífen, versão legada descontinuada).

### Credenciais necessárias

Você precisa ter em mãos, antes de começar. Use este checklist para não travar
no meio do processo:

- [ ] **Chave SSH privada** cadastrada no GitHub (clone dos repositórios)
- [ ] **`GH_TOKEN`** — Personal Access Token do GitHub (escopos `repo` e `project`)
- [ ] **`KIRO_API_KEY`** — API key do Kiro (requer plano Pro ou superior)

> ⚠ **Conta Kiro gerenciada por administrador (R-3):** se sua conta é
> corporativa/gerenciada, o administrador precisa **habilitar a geração de API
> keys** antes que você consiga criar a `KIRO_API_KEY`. Verifique isso já, pois
> é o ponto mais comum de bloqueio.

#### 1. Chave SSH privada (para clone de repositórios via SSH)

A esteira clona os repositórios via SSH. A chave precisa estar cadastrada
no GitHub da conta que tem acesso ao(s) repositório(s) configurado(s) no
`pipe.yml`.

- Se você ainda não tem uma chave SSH, gere com:
  ```bash
  ssh-keygen -t ed25519 -C "pipe-esteira"
  ```
- Adicione a chave pública em: `github.com → Settings → SSH and GPG keys`.

#### 2. GitHub Personal Access Token — `GH_TOKEN`

O token é usado pelo `gh` CLI para acessar o GitHub Projects V2 (board).

- Gere em: `github.com → Settings → Developer settings → Personal access tokens → Tokens (classic)`.
- Escopos obrigatórios: **`repo`** e **`project`**.
- Guarde o valor — ele não é exibido novamente.

#### 3. Kiro API Key — `KIRO_API_KEY`

A API key autentica o `kiro-cli` em modo headless (sem browser).

- **Requer plano Kiro Pro, Pro+, Pro Max ou Power.**
- Gere em: `app.kiro.dev → Settings → API Keys → Generate`.
- Em contas gerenciadas por administrador: o admin precisa habilitar a
  geração de API keys antes que você consiga criá-la. Consulte seu
  administrador Kiro. Referência:
  [kiro.dev/docs/cli/enterprise/governance/api-keys](https://kiro.dev/docs/cli/enterprise/governance/api-keys/).
- Guarde o valor — ele não é exibido novamente.

---

## Quickstart (TL;DR)

> Para quem **já tem** as três credenciais em mãos (SSH, `GH_TOKEN`,
> `KIRO_API_KEY`) e só quer subir. Se é sua primeira vez, pule para o
> [passo a passo detalhado](#passo-a-passo-de-subida).

```bash
# 1. Clonar e entrar no repositório
git clone git@github.com:<seu-usuario>/pipe.git && cd pipe

# 2. Criar o .env e preencher os 3 segredos (SSH_KEY_FILE_HOST, GH_TOKEN, KIRO_API_KEY)
cp .env.example .env
${EDITOR:-nano} .env

# 3. Ajustar pipe.yml e o contexto do agente (contexts/kiro-cli/dev.md)

# 4. Construir e subir
docker compose build
docker compose up -d

# 5. Acompanhar o arranque
docker compose logs -f
```

Loop rodando sem erros nas primeiras linhas = sucesso. Detalhes de cada passo e
como verificar a saúde estão nas seções abaixo.

---

## Passo a passo de subida

### 1. Clonar o repositório

```bash
git clone git@github.com:<seu-usuario>/pipe.git
cd pipe
```

### 2. Criar o arquivo `.env`

Copie o exemplo e preencha com os seus valores:

```bash
cp .env.example .env
```

Edite `.env`:

```dotenv
# Caminho da chave SSH privada no host (será montada como Docker secret)
SSH_KEY_FILE_HOST=~/.ssh/id_ed25519

# Personal Access Token do GitHub (escopos: repo, project)
GH_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# API key do kiro-cli (requer plano Pro ou superior)
KIRO_API_KEY=kiro_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> **Atenção:** o `.env` nunca deve ser commitado. Ele já está no `.gitignore`.

### 3. Preparar a configuração da esteira

Crie (ou ajuste) o `pipe.yml` na raiz do repositório. Consulte o
`README.md` para a estrutura completa. Exemplo mínimo:

```yaml
sleep: 60

git:
  repo:
    main: git@github.com:<seu-usuario>/<seu-repo>.git
  flow:
    base: main

agents:
  kiro-cli:
    dev:
      name: engineering
      model: claude-sonnet-4-20250514

boards:
  platform: github
  backlog:
    name: Backlog
    columns:
      todo:
        name: To Do
      doing:
        name: Doing
        agent: dev
        change:
          advance: done
      done:
        name: Done
        archive: true
```

Crie também o diretório de contextos (preenchido com o papel do agente):

```bash
mkdir -p contexts/kiro-cli
# Edite o arquivo com o contexto/persona do agente:
nano contexts/kiro-cli/dev.md
```

### 4. Construir a imagem

```bash
docker compose build
```

Aguarde a conclusão. O processo instala todas as dependências (Python, Git,
`gh` CLI, `kiro-cli`, PyYAML) dentro da imagem.

### 5. Subir a esteira

```bash
docker compose up -d
```

O container inicia em background. Passe para a próxima seção para verificar
que está rodando corretamente.

---

## Como verificar que está rodando

### Status do container

```bash
docker compose ps
```

Saída esperada:

```
NAME   IMAGE        COMMAND           STATUS    PORTS
pipe   pipe:latest  "python -m src"   Up X min
```

### Acompanhar os logs em tempo real

```bash
docker compose logs -f
```

Nas primeiras linhas você verá a sequência de inicialização. Exemplo de
saída esperada de um arranque bem-sucedido:

```
[Config] Validando pipe.yml
[Config] pipe.yml válido
[Startup] Verificando repositórios
[Startup] Clonando main
[Board] Sincronizando estrutura local
[Board] Sincronizando boards remotos
[Board] 0 mudança(s) remota(s) adicionada(s) à fila
[Main] Dormindo 60 segundos
```

O ciclo `[Board] Sincronizando…` → `[Main] Dormindo N segundos` repete
indefinidamente enquanto a esteira estiver ociosa. Quando há tarefas,
você verá linhas de `[Agent]` e `[KeepTask]` no lugar do sleep.

### Sinais de problema no arranque

| Mensagem nos logs | Causa | Solução |
|-------------------|-------|---------|
| `Variável de ambiente 'PIPE_SSH_KEY_FILE' não definida` | `.env` sem `PIPE_SSH_KEY_FILE` | Preencher `.env` |
| `Arquivo SSH não encontrado: /run/secrets/ssh_key` | Docker secret não montado | Verificar `SSH_KEY_FILE_HOST` no `.env` |
| `pipe.yml não encontrado` | Volume do `pipe.yml` não montado | Verificar `docker-compose.yml` e se o arquivo existe |
| `Arquivos de contexto vazios` | `contexts/kiro-cli/dev.md` vazio | Preencher o arquivo de contexto |

---

## Parar a esteira

### Parar preservando o estado (recomendado)

```bash
docker compose down
```

Os volumes nomeados (`pipe-repo`, `pipe-logs`, `pipe-state`, `kiro-home`)
são **preservados**. Ao subir novamente com `docker compose up -d`:

- A fila de mudanças, snapshots e sessões são retomados de onde pararam.
- Os clones dos repositórios permanecem (sem re-clone).
- O histórico de sessões do kiro-cli é mantido (continuidade de raciocínio
  dos agentes).

### ⛔ Destruir o estado (reset completo)

> **AÇÃO IRREVERSÍVEL.** O comando abaixo apaga **todo o estado** da esteira.
> Use apenas se quiser realmente começar do zero.

```bash
docker compose down -v
```

O flag `-v` remove **todos os volumes nomeados**. Na próxima subida, a esteira
parte do zero (re-clona repositórios, recria snapshots, inicia novas sessões de
agente — perdendo a continuidade de raciocínio dos agentes).

---

## Rotação da KIRO_API_KEY

A documentação oficial do kiro-cli recomenda rotação periódica de API keys.
Procedimento sem perda de continuidade:

1. Gere uma **nova** API key em `app.kiro.dev → Settings → API Keys`.
   A chave antiga permanece válida durante a troca.

2. Atualize `KIRO_API_KEY` no arquivo `.env` do host com o novo valor.

3. Reinicie o container (sem rebuild):
   ```bash
   docker compose up -d
   ```

4. Verifique nos logs que a esteira subiu normalmente (mesma sequência
   de inicialização descrita acima).

5. Revogue a chave antiga em `app.kiro.dev → Settings → API Keys → Revoke`.

> O estado da esteira (volumes) não é afetado pela rotação — sessões,
> snapshots e histórico são preservados.

---

## Referências

- [README.md](../../README.md) — estrutura do `pipe.yml` e configuração geral
- [kiro.dev/docs/cli/headless](https://kiro.dev/docs/cli/headless/) — modo headless do kiro-cli
- [cli.github.com/manual/gh_help_environment](https://cli.github.com/manual/gh_help_environment) — `GH_TOKEN`
- [kiro.dev/docs/cli/enterprise/governance/api-keys](https://kiro.dev/docs/cli/enterprise/governance/api-keys/) — governança de API keys em contas administradas
