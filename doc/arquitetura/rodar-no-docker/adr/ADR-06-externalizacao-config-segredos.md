# ADR-06 — Externalização de configuração e segredos

Status: aceito
Data: 2026-07-07
Relacionado: RNF-01, RNF-03, RNF-04
Escopo: princípio definido em US-01; concretização em US-02/US-03

## Contexto

A esteira depende de configuração de ambiente (`pipe.yml`, `contexts/`) e de
segredos (chave SSH, `GH_TOKEN`, `KIRO_API_KEY`). Nada disso pode ser embutido
na imagem (RNF-01), e trocar uma credencial não pode exigir rebuild (RNF-03).

## Decisão

**Nada de ambiente ou segredo entra na imagem.** A imagem contém apenas código
(`src/`, obtido por `git clone` no build — ADR-07) e binários de runtime. Tudo
o mais é injetado no arranque do container:

| Tipo | Como é injetado | Momento |
|------|-----------------|---------|
| `pipe.yml`, `contexts/` | volume somente-leitura | runtime (US-03) |
| Chave SSH | Docker secret / arquivo ro apontado por `PIPE_SSH_KEY_FILE` | runtime (US-02) |
| `GH_TOKEN`, `KIRO_API_KEY` | variável de ambiente via `.env` do host (não versionado) | runtime (US-02) |
| Estado (`repo/`, `logs/`, `.pipe/`, `~/.kiro`, `~/.local/share/kiro-cli`) | volumes nomeados | runtime (US-02) |

Garantias na imagem (US-01): `.dockerignore` nega **todo** o contexto de build
(`*`), de modo que nenhum segredo/estado local chega ao daemon. O código vem por
`git clone` autenticado com um **secret efêmero de BuildKit** que não persiste em
camadas (ADR-07).

## Justificativa

- Separar imagem (imutável, reprodutível) de configuração (mutável, sensível) é
  o padrão 12-factor e o que torna a mesma imagem portável entre hosts (RNF-04).
- Segredos em volume/secret ro não aparecem em `docker history`/`docker inspect`
  da imagem; a chave SSH em secret evita exposição via variável de ambiente.
- `.env` no `.gitignore` mantém os valores fora do versionamento.

## Consequências

- A imagem sozinha não roda: exige as montagens/variáveis de US-02/US-03 — é o
  comportamento desejado.
- `check_config()`/`_validate_env()` já falham cedo e claro se a configuração
  mínima estiver ausente (US-05), tornando a ausência de injeção detectável no
  arranque em vez de falha silenciosa.
- A escolha entre Docker secret e bind mount ro para a chave SSH é detalhada em
  US-02; ambas satisfazem RNF-01.
