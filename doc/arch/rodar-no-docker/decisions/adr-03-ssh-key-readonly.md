# ADR-03 — Chave SSH montada read-only, copiada para `~/.ssh/id_pipe`

Status: Aceito
Data: 2026-07-07
Story: US-02 (#17)
Contexto relacionado: RF-02, RNF-01, RNF-03

## Contexto

O `startup()` clona os repositórios via SSH (`git@github.com:...`). Isso exige
uma chave privada disponível e com permissão restrita (`0600`) — o SSH recusa
chaves com permissão frouxa. Em container, a chave precisa entrar por fora, sem
ser embutida na imagem, e o ponto de montagem tende a ser read-only (Docker
secret).

## Decisão

Montar a chave privada como **volume/secret read-only** (ex.:
`/run/secrets/ssh_key`) e apontar `PIPE_SSH_KEY_FILE` para esse caminho.
`_setup_ssh()` (já existente) copia a chave para `~/.ssh/id_pipe` com modo
`0600` e escreve `~/.ssh/config` com `IdentityFile ~/.ssh/id_pipe` e
`StrictHostKeyChecking no` para `github.com`.

A cópia é necessária precisamente porque a origem é read-only: o SSH exige
`0600` no arquivo de chave, e não é possível ajustar permissão de um secret
montado read-only. A cópia em HOME (gravável — ADR-05) resolve isso.

O clone SSH no `startup()` é, ele próprio, o teste da credencial: chave inválida
faz o `git clone` falhar no arranque. Não é necessário um teste SSH adicional.

## Alternativas consideradas

- **Montar direto em `~/.ssh/id_pipe` e usar sem copiar** — falha quando a
  montagem é read-only ou traz permissão incompatível; o SSH rejeita. A cópia
  é mais robusta e já implementada. Descartado.
- **`ssh-agent` dentro do container** — adiciona um processo e estado; overkill
  para uma única chave estática. Descartado (simplicidade).
- **Chave em env var (base64)** — expõe segredo em `docker inspect`/env dump;
  viola RNF-01. Descartado.

## Consequências

- (+) Reaproveita `_setup_ssh` sem mudança de código.
- (+) Segredo nunca na imagem; origem permanece read-only, só a cópia é gravável.
- (−) A chave existe em dois lugares no container em runtime (montagem + cópia
  em HOME); ambos efêmeros e dentro do container. Aceitável.
- Validação de presença/arquivo já ocorre no arranque (`_validate_env`).

## Fontes

`src/__main__.py` (`_setup_ssh`, `startup`), `src/core/config.py`
(`_validate_env`).
