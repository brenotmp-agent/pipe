# ADR-06 — Externalização de configuração e segredos

Status: aprovado
Owner: arquitetura
Last updated: 2026-07-22
Autora: Rafael Martins — Analista de Requisitos

---

## Contexto

A esteira precisa de vários itens de configuração e segredo para operar:
- `pipe.yml` — configuração do loop (boards, agentes, sleep)
- `contexts/` — contextos dos agentes (podem conter instruções sensíveis)
- Chave SSH — para clonar repositórios privados
- `GH_TOKEN` — para operações de board no GitHub
- Autenticação do `gh` CLI (`~/.config/gh/`)

Esses itens são específicos de cada instalação e não devem ser embutidos na
imagem — isso violaria RNF-01 e tornaria a imagem não portável.

## Decisão

**Nenhum segredo ou configuração de instância** é copiado para a imagem.
Toda configuração é fornecida em tempo de execução via `docker-compose`:

| Item | Mecanismo |
|------|-----------|
| `pipe.yml` | Volume bind mount somente-leitura |
| `contexts/` | Volume bind mount |
| Chave SSH | Volume bind mount somente-leitura para `/home/pipe/.ssh/` |
| `GH_TOKEN` | Variável de ambiente |
| Config `gh` | Volume bind mount somente-leitura para `/home/pipe/.config/gh/` |
| Estado `.pipe/` | Volume nomeado (persistido entre reinícios) |
| `logs/` | Volume nomeado (persistido entre reinícios) |
| `repo/` | Volume nomeado (persistido entre reinícios) |

A imagem contém **apenas**: runtime Python, binários de sistema, e o código
de `src/`. Nenhum arquivo do operador.

## Justificativa

- **Portabilidade**: a mesma imagem funciona para qualquer instalação — cada
  operador injeta sua própria configuração via compose.
- **Segurança (RNF-01)**: segredos nunca ficam na imagem, logo nunca aparecem
  em `docker history`, `docker inspect`, ou registries.
- **Sem rebuild para reconfigurar**: alterar `pipe.yml` ou credenciais não
  requer rebuild da imagem — apenas reiniciar o container (RF-05).
- **12-Factor**: alinha com os fatores III (config via env) e IV (backing services
  como recursos atachados).

## Implicações para o .dockerignore

Como `pipe.yml`, `contexts/`, `.pipe/`, `.env` e credenciais ficam no
diretório do projeto no host, o `.dockerignore` deve excluí-los do contexto
de build. Com a abordagem de `git clone` (ADR-07), o contexto de build pode
ser completamente vazio — `.dockerignore: *` é suficiente.

## Implicações para o Dockerfile

- Não há `COPY pipe.yml`, `COPY contexts/` ou qualquer `COPY` de
  credenciais.
- A instrução `ENV PIPE_SSH_KEY_FILE` **não** é definida na imagem (seu valor
  depende do operador).
- A única `ENV` obrigatória na imagem é `PYTHONUNBUFFERED=1` (para logging).

## Consequências

- Um container sem volumes montados e sem `GH_TOKEN` falhará em `check_config`
  com `SystemExit(1)` — comportamento intencional e documentado (AC-07 da US-01).
- O `docker-compose.yml` é o único artefato que declara os volumes e variáveis
  de ambiente necessários para uma instalação funcionar.
