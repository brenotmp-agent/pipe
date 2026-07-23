# Change File — US-01: Empacotar a esteira em imagem Docker

**Story:** #16 — Empacotar a esteira em imagem Docker  
**Epic:** #1 — Rodar no Docker  
**Branch:** `epic16-16-empacotar_a_esteira_em_imagem_docker` → mesclado em `epic`  
**Versão resultante:** 1.6.0  
**Data:** 2026-07-23

---

## Resumo

Esta story entrega o empacotamento da esteira em imagem Docker. O operador
passa a precisar apenas de um `Dockerfile` e acesso de leitura ao repositório —
sem clonar o código manualmente nem preparar o host além do Docker.

---

## Arquivos entregues

### Artefatos de build e orquestração

| Arquivo | Descrição |
|---------|-----------|
| `Dockerfile` | Imagem single-stage baseada em `python:3.12-slim`; instala `git`, `openssh-client`, `ca-certificates`, `gh` (2.96.0), `pyyaml` (6.0.2) e `kiro-cli` (2.13.1); roda como usuário não-root `pipe` (uid 1000); clona `src/` do repositório privado via BuildKit secret SSH efêmero (ADR-07); `PYTHONUNBUFFERED=1`. |
| `.dockerignore` | Nega todo o contexto de build (`*`); garante que nenhum segredo, `pipe.yml` ou `contexts/` entre na imagem (RNF-01, ADR-06). |
| `docker-compose.yml` | Orquestração com volumes nomeados para `repo/`, `logs/`, `.pipe/`, `~/.kiro/` e `~/.local/share/kiro-cli/`; credenciais via Docker secret e `env_file`; `restart: unless-stopped`. |
| `.env.example` | Template comentado com todas as variáveis necessárias (`GH_TOKEN`, `SSH_KEY_FILE_HOST`, `KIRO_API_KEY`, caminhos de estado opcionais). |
| `docker/versions.env` | Arquivo de referência com versões pinadas validadas: `git`, `openssh-client`, `gh`, `pyyaml`, `kiro-cli` (com SHA-256). |
| `prepare-docker.sh` | Script de preparação do contexto de build. |
| `compose.ephemeral.yml` | Compose alternativo para execuções efêmeras (sem volumes persistentes). |

### Código fonte alterado

| Arquivo | Alteração |
|---------|-----------|
| `src/core/preflight.py` | **Novo módulo.** Verificação agregada de credenciais no arranque (SSH, `GH_TOKEN`, `KIRO_API_KEY`); falha rápida com `SystemExit(1)` e resumo completo; nunca imprime valores de segredo. |
| `src/__main__.py` | Integra `preflight()` no fluxo de boot (antes do loop principal). |
| `src/core/version.py` | Bump para versão `1.6.0`. |
| `src/core/config.py` | Ajustes para contexto Docker (mensagens de erro). |
| `src/adapters/kiro_cli_agent.py` | Ajustes compatíveis com ambiente containerizado. |
| `src/adapters/github_board.py` | Ajustes de compatibilidade. |
| `src/core/agent.py` | Ajustes relacionados. |
| `src/core/agent_guard.py` | **Novo módulo.** Guard de execução de agente. |
| `src/core/commands.py` | Ajustes. |
| `src/core/context_generator.py` | **Novo módulo.** Geração de contexto do agente. |
| `src/core/sync.py` | Ajustes de sincronização. |

### Documentação

| Arquivo | Descrição |
|---------|-----------|
| `doc/stories/rodar-no-docker/user-stories.md` | Requisitos completos de US-01 a US-06 com critérios de aceitação. |
| `doc/ux/rodar-no-docker/descoberta.md` | Roteiro de entrevista, lacunas, referências de mercado. |
| `doc/ux/rodar-no-docker/jornada-operador.md` | 2 personas, 7 fases da jornada do operador. |
| `doc/ux/rodar-no-docker/prototipos.md` | Mockups de terminal, catálogo de erros, wireframe do runbook. |
| `doc/ux/rodar-no-docker/README.md` | Índice da documentação UX. |
| `doc/arquitetura/rodar-no-docker/arquitetura.md` | Visão da solução, topologia, Dockerfile de referência, fluxo de arranque, matriz de verificação dos ACs (revisão 2). |
| `doc/arquitetura/rodar-no-docker/README.md` | Catálogo de requisitos RF-01, RNF-01..05, D-01/D-02, riscos R-1, R-2. |
| `doc/arquitetura/rodar-no-docker/adr/ADR-01..07.md` | 7 Architectural Decision Records: imagem base, build single-stage, instalação do kiro-cli, pinagem de versões, usuário não-root, externalização de segredos, aquisição do código via git clone. |
| `doc/runbook/docker.md` | Runbook completo de operação Docker: pré-requisitos, build, subida, diagnóstico, parada, FAQ. |

### Testes

| Arquivo | O que testa |
|---------|-------------|
| `tests/test_dockerfile.py` | Estrutura e corretude do Dockerfile. |
| `tests/test_versions_env.py` | Consistência do `docker/versions.env` com o Dockerfile. |
| `tests/test_docker_compose.py` | Estrutura do `docker-compose.yml`. |
| `tests/test_docker_runbook.py` | Consistência do runbook com os artefatos reais. |
| `tests/test_preflight.py` | Cobertura do módulo `preflight.py`. |
| `tests/test_startup.py` | Fluxo de boot com preflight integrado. |
| `tests/test_autonomous_operation.py` | Operação autônoma em modo headless. |

---

## Critérios de aceitação — status

| AC | Descrição | Status |
|----|-----------|--------|
| AC-01 | `docker build` gera imagem com base `python:3.12-slim` com todas as dependências | ✅ Entregue |
| AC-02 | Dependências pinadas: `git`, `gh`, `kiro-cli`, `openssh-client`, `ca-certificates`, `pyyaml` | ✅ Entregue — versões em `docker/versions.env` |
| AC-03 | `src/` copiado; `pipe.yml` e `contexts/` **não** copiados (entram por volume) | ✅ Entregue — via `git clone` + `.dockerignore: *` |
| AC-04 | Nenhum segredo embutido na imagem | ✅ Entregue — BuildKit secret efêmero (ADR-07, ADR-06) |
| AC-05 | Usuário não-root com `$HOME` gravável | ✅ Entregue — usuário `pipe` (uid 1000, ADR-05) |
| AC-06 | `PYTHONUNBUFFERED=1` definido | ✅ Entregue |
| AC-07 | `python -m src` inicia sem instalação adicional no host | ✅ Entregue |

---

## Decisões arquiteturais relevantes

- **ADR-03:** kiro-cli instalado via zip installer (não `.deb`), em `~/.local/bin`, como usuário não-root.
- **ADR-04:** Risco R-2 fechado — versão `2.13.1` com SHA-256 `49d712...` fixados em `docker/versions.env`.
- **ADR-07:** Código da esteira obtido por `git clone --depth 1` no build, usando chave SSH como BuildKit secret efêmero — operador não precisa clonar o repositório manualmente.

---

## Notas

- SIGTERM handler (`src/__main__.py`) e correção de ANSI sem TTY (`src/core/log.py`) foram identificados como melhorias futuras (US-04) e **não fazem parte desta story** — não bloqueiam a entrega.
- Preflight de credenciais (`src/core/preflight.py`) foi antecipado nesta story por ser pré-requisito do container headless.
- Validação end-to-end (T7 do planejamento técnico) requer host com Docker e chave SSH válida — marcada com `/need_human` no board e fora do escopo automatizável.
