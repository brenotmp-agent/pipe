# Requisitos — Rodar no Docker

Status: draft
Owner: requirements
Last updated: 2026-07-02

## Inputs
- Issue #1 "Rodar no Docker"
- doc/product/rodar-no-docker/vision.md
- doc/product/rodar-no-docker/problem-space.md
- doc/product/rodar-no-docker/epicos.md
- src/core/config.py
- src/adapters/kiro_cli_agent.py
- src/__main__.py (startup, _setup_ssh)
- README.md / CONTEXT.md

---

## Contexto de análise

A esteira hoje pressupõe um host preparado manualmente. O `startup` lê a
variável `PIPE_SSH_KEY_FILE`, copia a chave para `~/.ssh/id_pipe` e configura
`~/.ssh/config`. O adapter `kiro_cli_agent` invoca `kiro-cli chat` via PATH,
assumindo autenticação prévia. As operações de board usam `gh` CLI autenticado.
Nada disso é empacotado nem parametrizável para um ambiente efêmero de
container.

---

## Requisitos Funcionais

### RF-01 — Imagem com todas as dependências de runtime
A imagem deve conter, pré-instalados e no PATH:
- Python 3.12+
- Código-fonte da esteira (`src/`)
- `pyyaml` (única dependência Python declarada no README)
- `git`
- `gh` CLI (GitHub CLI)
- `kiro-cli`

**Critério de aceitação:** `python -m src` executa dentro do container sem
nenhuma instalação adicional no host.

### RF-02 — Injeção de chave SSH via variável de ambiente
A variável `PIPE_SSH_KEY_FILE` já é o ponto de entrada de configuração SSH
(`_validate_env` em `config.py`). No contexto de container, o arquivo SSH deve
ser fornecido via montagem de volume ou secret Docker; `PIPE_SSH_KEY_FILE` deve
apontar para o caminho montado dentro do container.

**Critério de aceitação:** a esteira clona repositórios via SSH sem nenhuma
preparação manual dentro do container.

### RF-03 — Autenticação do `gh` CLI sem interatividade
O `gh` CLI precisa estar autenticado antes que qualquer chamada de board ocorra
(`github_board.py` usa `gh api`). A autenticação deve ser possível via arquivo
de credenciais ou token injetado como variável de ambiente — sem prompt
interativo.

**Critério de aceitação:** `gh auth status` retorna sucesso dentro do
container a partir de credenciais fornecidas via compose, sem nenhuma ação
manual.

### RF-04 — Autenticação do `kiro-cli` sem interatividade
O adapter `kiro_cli_agent.py` chama `kiro-cli chat --no-interactive`. A
autenticação do `kiro-cli` deve funcionar em modo headless, a partir de
credenciais ou arquivos injetados via compose.

**Critério de aceitação:** `kiro-cli chat --no-interactive` executa com
sucesso dentro do container sem prompt de login.

**Risco:** o mecanismo de autenticação headless do `kiro-cli` deve ser
confirmado em Arquitetura — pode ser bloqueador.

### RF-05 — Configuração completa via `docker-compose`
Toda configuração necessária para rodar a esteira deve ser declarável no
`docker-compose.yml`, sem alterar a imagem:
- `pipe.yml` — via montagem de volume.
- `contexts/` — via montagem de volume.
- Chave SSH — via volume ou Docker secret.
- Credencial do `gh` — via variável de ambiente (token) ou volume.
- Credencial do `kiro-cli` — via volume ou variável de ambiente.

**Critério de aceitação:** `docker compose up` sobe a esteira funcionando com
configurações distintas sem rebuild da imagem.

### RF-06 — Persistência configurável de estado de runtime
Os diretórios `.pipe/`, `logs/` e `repo/` acumulam estado entre ciclos. O
compose deve permitir que o usuário monte esses diretórios como volumes,
tornando o estado persistente entre reinícios do container.

**Critério de aceitação:** após `docker compose down && docker compose up`, o
estado anterior (`.pipe/`, `logs/`, `repo/`) é preservado quando volumes estão
configurados.

### RF-07 — Operação autônoma sem prompts interativos
Nenhuma etapa do ciclo principal — startup, clone, sync, agente — pode
aguardar input do terminal. Falhas de credencial ou setup devem resultar em
saída com código de erro e mensagem clara, não em travamento silencioso.

**Critério de aceitação:** o container roda `python -m src` sem nenhum prompt
interativo; falhas de credencial geram log de erro e exit-code != 0.

### RF-08 — Documentação de operação simples e completa
Deve existir um guia de operação que cubra:
1. Pré-requisitos no host (Docker, credenciais disponíveis).
2. Estrutura do `docker-compose.yml` com todos os parâmetros.
3. Comando para subir a esteira (`docker compose up`).
4. Como verificar que a esteira está rodando (log output esperado).
5. Como parar e reiniciar preservando estado.

**Critério de aceitação:** um usuário sem conhecimento prévio do código
consegue colocar a esteira para rodar seguindo apenas o guia.

---

## Requisitos Não-Funcionais

### RNF-01 — Segredos nunca embutidos na imagem
A imagem deve ser construída sem nenhum segredo hardcoded. Tokens, chaves e
senhas só entram em runtime, via variáveis de ambiente ou volumes externos.

### RNF-02 — Imagem leve e baseada em imagem oficial
Usar base oficial (ex.: `python:3.12-slim` ou similar) para reduzir superfície
de ataque e tamanho da imagem. Instalar apenas as dependências estritamente
necessárias.

### RNF-03 — Compatibilidade com `docker compose` (V2)
O compose deve funcionar com `docker compose` (plugin V2, sem hífen). Não é
obrigatorio garantir compatibilidade com `docker-compose` V1 (deprecado).

### RNF-04 — Sem alteração da lógica de negócio da esteira
O código da esteira não deve ser modificado para rodar em container. Toda
adaptação deve ocorrer via configuração externa e Dockerfile.
Exceção permitida: se o `kiro-cli` não suportar autenticação headless de
nenhuma forma, o adapter pode precisar de ajuste minimal — deve ser documentado
como issue separada e não bloquear a entrega deste escopo.

### RNF-05 — Reprodutibilidade do build
O `Dockerfile` deve produzir a mesma imagem em builds sucessivos (pinagem de
versões de dependências, sem `latest` genérico em dependências críticas).

---

## Dependências e Riscos

| ID | Item | Tipo | Ação |
|----|------|------|------|
| D-01 | Autenticação headless do `kiro-cli` | Risco técnico (bloqueador potencial) | Confirmar mecanismo em Arquitetura antes de implementar RF-04 |
| D-02 | Versão do `kiro-cli` compatível com `--no-interactive` | Dependência | Confirmar versão mínima e método de instalação |
| D-03 | Autenticação do `gh` via token de ambiente | Dependência | Verificar suporte (`GH_TOKEN` / `GITHUB_TOKEN`) — documentado pelo GitHub CLI |
| D-04 | Política de persistência de `.pipe/` | Decisão de produto | Usuário decide se persiste ou começa zerado a cada `up` |

---

## Fora de Escopo

- Publicação da imagem em registry (Docker Hub, GHCR, ECR etc.).
- Orquestração com Kubernetes ou qualquer runtime além de Docker Compose.
- Alteração dos gates de aprovação do fluxo (`need_human`).
- CI/CD da própria esteira (build e push automático da imagem).
- Multi-repositório no compose (um serviço = uma instância da esteira).

---

## Critério de conclusão da feature

A feature "Rodar no Docker" está concluída quando:
1. Existe um `Dockerfile` e um `docker-compose.yml` (ou `docker-compose.example.yml`) na raiz do repositório.
2. Todos os requisitos RF-01 a RF-08 são atendidos e verificáveis.
3. A documentação de operação (RF-08) está publicada no repositório.
4. A imagem não contém segredos (RNF-01).
