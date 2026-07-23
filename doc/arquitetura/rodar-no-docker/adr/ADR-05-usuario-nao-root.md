# ADR-05 — Usuário não-root com `$HOME` gravável

Status: aceito
Data: 2026-07-07
Relacionado: RNF-01, RF-01, AC-04

## Contexto

Boa prática de container é não rodar como root. Mas a esteira **escreve no
`$HOME` em runtime**:

- `_setup_ssh()` (`src/__main__.py`) cria `~/.ssh/`, escreve `~/.ssh/id_pipe`
  (0600) e `~/.ssh/config`.
- O kiro-cli persiste sessões e config em `~/.kiro/` e mantém um índice SQLite
  em `~/.local/share/kiro-cli/` (keyed por cwd) — base da continuidade de
  sessão da esteira (`.pipe/sessions.json`).
- O kiro-cli também escreve logs em `$XDG_RUNTIME_DIR/kiro-log/`.

Logo, o usuário precisa ser não-root **e** ter um `$HOME` real e gravável.

## Decisão

Criar um usuário `pipe` (uid 1000) com home próprio
(`useradd --create-home`), rodar o container como esse usuário (`USER pipe`) e
garantir `WORKDIR /app` de sua propriedade. Definir `XDG_RUNTIME_DIR=/tmp` para
os logs do kiro-cli (containers Debian slim não definem essa variável).

## Justificativa

- Não-root reduz o impacto de um comprometimento (RNF-01) e é exigência comum
  de plataformas de orquestração.
- `--create-home` garante `/home/pipe` gravável, atendendo `_setup_ssh()` e o
  estado do kiro-cli sem `chmod` frágil em runtime.
- uid 1000 fixo facilita casar permissões de volumes nomeados (US-02).

## Consequências

- A instalação do kiro-cli (ADR-03) roda **após** `USER pipe`, indo para
  `~/.local/bin` do usuário.
- `gh` e pacotes `apt` são instalados **antes** do `USER pipe` (exigem root).
- Volumes de estado montados devem pertencer ao uid 1000 (documentar em US-02).
- A chave SSH é injetada como secret/arquivo somente-leitura e **copiada** pelo
  `_setup_ssh()` para `~/.ssh/id_pipe` — o segredo nunca fica na imagem
  (RNF-01).
