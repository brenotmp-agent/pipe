# User Stories — Rodar no Docker

Status: draft
Owner: product (Helena Costa — Product Manager)
Last updated: 2026-07-06
Épico de origem: #1 "Rodar no Docker" (board `epic`)

## Inputs

- Issue #1 "Rodar no Docker" (board `epic`)
- doc/product/rodar-no-docker/{vision,problem-space,epicos}.md
- doc/requirements/rodar-no-docker/requisitos.md (RF-01..08, RNF-01..05, D-01..04)
- doc/architecture/rodar-no-docker/arquitetura.md (ADR-01..06, R-1..R-5)

---

## Objetivo

Quebrar o épico "Rodar no Docker" nas user stories mais pertinentes para
execução. Cada story é uma fatia de valor independente, testável e rastreável
aos requisitos e às decisões de arquitetura já aprovados. As stories são
sub-issues do épico #1 e residem no board **User Story** (`story`).

## Esclarecimento de escopo herdado (do produto)

"Sem a presença de um humano" = **operação autônoma do runtime**: o container
sobe e roda o loop sem setup manual do host nem prompts interativos. Os gates de
aprovação do fluxo (`need_human`) permanecem e são resolvidos pela ação humana
**diretamente no board do GitHub**; no ciclo seguinte a esteira sincroniza a
issue localmente e retoma. Nenhuma story abaixo remove esses gates.

---

## Mapa das stories

| # | Story | Épicos cobertos | Requisitos | Arquitetura | Nível |
|---|-------|-----------------|------------|-------------|-------|
| US-01 | Empacotar a esteira em imagem Docker | Imagem containerizada | RF-01, RNF-02, RNF-05, D-02 | ADR-02..06, R-2 | high |
| US-02 | Autenticar dependências externas em modo headless | Config/segredos por fora | RF-02, RF-03, RF-04, D-01, D-03 | ADR-01, ADR-02, ADR-03, R-1, R-3 | high |
| US-03 | Configurar a esteira via docker-compose sem rebuild | Config/segredos por fora | RF-05, RNF-01, RNF-03 | ADR-01..03 | medium |
| US-04 | Persistir estado de runtime entre reinícios | Config/segredos por fora | RF-06, D-04 | ADR-04 | low |
| US-05 | Operar de forma autônoma sem intervenção no runtime | Operação autônoma | RF-07, RNF-04 | ADR-05, ADR-06, R-4, R-5 | medium |
| US-06 | Documentar a operação em Docker | Documentação de operação | RF-08, D-04 | R-3, R-4 | medium |

### Ordem recomendada de execução

`US-01` (base) → `US-02` + `US-03` (credenciais e orquestração) → `US-04`
(persistência) → `US-05` (operação autônoma) → `US-06` (documentação, consolida
tudo). As dependências entre stories estão registradas nos artefatos abaixo; no
board só é possível declarar `/blocked_by` por id, então enquanto as stories não
tiverem id a ordem é mantida por esta documentação.

---

## US-01 — Empacotar a esteira em imagem Docker

**Como** analista/operador,
**quero** uma imagem Docker que contenha a esteira e todas as suas dependências
de runtime,
**para** executar `python -m src` em qualquer host com Docker, sem preparar a
máquina manualmente.

### Contexto

A esteira é uma app Python autocontida (`python -m src`, única dependência
`pyyaml`), mas hoje exige host preparado à mão. Esta story entrega o
empacotamento em si (Dockerfile), base da feature inteira.

### Critérios de aceitação

- **Dado** o `Dockerfile` na raiz, **quando** rodo `docker build`, **então** a
  imagem é gerada com base `python:3.12-slim` (RNF-02).
- A imagem contém, no PATH e com versões pinadas (RNF-05, D-02):
  `git`, `gh` (GitHub CLI), `kiro-cli`, `openssh-client`, `ca-certificates` e
  `pyyaml`.
- O código-fonte `src/` é copiado; `pipe.yml` e `contexts/` **não** são
  copiados (entram por volume — ver US-03).
- **Nenhum segredo** é copiado ou embutido na imagem (RNF-01).
- A imagem roda como **usuário não-root** com `$HOME` gravável (necessário para
  `_setup_ssh` escrever `~/.ssh` e para o estado de sessão do kiro-cli) — ADR-05.
- `PYTHONUNBUFFERED=1` definido, para logs em tempo real em `docker logs`.
- **Quando** executo o container, **então** `python -m src` inicia sem nenhuma
  instalação adicional no host (RF-01).

### Fora de escopo

Publicação em registry, CI/CD de build da imagem, injeção de credenciais
(US-02) e orquestração (US-03).

### Riscos / notas

- R-2: fixar método e versão de instalação do `kiro-cli`; validar
  `kiro-cli chat --no-interactive` na imagem.

---

## US-02 — Autenticar dependências externas em modo headless

**Como** operador,
**quero** fornecer as credenciais das três dependências externas (SSH, GitHub,
kiro-cli) por fora do container,
**para** que a esteira autentique e opere sem qualquer interação manual.

### Contexto

São três credenciais: chave SSH (git), `gh` (board) e `kiro-cli` (agente). A
arquitetura resolveu o único risco potencialmente bloqueador (D-01): o
`kiro-cli` autentica em modo headless oficial via `KIRO_API_KEY` (ADR-01).

### Critérios de aceitação

- **SSH (RF-02):** a chave privada é montada por volume **read-only** e
  `PIPE_SSH_KEY_FILE` aponta para o caminho interno; **então** `_setup_ssh` copia
  para `~/.ssh/id_pipe` e o clone via SSH funciona sem preparação manual (ADR-03).
- **gh (RF-03, D-03):** com `GH_TOKEN` injetado por env, `gh auth status`
  retorna sucesso dentro do container **sem** `gh auth login` (ADR-02).
- **kiro-cli (RF-04, D-01):** com `KIRO_API_KEY` injetado por env,
  `kiro-cli chat --no-interactive` executa sem prompt de login; `kiro-cli whoami`
  confirma o método ativo (ADR-01, R-3).
- **Continuidade de sessão (R-1):** validar que `--list-sessions` e
  `--resume-id` operam normalmente sob autenticação por API key; se não
  operarem, degradar para execução sem retomada **sem quebrar o loop**
  (documentar como débito).
- Nenhuma credencial fica embutida na imagem (RNF-01).

### Fora de escopo

O arquivo `docker-compose.yml` que declara essas credenciais é entregue em US-03
(esta story trata do mecanismo e da validação da autenticação em si).

### Riscos / notas

- R-3: `KIRO_API_KEY` exige assinatura Kiro Pro/Pro+/Pro Max/Power; contas
  gerenciadas por admin precisam de governança habilitando geração de keys.
  Pré-requisito a documentar em US-06.

---

## US-03 — Configurar a esteira via docker-compose sem rebuild

**Como** operador,
**quero** declarar toda a configuração e todos os segredos no `docker-compose`,
**para** trocar a configuração sem reconstruir a imagem e sem nada sensível
fixado nela.

### Contexto

Materializa a injeção externa: `pipe.yml`, `contexts/` e as três credenciais
entram via env/volumes declarados no compose (RF-05, RNF-01).

### Critérios de aceitação

- Existe um `docker-compose.yml` (ou `docker-compose.example.yml`) na raiz.
- Declara as envs: `GH_TOKEN`, `KIRO_API_KEY`, `PIPE_SSH_KEY_FILE`.
- Declara os volumes **read-only**: `pipe.yml`, `contexts/` e a chave SSH.
- Os segredos vêm de `.env`/secret externo — **nada** sensível é versionado
  nem embutido na imagem (RNF-01).
- **Quando** rodo `docker compose up` com configurações distintas, **então** a
  esteira sobe funcionando **sem rebuild** da imagem (RF-05).
- O compose funciona no formato `docker compose` V2 (RNF-03).

### Fora de escopo

Persistência de estado (US-04) e política de restart/operação autônoma (US-05),
tratadas em stories próprias, embora convivam no mesmo arquivo compose.

---

## US-04 — Persistir estado de runtime entre reinícios

**Como** operador,
**quero** persistir `.pipe/`, `logs/` e `repo/` via volumes,
**para** preservar snapshots, fila, sessões e clones entre reinícios do
container.

### Contexto

Esses diretórios acumulam estado entre ciclos. A persistência é **opcional por
design** (ADR-04); a recomendação é persistir `.pipe/` (evita re-sync e preserva
continuidade de raciocínio do agente) e `repo/` (evita re-clone); `logs/` é
conveniência.

### Critérios de aceitação

- O compose permite montar `.pipe/`, `logs/` e `repo/` como volumes.
- **Dado** que os volumes estão configurados, **quando** executo
  `docker compose down && docker compose up`, **então** o estado anterior é
  preservado (RF-06).
- Os binds são opcionais: removê-los resulta em operação efêmera (estado zerado
  a cada `up`) sem erro (D-04).

### Fora de escopo

Estratégia de backup dos volumes; multi-instância.

---

## US-05 — Operar de forma autônoma sem intervenção no runtime

**Como** analista,
**quero** que o container rode o loop principal ininterruptamente, sem prompts e
com falha clara em erro de setup,
**para** operar a esteira sem precisar acessar a máquina hospedeira.

### Contexto

O código já é adequado à operação headless; esta story garante e verifica o
comportamento autônomo, reaproveitando `check_config` (fail-fast) e a política
de restart do compose. Sem alteração de lógica de negócio (RNF-04, ADR-06).

### Critérios de aceitação

- Nenhuma etapa do ciclo (startup, clone, sync, agente) aguarda `stdin`; o
  `kiro-cli` é chamado com `--no-interactive` (RF-07).
- **Quando** falta uma credencial/config, **então** `check_config` faz
  fail-fast com exit-code != 0 e mensagem clara — sem travamento silencioso
  (RF-07).
- `restart: unless-stopped` mantém o loop rodando após crash duro (ADR-05).
- Logs aparecem em tempo real em `docker logs` (`PYTHONUNBUFFERED=1`).
- O gate `need_human` é resolvido pela ação humana **no board do GitHub**; o
  container permanece rodando e retoma no ciclo seguinte (comportamento
  verificado, não removido).

### Fora de escopo

Remoção de qualquer gate de aprovação do fluxo; observabilidade avançada
(métricas/alertas).

### Riscos / notas

- R-4: revogação/rotação/expiração da `KIRO_API_KEY` interrompe as chamadas do
  agente → procedimento de rotação documentado em US-06 e erros visíveis no log.
- R-5: `StrictHostKeyChecking no` no `_setup_ssh` é decisão consciente
  (aceitável para github.com).

---

## US-06 — Documentar a operação em Docker

**Como** usuário novo (sem conhecimento do código),
**quero** um guia simples e completo,
**para** colocar a esteira para rodar em Docker seguindo apenas a documentação.

### Contexto

Consolida a operação de ponta a ponta. Depende das definições das stories
anteriores estarem materializadas (Dockerfile, compose, credenciais,
persistência).

### Critérios de aceitação

O guia (no repositório) cobre:

1. **Pré-requisitos no host:** Docker + `docker compose` V2; assinatura Kiro
   Pro/Pro+/Pro Max/Power e (se conta gerenciada) governança de admin para gerar
   `KIRO_API_KEY` (R-3); token do GitHub; chave SSH.
2. **Estrutura do `docker-compose.yml`** com todos os parâmetros (envs, volumes,
   `.env`).
3. **Comando para subir:** `docker compose up`.
4. **Como verificar que está rodando:** log output esperado (ciclo do loop).
5. **Parar e reiniciar preservando estado** (volumes de US-04).
6. **Rotação da `KIRO_API_KEY`** (atualizar env + restart) — R-4.

- **Critério de sucesso:** um usuário sem conhecimento prévio do código coloca a
  esteira para rodar seguindo apenas o guia (RF-08, métrica de sucesso da
  vision).

### Fora de escopo

Documentação interna da arquitetura Docker (já coberta em
`doc/architecture/rodar-no-docker/arquitetura.md`).

---

## Rastreabilidade — cobertura dos requisitos

| Requisito | Story(ies) |
|-----------|------------|
| RF-01 | US-01 |
| RF-02 | US-02 |
| RF-03 | US-02 |
| RF-04 | US-02 |
| RF-05 | US-03 |
| RF-06 | US-04 |
| RF-07 | US-05 |
| RF-08 | US-06 |
| RNF-01 | US-01, US-02, US-03 |
| RNF-02 | US-01 |
| RNF-03 | US-03 |
| RNF-04 | US-05 |
| RNF-05 | US-01 |

Todos os RF (01–08) e RNF (01–05) estão cobertos por ao menos uma story.
