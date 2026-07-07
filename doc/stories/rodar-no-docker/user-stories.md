# User Stories — Rodar no Docker

Status: draft
Owner: requirements
Last updated: 2026-07-07

## Inputs

- Issue #1 "Rodar no Docker"
- `doc/product/rodar-no-docker/vision.md`
- `doc/product/rodar-no-docker/problem-space.md`
- `doc/product/rodar-no-docker/epicos.md`
- `doc/requirements/rodar-no-docker/requisitos.md`
- `doc/architecture/rodar-no-docker/arquitetura.md`
- `src/__main__.py`, `src/core/config.py`, `src/adapters/kiro_cli_agent.py`

---

## Mapa de cobertura RF/RNF por story

| Requisito | US-01 | US-02 | US-03 | US-04 | US-05 | US-06 |
|-----------|:-----:|:-----:|:-----:|:-----:|:-----:|:-----:|
| RF-01 | ✓ | | | | | |
| RF-02 | | ✓ | | | | |
| RF-03 | | ✓ | | | | |
| RF-04 | | ✓ | | | | |
| RF-05 | | | ✓ | | | |
| RF-06 | | | | ✓ | | |
| RF-07 | | | | | ✓ | |
| RF-08 | | | | | | ✓ |
| RNF-01 | ✓ | ✓ | ✓ | | | |
| RNF-02 | ✓ | | | | | |
| RNF-03 | | | ✓ | | | |
| RNF-04 | | | | | ✓ | |
| RNF-05 | ✓ | | | | | |

---

## Ordem recomendada de execução

US-01 → US-02 + US-03 → US-04 → US-05 → US-06

Justificativa: US-01 entrega a imagem-base; US-02 e US-03 podem ser paralelas
(credenciais e compose são complementares). US-04 depende do compose. US-05
só faz sentido quando a imagem, as credenciais e o compose existem (precisa
verificar o loop rodando). US-06 é última, quando tudo está materializado.

---

## Desambiguação: "operação autônoma" não significa ausência de gates humanos

O esclarecimento a seguir é central para todas as stories e foi confirmado com
o negócio: "sem a presença de um humano" refere-se à **operação autônoma do
runtime** — o container sobe e roda o loop principal sem setup manual do host
nem prompts interativos. Os gates de aprovação do fluxo (`need_human`: Aprovação
de Negócio, Validação Negocial, Validação Arquitetural, Homologação) **não são
removidos**. A intervenção humana nesses pontos ocorre **diretamente no board do
GitHub** (o humano move o card no site); no ciclo seguinte a esteira sincroniza
a issue localmente e retoma o trabalho. O container permanece rodando
ininterruptamente enquanto aguarda.

---

## US-01 — Empacotar a esteira em imagem Docker

**Issue:** #16 (board `story`)
**Rastreabilidade:** RF-01, RNF-01, RNF-02, RNF-05, D-02; ADR-05, ADR-06; R-2

**Como** analista/operador,
**quero** uma imagem Docker que contenha a esteira e todas as suas dependências
de runtime,
**para** executar `python -m src` em qualquer host com Docker, sem preparar a
máquina manualmente.

### Escopo desta story

Esta story entrega **apenas o empacotamento** (Dockerfile): o que está dentro
da imagem, como é construída e o que ela carrega. Não cobre injeção de
credenciais (US-02), composição do docker-compose (US-03) nem política de
restart (US-05). A imagem produzida aqui é a fundação que as demais stories
consomem.

### Critérios de aceitação

| # | Critério |
|---|---------|
| AC-01 | `docker build` conclui sem erro e gera imagem funcional (base `python:3.12-slim`, RNF-02). |
| AC-02 | A imagem contém no PATH, com versões pinadas: `git`, `gh` (GitHub CLI), `kiro-cli`, `openssh-client`, `ca-certificates`, `python` e `pyyaml` (RNF-05, D-02). |
| AC-03 | `src/` está copiado para a imagem; `pipe.yml` e `contexts/` **não** estão — entram por volume em runtime (RF-05). |
| AC-04 | Nenhum segredo (token, chave SSH, API key) embutido na imagem (RNF-01). |
| AC-05 | O container roda como usuário não-root com `$HOME` gravável — necessário para `_setup_ssh` escrever `~/.ssh/id_pipe` e para o estado de sessão do kiro-cli (ADR-05). |
| AC-06 | `PYTHONUNBUFFERED=1` definido na imagem, para que os logs apareçam em tempo real em `docker logs`. |
| AC-07 | Executando apenas `docker run <imagem>` sem variáveis de ambiente, a esteira falha em `check_config` com mensagem clara e exit-code != 0 (sem travar silenciosamente — RF-07 parcial). |

### Fora de escopo

Publicação em registry, CI/CD de build, injeção de credenciais (US-02) e
orquestração via compose (US-03).

### Notas / riscos

- **R-2**: fixar método e versão de instalação do `kiro-cli` no Dockerfile e
  validar `kiro-cli chat --no-interactive` dentro da imagem construída.

---

## US-02 — Autenticar dependências externas em modo headless

**Issue:** #17 (board `story`)
**Rastreabilidade:** RF-02, RF-03, RF-04, D-01, D-03; ADR-01, ADR-02, ADR-03;
R-1, R-3

**Como** operador,
**quero** fornecer as credenciais das três dependências externas (SSH, GitHub,
kiro-cli) por fora do container,
**para** que a esteira autentique e opere sem qualquer interação manual.

### Escopo desta story

Cobre o **mecanismo de autenticação** de cada uma das três dependências e a
**validação** de que cada uma funciona em modo headless. Não cobre a declaração
dessas credenciais no docker-compose (responsabilidade de US-03).

### Diferença em relação a US-01

US-01 entrega a imagem com os binários instalados. US-02 responde à pergunta:
"dado que a imagem existe, como cada dependência **autentica** sem prompt?" São
camadas distintas: empacotamento (US-01) vs. autenticação (US-02).

### Credenciais e mecanismo

| Credencial | Mecanismo | Referência |
|-----------|-----------|------------|
| **SSH** (git) | Chave privada montada como volume ro; `PIPE_SSH_KEY_FILE` aponta para o caminho interno; `_setup_ssh` copia para `~/.ssh/id_pipe`. | ADR-03 |
| **gh CLI** (board) | `GH_TOKEN` como variável de ambiente — suporte nativo do `gh`; nenhum `gh auth login` necessário. | ADR-02 |
| **kiro-cli** (agente) | `KIRO_API_KEY` como variável de ambiente — modo headless oficial do kiro-cli. | ADR-01 |

### Critérios de aceitação

| # | Critério |
|---|---------|
| AC-01 | Com `PIPE_SSH_KEY_FILE` apontando para a chave montada (volume ro), `_setup_ssh` copia para `~/.ssh/id_pipe` e um `git clone` via SSH funciona sem interação (RF-02). |
| AC-02 | Com `GH_TOKEN` definido, `gh auth status` retorna sucesso dentro do container **sem** nenhum `gh auth login` (RF-03, ADR-02, D-03). |
| AC-03 | Com `KIRO_API_KEY` definido, `kiro-cli chat --no-interactive` executa com sucesso e `kiro-cli whoami` confirma autenticação por API key (RF-04, ADR-01, D-01). |
| AC-04 | `--list-sessions` e `--resume-id` operam normalmente sob `KIRO_API_KEY`; se não, a esteira degrada para execução sem retomada de sessão sem quebrar o loop (R-1). |
| AC-05 | Nenhuma credencial embutida na imagem (RNF-01). |
| AC-06 | `check_config()` valida apenas `PIPE_SSH_KEY_FILE` no startup; `GH_TOKEN` e `KIRO_API_KEY` falham na primeira operação com log claro (comportamento intencional — validação lazy). Os três devem ser pré-requisitos no runbook (US-06). |

### Pré-requisito externo

A `KIRO_API_KEY` está disponível apenas para assinantes Kiro Pro, Pro+, Pro Max
ou Power. Contas gerenciadas por administrador requerem que a governança habilite
a geração de API keys. Documentar como pré-requisito em US-06 (R-3).

### Fora de escopo

O `docker-compose.yml` que declara as credenciais é responsabilidade de US-03;
aqui tratamos do mecanismo e da validação da autenticação em si.

---

## US-03 — Configurar a esteira via docker-compose sem rebuild

**Issue:** #18 (board `story`)
**Rastreabilidade:** RF-05, RNF-01, RNF-03; ADR-01, ADR-02, ADR-03

**Como** operador,
**quero** declarar toda a configuração e todos os segredos no `docker-compose`,
**para** trocar a configuração sem reconstruir a imagem e sem nada sensível
fixado nela.

### Escopo desta story

Entrega o arquivo `docker-compose.yml` (ou `docker-compose.example.yml`) que
orquestra a injeção de configuração e credenciais. Não cobre política de
restart/operação autônoma (US-05) nem persistência de estado (US-04), embora
esses elementos possam conviver no mesmo arquivo.

### Critérios de aceitação

| # | Critério |
|---|---------|
| AC-01 | Existe `docker-compose.yml` (ou `docker-compose.example.yml`) na raiz do repositório. |
| AC-02 | O compose declara as envs: `GH_TOKEN`, `KIRO_API_KEY`, `PIPE_SSH_KEY_FILE`. |
| AC-03 | O compose declara os volumes **read-only**: `pipe.yml`, `contexts/` e a chave SSH. Segredos vêm de `.env` externo — nada sensível versionado nem embutido na imagem (RNF-01). |
| AC-04 | `docker compose up` com configurações distintas sobe a esteira funcionando **sem rebuild** (RF-05). |
| AC-05 | O compose usa o formato `docker compose` V2 (plugin, sem hífen — RNF-03). |

### Fora de escopo

Persistência de estado (US-04) e política de restart/operação autônoma (US-05),
tratadas em stories próprias, embora possam conviver no mesmo arquivo compose.

---

## US-04 — Persistir estado de runtime entre reinícios

**Issue:** #19 (board `story`)
**Rastreabilidade:** RF-06, D-04; ADR-04

**Como** operador,
**quero** persistir `.pipe/`, `logs/` e `repo/` via volumes,
**para** preservar snapshots, fila de mudanças, sessões de agente e clones de
repositório entre reinícios do container.

### Escopo desta story

Cobre a **camada de persistência opcional** — volumes nomeados ou bind mounts
para os três diretórios de estado. A persistência é opcional por design
(ADR-04): remover os binds resulta em operação efêmera (estado zerado a cada
`up`) sem erro.

### Por que persistir `.pipe/`

`.pipe/` contém:
- `snapshot.json` por board (evita re-sync completo a cada restart)
- `changeQueue.json` (recuperação de crash — itens pendentes são re-enfileirados)
- `sessions.json` (índice de sessões: preserva a continuidade de raciocínio do
  agente entre reinícios; sem persistência, o `SessionIndex` perde os IDs e o
  agente começa do zero a cada `up`)
- `throttle` (estado do throttle de rate limit)

### Critérios de aceitação

| # | Critério |
|---|---------|
| AC-01 | O compose permite montar `.pipe/`, `logs/` e `repo/` como volumes (bind mounts ou volumes nomeados). |
| AC-02 | Com os volumes configurados, `docker compose down && docker compose up` preserva snapshot, fila de mudanças, sessões de agente e clones de repositório (RF-06). |
| AC-03 | Removendo os binds, a esteira sobe normalmente em modo efêmero (estado zerado) sem erro (D-04). |

### Recomendação de operação (ADR-04)

Persistir `.pipe/` e `repo/` é fortemente recomendado: evita re-sync completo e
re-clone a cada restart, e preserva a continuidade de raciocínio do agente.
`logs/` é conveniência. O operador decide a estratégia conforme sua necessidade.

### Fora de escopo

Estratégia de backup dos volumes; multi-instância da esteira.

---

## US-05 — Operar de forma autônoma sem intervenção no runtime

**Issue:** #20 (board `story`)
**Rastreabilidade:** RF-07, RNF-04; ADR-05, ADR-06; R-4, R-5

**Como** analista,
**quero** que o container rode o loop principal ininterruptamente, sem prompts
e com falha clara em erro de setup,
**para** operar a esteira sem precisar acessar a máquina hospedeira.

### Escopo desta story

Verifica e garante o comportamento autônomo do runtime — sem alterar lógica de
negócio (RNF-04, ADR-06). O código já é adequado à operação headless; esta
story reaproveitando `check_config` (fail-fast) e a política de restart do
compose. O que esta story entrega: configuração de `PYTHONUNBUFFERED=1`,
validação do fail-fast com exit-code claro, e verificação de que o gate
`need_human` não interrompe o loop.

### Diferença em relação a US-01 (resposta à dúvida do board)

Esta é a distinção mais importante da story para evitar sobreposição com US-01:

| Dimensão | US-01 — Empacotar | US-05 — Operar autonomamente |
|----------|-------------------|------------------------------|
| **Foco** | O que está **dentro da imagem** (binários, código-fonte, usuário, variáveis de build) | Como o **container se comporta em runtime** (sem prompts, fail-fast, restart, logs, gates) |
| **Artefato principal** | `Dockerfile` | Configuração de compose (`restart`) + verificação de comportamento |
| **Pergunta respondida** | "A imagem compila e tem o que precisa?" | "Uma vez em pé, o container opera sozinho sem travar nem parar por issues de negócio?" |
| **Interação com `PYTHONUNBUFFERED`** | Define na imagem | Verifica que logs saem em tempo real em `docker logs` |
| **Interação com `check_config`** | Não cobre | Verifica que falta de credencial/config gera exit-code != 0 e mensagem clara |
| **Interação com `need_human`** | Não cobre | Verifica que o gate não paralisa o container; o loop segue rodando |
| **Interação com `restart`** | Não cobre | Garante `restart: unless-stopped` no compose |

Em resumo: US-01 garante que a imagem **existe e está correta**; US-05 garante
que o **container roda continuamente e de forma previsível** uma vez configurado.
São camadas ortogonais: seria possível ter uma imagem perfeita (US-01) e ainda
assim o compose sem `restart` ou o agente travando em `stdin` — o que US-05
cobre.

### Critérios de aceitação

| # | Critério |
|---|---------|
| AC-01 | Nenhuma etapa do ciclo (startup, clone, sync, agente) aguarda `stdin`; o `kiro-cli` é chamado com `--no-interactive` (RF-07). Verificar que a flag está presente em `kiro_cli_agent.py`. |
| AC-02 | Falta de credencial ou configuração inválida gera `SystemExit(1)` em `check_config` com mensagem clara — sem travamento silencioso (RF-07). Coberto por `_validate_env` (verifica `PIPE_SSH_KEY_FILE`) e `_validate_agents` (verifica contexts não-vazios). |
| AC-03 | `restart: unless-stopped` está declarado no `docker-compose.yml`, mantendo o loop rodando após crash duro (ADR-05). |
| AC-04 | `PYTHONUNBUFFERED=1` está definido (na imagem ou no compose), e os logs aparecem em tempo real em `docker logs <container>` — sem buffering. |
| AC-05 | O gate `need_human` **não** interrompe o container: a esteira ignora issues marcadas com `/need_human` no `keep_task` e segue o ciclo aguardando que o humano atue no board do GitHub. O container permanece rodando. Comportamento verificado (não removido). |
| AC-06 | Nenhum gate de aprovação do fluxo (colunas `need_human`) foi removido do `pipe.yml` (RNF-04, ADR-06). |

### Fora de escopo

Remoção de qualquer gate de aprovação do fluxo; observabilidade avançada
(métricas/alertas/healthcheck HTTP).

### Notas / riscos

- **R-4**: revogação, rotação ou expiração da `KIRO_API_KEY` interrompe as
  chamadas do agente. O error path já é coberto pelo adapter (`kiro_cli_agent.py`
  captura returncode e loga o erro). O procedimento de rotação deve ser
  documentado em US-06.
- **R-5**: `StrictHostKeyChecking no` no `_setup_ssh` é uma decisão consciente e
  aceitável para github.com; registrada como débito técnico (não-bloqueador).

---

## US-06 — Documentar a operação em Docker

**Issue:** #21 (board `story`)
**Rastreabilidade:** RF-08, D-04; R-3, R-4

**Como** usuário novo (sem conhecimento do código),
**quero** um guia simples e completo,
**para** colocar a esteira para rodar em Docker seguindo apenas a documentação.

### Escopo desta story

Consolida a operação de ponta a ponta em um documento de runbook. Depende de
US-01 a US-05 materializadas (Dockerfile, compose, credenciais, persistência,
operação autônoma verificada).

### Critérios de aceitação

O guia, versionado no repositório, cobre:

| # | Seção |
|---|-------|
| AC-01 | **Pré-requisitos no host:** Docker + `docker compose` V2; assinatura Kiro Pro/Pro+/Pro Max/Power e (se conta gerenciada) governança de admin para gerar `KIRO_API_KEY` (R-3); PAT do GitHub com escopos `repo` e `project`; chave SSH configurada no GitHub. |
| AC-02 | **Estrutura do `docker-compose.yml`**: todos os parâmetros (envs, volumes, arquivo `.env`). |
| AC-03 | **Comando para subir:** `docker compose up -d` e verificação de que está rodando (log output esperado do banner + ciclo do loop). |
| AC-04 | **Parar e reiniciar preservando estado** (com e sem volumes de US-04). |
| AC-05 | **Rotação da `KIRO_API_KEY`**: atualizar a variável no `.env` + `docker compose restart` — sem re-login (R-4). |
| AC-06 | **Critério de sucesso final:** um usuário sem conhecimento prévio do código consegue colocar a esteira para rodar seguindo apenas o guia (RF-08 e métrica de sucesso da vision). |

### Fora de escopo

Documentação interna da arquitetura Docker (coberta em
`doc/architecture/rodar-no-docker/arquitetura.md`).

---

## Dependências entre stories

```
US-01 (imagem base)
  └─► US-02 (autenticação headless)
  └─► US-03 (compose + credenciais)
        └─► US-04 (persistência de estado)
        └─► US-05 (operação autônoma verificada)
              └─► US-06 (documentação / runbook)
```

US-02 e US-03 podem ser desenvolvidas em paralelo após US-01. US-04 e US-05
dependem de US-03. US-06 é a última: depende de US-01 a US-05 materializadas.
