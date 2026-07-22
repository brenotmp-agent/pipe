# User Stories — Rodar no Docker

Status: active
Owner: product
Last updated: 2026-07-22

## Histórico de revisões

| Data | Alteração |
|------|-----------|
| 2026-07-21 | Versão inicial (task #40, abordagem COPY) |
| 2026-07-22 | Atualizado para abordagem git clone (ADR-07) + download kiro-cli (ADR-03) |

## Inputs
- Issue #1 "Rodar no Docker"
- doc/product/rodar-no-docker/vision.md
- doc/product/rodar-no-docker/epicos.md
- doc/product/rodar-no-docker/problem-space.md
- doc/arquitetura/rodar-no-docker/arquitetura.md
- CONTEXT.md

---

## US-01 — Empacotar a esteira em imagem Docker (Issue #16)

**Como** analista/operador, **quero** uma imagem Docker que contenha a esteira e
todas as suas dependências de runtime, **para** executar `python -m src` em
qualquer host com Docker, sem preparar a máquina manualmente.

### Contexto

A esteira é uma aplicação Python autocontida (`python -m src`, única dependência
externa `pyyaml`), mas hoje exige um host preparado à mão. Esta story entrega o
empacotamento (Dockerfile) — a base sobre a qual as demais stories de "Rodar no
Docker" se apoiam.

O código da esteira é adquirido durante o build via `git clone` com chave SSH
efêmera (BuildKit secret) — a chave nunca é salva em nenhuma camada da imagem
(ADR-07). O kiro-cli é baixado via URL + verificação SHA-256 durante o build
(ADR-03).

### Critérios de aceitação

- **AC-01**: `docker build` gera imagem com base `python:3.12-slim` (ADR-01).
- **AC-02**: A imagem contém no PATH, com versões pinadas: `git`, `gh`
  (GitHub CLI), `kiro-cli`, `openssh-client`, `ca-certificates` e `pyyaml`
  (ADR-04).
- **AC-03**: `src/` está em `/app/src/`; `pipe.yml` e `contexts/` **não** foram
  copiados (entram por volume em runtime — ADR-06).
- **AC-04**: Nenhum segredo é copiado ou embutido na imagem. `docker history
  --no-trunc` não contém chave SSH, token ou senha (ADR-06, ADR-07).
- **AC-05**: Roda como **usuário não-root** `pipe` (uid 1000) com `$HOME`
  gravável (ADR-05).
- **AC-06**: `PYTHONUNBUFFERED=1` definido na imagem, para logs em tempo real
  em `docker logs` (12-Factor XI).
- **AC-07**: Ao executar o container sem variáveis de ambiente obrigatórias,
  `check_config` falha com `SystemExit(1)` — sem instalação adicional no host.
- **AC-08**: O build é invocado com BuildKit e `--secret id=ssh_key` para
  prover a chave SSH efêmera ao `git clone` (ADR-07).
- **AC-09**: `.dockerignore` contém apenas `*` — contexto de build é vazio por
  construção (ADR-06, ADR-07).

### Dependências

Story-base da feature. Não depende de outra story. Habilita US-02, US-03,
US-04, US-05 e US-06.

Task de pré-requisito: issue #44 (levantar e fixar versões) — ✅ concluída.

### Rastreabilidade

RF-01, RNF-01, RNF-02, RNF-05 | ADR-01, ADR-02, ADR-03, ADR-04, ADR-05,
ADR-06, ADR-07 | Riscos R-2

---

## US-02 — Injetar credenciais e configuração por fora (Issue #17)

**Como** analista/operador, **quero** fornecer toda configuração e segredo via
`docker-compose`, sem nada sensível fixo na imagem, **para** operar a esteira
de forma segura em qualquer ambiente.

### Critérios de aceitação

- Chave SSH montada como volume somente-leitura em `/home/pipe/.ssh/`.
- `GH_TOKEN` injetado via variável de ambiente (não copiado para a imagem).
- `pipe.yml` montado como volume somente-leitura em `/app/pipe.yml`.
- `contexts/` montado como volume em `/app/contexts/`.
- Configuração do `gh` CLI montada como volume somente-leitura em
  `/home/pipe/.config/gh/`.
- Nenhum valor sensível fixo na imagem.

---

## US-03 — Orquestrar via docker-compose (Issue #18) ✅

**Como** analista/operador, **quero** um `docker-compose.yml` pronto para uso,
**para** subir a esteira com um único comando.

### Critérios de aceitação

- **AC-01**: Serviço `pipe` definido com `image: pipe:latest`.
- **AC-02**: Variáveis de ambiente obrigatórias declaradas.
- **AC-03**: `restart: unless-stopped` configurado para recuperação automática
  após crash.
- **AC-04**: Volumes nomeados para `.pipe/`, `logs/` e `repo/` (persistência
  entre reinícios).
- **AC-05**: Volumes dos segredos (SSH, gh, contexts) montados conforme US-02,
  com caminhos compatíveis com o usuário `pipe` (uid 1000, home `/home/pipe`).

---

## US-04 — Verificar binários no PATH após build (Issue #19)

**Como** desenvolvedor, **quero** confirmar que todos os binários estão
acessíveis dentro do container, **para** garantir que o empacotamento está
correto antes de deployar.

### Critérios de aceitação

- `python --version` retorna Python 3.12.x.
- `git --version` retorna a versão pinada (1:2.47.3-0+deb13u1).
- `gh --version` retorna a versão pinada (2.96.0).
- `kiro-cli --version` retorna sem erro (2.13.1).
- Todos os comandos executam sem instalação adicional.

---

## US-05 — Operar de forma autônoma sem intervenção no runtime (Issue #20) ✅

**Como** analista, **quero** que o container rode o loop principal
ininterruptamente, sem prompts e com falha clara em erro de setup, **para**
operar a esteira sem precisar acessar a máquina hospedeira.

### Critérios de aceitação

- **AC-01**: Nenhuma etapa do ciclo aguarda `stdin`; `kiro-cli` é chamado com
  `--no-interactive` em `kiro_cli_agent.py`.
- **AC-02**: Falta de credencial/config gera `SystemExit(1)` em `check_config`
  com mensagem clara.
- **AC-03**: `restart: unless-stopped` declarado no `docker-compose.yml`.
- **AC-04**: `PYTHONUNBUFFERED=1` definido e logs aparecem em tempo real em
  `docker logs`.
- **AC-05**: Gate `need_human` não interrompe o container; a esteira ignora
  issues com `/need_human` em `keep_task` e segue o ciclo.
- **AC-06**: Nenhum gate de aprovação do fluxo foi removido do `pipe.yml`.

---

## US-06 — Documentação de operação Docker / runbook (Issue #21) ✅

**Como** analista novo, **quero** um guia simples e completo, **para** colocar
a esteira para rodar em Docker sem conhecimento prévio do código.

### Critérios de aceitação

- Pré-requisitos listados (Docker, chave SSH, GH_TOKEN, KIRO_API_KEY).
- Passo a passo de subida com `docker compose up`.
- Verificação de que está rodando (logs, `docker ps`).
- Procedimento de rotação da `KIRO_API_KEY` documentado.

---

## Referências de Requisitos Funcionais e Não-Funcionais

| ID    | Descrição |
|-------|-----------| 
| RF-01 | Container executa `python -m src` sem preparação manual do host |
| RF-05 | `pipe.yml` e `contexts/` entram por volume — nunca copiados na imagem |
| RF-07 | Operação headless: nenhuma etapa aguarda `stdin` |
| RF-08 | Runbook documenta subida, verificação e rotação de credenciais |
| RNF-01 | Nenhum segredo embutido na imagem |
| RNF-02 | Base `python:3.12-slim`; todas as dependências com versões pinadas |
| RNF-04 | Sem alteração de lógica de negócio (gates `need_human` preservados) |
| RNF-05 | Versões de todos os binários e pacotes pinadas (sem `latest`) |

## ADRs

| ID     | Decisão |
|--------|---------|
| ADR-01 | Imagem base: `python:3.12-slim` |
| ADR-02 | Build single-stage |
| ADR-03 | kiro-cli: download via URL + SHA-256 |
| ADR-04 | Pinagem de versões de todas as dependências |
| ADR-05 | Usuário não-root: `pipe` (uid 1000) |
| ADR-06 | Externalização de configuração e segredos |
| ADR-07 | Código adquirido via `git clone` com BuildKit secret |
