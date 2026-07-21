# User Stories — Rodar no Docker

Status: active
Owner: product
Last updated: 2026-07-21

## Inputs
- Issue #1 "Rodar no Docker"
- doc/product/rodar-no-docker/vision.md
- doc/product/rodar-no-docker/epicos.md
- doc/product/rodar-no-docker/problem-space.md
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

### Critérios de aceitação

- **AC-01**: `docker build` gera imagem com base `python:3.12-slim`.
- **AC-02**: A imagem contém no PATH, com versões pinadas: `git`, `gh`
  (GitHub CLI), `kiro-cli`, `openssh-client`, `ca-certificates` e `pyyaml`.
- **AC-03**: `src/` é copiado; `pipe.yml` e `contexts/` **não** são copiados
  (entram por volume em runtime).
- **AC-04**: Nenhum segredo é copiado ou embutido na imagem (chaves SSH,
  tokens, `contexts/`).
- **AC-05**: Roda como **usuário não-root** com `$HOME` gravável (necessário
  para `_setup_ssh` escrever `~/.ssh/` e para o kiro-cli persistir estado de
  sessão em `~/`).
- **AC-06**: `PYTHONUNBUFFERED=1` definido na imagem, para logs em tempo real
  em `docker logs` (12-Factor XI).
- **AC-07**: Ao executar o container sem variáveis de ambiente obrigatórias,
  `check_config` falha com `SystemExit(1)` — sem instalação adicional no host.

### Dependências

Story-base da feature. Não depende de outra story. Habilita US-02, US-03,
US-04, US-05 e US-06.

### Rastreabilidade

RF-01, RNF-01, RNF-02, RNF-05 | ADR-05, ADR-06 | Risco R-2

---

## US-02 — Injetar credenciais e configuração por fora (Issue #17)

**Como** analista/operador, **quero** fornecer toda configuração e segredo via
`docker-compose`, sem nada sensível fixo na imagem, **para** operar a esteira
de forma segura em qualquer ambiente.

### Critérios de aceitação

- Chave SSH montada como volume somente-leitura.
- `GH_TOKEN` injetado via variável de ambiente (não copiado para a imagem).
- `pipe.yml` montado como volume somente-leitura.
- `contexts/` montado como volume.
- Configuração do `gh` CLI montada como volume somente-leitura.
- Nenhum valor sensível fixo na imagem.

---

## US-03 — Orquestrar via docker-compose (Issue #18)

**Como** analista/operador, **quero** um `docker-compose.yml` pronto para uso,
**para** subir a esteira com um único comando.

### Critérios de aceitação

- **AC-01**: Serviço `pipe` definido com `image: pipe:latest`.
- **AC-02**: Variáveis de ambiente obrigatórias declaradas.
- **AC-03**: `restart: unless-stopped` configurado para recuperação automática
  após crash.
- **AC-04**: Volumes nomeados para `.pipe/`, `logs/` e `repo/` (persistência
  entre reinícios).
- **AC-05**: Volumes dos segredos (SSH, gh, contexts) montados conforme US-02.

---

## US-04 — Verificar binários no PATH após build (Issue #19)

**Como** desenvolvedor, **quero** confirmar que todos os binários estão
acessíveis dentro do container, **para** garantir que o empacotamento está
correto antes de deployar.

### Critérios de aceitação

- `python --version` retorna Python 3.12.x.
- `git --version` retorna a versão pinada.
- `gh --version` retorna a versão pinada.
- `kiro-cli --version` retorna sem erro.
- Todos os comandos executam sem instalação adicional.

---

## US-05 — Operar de forma autônoma sem intervenção no runtime (Issue #20)

**Como** analista, **quero** que o container rode o loop principal
ininterruptamente, sem prompts e com falha clara em erro de setup, **para**
operar a esteira sem precisar acessar a máquina hospedeira.

### Contexto

O código já é adequado à operação headless; esta story garante e verifica o
comportamento autônomo, reaproveitando `check_config` (fail-fast) e a política
de restart do compose. Sem alteração de lógica de negócio (RNF-04, ADR-06).

"Sem humano" refere-se à operação do runtime. Os gates `need_human` permanecem
e são resolvidos pela ação humana diretamente no board do GitHub; o container
segue rodando e retoma no ciclo seguinte.

### Critérios de aceitação

- **AC-01**: Nenhuma etapa do ciclo aguarda `stdin`; `kiro-cli` é chamado com
  `--no-interactive` em `kiro_cli_agent.py`.
- **AC-02**: Falta de credencial/config gera `SystemExit(1)` em `check_config`
  com mensagem clara (sem travamento silencioso).
- **AC-03**: `restart: unless-stopped` declarado no `docker-compose.yml`.
- **AC-04**: `PYTHONUNBUFFERED=1` definido (na imagem ou no compose) e logs
  aparecem em tempo real em `docker logs`.
- **AC-05**: Gate `need_human` não interrompe o container; a esteira ignora
  issues com `/need_human` em `keep_task` e segue o ciclo.
- **AC-06**: Nenhum gate de aprovação do fluxo foi removido do `pipe.yml`.

### Dependências

Depende de US-03 (compose com `restart`) e US-02 (credenciais válidas).

### Rastreabilidade

RF-07, RNF-04 | ADR-05, ADR-06 | Riscos R-4, R-5

---

## US-06 — Documentação de operação Docker / runbook (Issue #21)

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

## ADRs Referenciados

| ID     | Decisão |
|--------|---------|
| ADR-05 | Usuário não-root (`pipe`, uid 1000) com `$HOME` gravável |
| ADR-06 | Sem alteração de lógica de negócio da esteira para suportar Docker |
