# ADR-04 — Preflight de credenciais no arranque

Status: accepted
Data: 2026-07-22
Owner: arquitetura

## Contexto

A esteira precisa verificar, no arranque, se todas as credenciais externas
estão presentes e válidas antes de iniciar qualquer operação (clone, loop,
chamada de agente). Hoje a validação é assimétrica:

- `PIPE_SSH_KEY_FILE`: falha rápido em `check_config()` se ausente/inválida.
- `GH_TOKEN`: falha lazy no primeiro acesso ao board (dentro do loop).
- `KIRO_API_KEY`: falha lazy na primeira chamada ao agente (dentro do loop).

Em ambiente Docker autônomo, uma falha lazy no meio do loop é operacionalmente
custosa: o operador não tem feedback imediato, e a esteira pode avançar
parcialmente antes de falhar.

## Decisão

Implementar um **preflight de credenciais** como função `preflight()` em
`src/core/preflight.py`, chamada em `startup()` após `_setup_ssh()` e antes
do primeiro clone/operação de board.

O preflight:
- Verifica SSH (presença de `PIPE_SSH_KEY_FILE` + existência do arquivo).
- Verifica GitHub (`GH_TOKEN` presente + `gh auth status` com exit 0).
- Verifica kiro-cli (`KIRO_API_KEY` presente + `kiro-cli whoami` com exit 0).
- **Agrega todos os resultados** antes de abortar — o operador vê todas as
  pendências de uma vez (não apenas a primeira falha).
- Se qualquer credencial falhar: `SystemExit(1)` após emitir resumo completo.
- Se todas ok: retorna normalmente, esteira continua.

O `SystemExit` propaga naturalmente — não é capturado pelo `except Exception`
do loop em `main()`, pois `SystemExit` herda de `BaseException`, não de
`Exception`.

## Sequência de boot após a mudança

```
main()
├── check_config()     # valida pipe.yml + PIPE_SSH_KEY_FILE (primeira barreira)
├── startup()
│   ├── _setup_ssh()   # copia chave para ~/.ssh/id_pipe
│   ├── preflight()    # verifica SSH + GH_TOKEN + KIRO_API_KEY (fail-fast agregado)
│   └── [clone, generate_context, etc.]
├── board.connect()
├── board.check_access()
├── board_full_sync()
└── while running: ...
```

## Consequências

**Positivas:**
- Feedback imediato de todas as pendências de credencial no arranque.
- Sem falhas silenciosas no meio do loop por credencial ausente.
- Testável de forma isolada (sem depender do loop).

**Negativas / trade-offs:**
- O preflight adiciona ~2 chamadas de subprocesso no arranque (`gh auth status`
  + `kiro-cli whoami`), cada uma com timeout de 15s. No happy path, adiciona
  poucos segundos ao tempo de boot.
- Duplica parcialmente a verificação de SSH que já existe em `check_config()`.
  Aceitável: as duas barreiras têm responsabilidades distintas — `check_config()`
  valida a configuração; `preflight()` confirma que o ambiente de runtime
  (após `_setup_ssh()`) está operacional.

## Alternativas consideradas

**A. Manter validação lazy:** rejeitado — não dá feedback imediato em container
autônomo; o operador não sabe o motivo da falha sem inspecionar logs do meio
do loop.

**B. Validar em `check_config()`:** rejeitado — `check_config()` ocorre antes
de `_setup_ssh()`, então a chave ainda não foi copiada para `~/.ssh/id_pipe`.
Além disso, `check_config()` valida apenas configuração estática; verificações
que dependem de subprocesso (`gh`, `kiro-cli`) não pertencem ao domínio de
config.

**C. Validar apenas com `env` (sem subprocess):** rejeitado — presença da env
var não garante validade do token; o preflight precisa confirmar que `gh` e
`kiro-cli` aceitam as credenciais.

## Referências

- `src/core/config.py` — `_validate_env()` (SSH)
- `src/__main__.py` — `startup()`, `main()`
- `doc/stories/rodar-no-docker/ux/terminal-prototypes.md` — cenas A, F
- US-02 (`doc/arch/rodar-no-docker/us-02-autenticacao-headless.md`)
