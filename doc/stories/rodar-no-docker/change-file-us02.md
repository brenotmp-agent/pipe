# Change File — US-02: Autenticar dependências externas em modo headless

**Story:** #17  
**Épico:** #1 — Rodar no Docker  
**Data:** 2026-07-23  
**Versão entregue:** 1.6.0  
**Branch da story:** `epic17-17-autenticar_dependencias_externas_em_modo_headless`  
**Tasks filhas mergeadas:** #33, #34, #35, #36 → branch `epic`

---

## Resumo executivo

Entrega do mecanismo completo de autenticação headless da esteira no contexto Docker.
A story fechou os três vetores de credencial (SSH, GitHub CLI, kiro-cli) sem interação manual
e adicionou um preflight de verificação fail-fast no arranque, conforme ADR-04.

---

## Alterações entregues

### #33 — Ajustar copy das mensagens de erro de SSH para contexto Docker

**Arquivo:** `src/core/config.py`

- Reescrita das mensagens de erro de validação de `PIPE_SSH_KEY_FILE` para serem Docker-aware.
- As mensagens anteriores sugeriam `export` no host; agora apontam para Docker secret/volume.
- Catálogo M-01 e M-02 implementados (template: causa / ação / onde).
- Garante que o operador saiba corrigir no `.env` ou `docker-compose.yml`, não no shell do host.

**Testes:** `tests/test_autonomous_operation.py` — 118 linhas adicionadas cobrindo os novos textos.

---

### #34 — Implementar função `preflight()` de verificação de credenciais no arranque

**Arquivo criado:** `src/core/preflight.py` (208 linhas)  
**Testes criados:** `tests/test_preflight.py` (1 049 linhas, 40 testes)

Implementação da função `preflight()` conforme ADR-04:

- **SSH:** verifica `PIPE_SSH_KEY_FILE` definida e arquivo existente no container.
- **GitHub CLI (RF-03):** verifica `GH_TOKEN` definido; executa `gh auth status` para confirmar autenticação headless sem `gh auth login`; detecta opcionalmente escopo `project` faltante (cena D do UX).
- **kiro-cli (RF-04, ADR-01):** verifica `KIRO_API_KEY` definida; tenta `kiro-cli whoami` (com fallback para `kiro-cli auth status`) para confirmar método headless ativo.
- **Agregação de falhas:** coleta todos os erros antes de emitir `SystemExit(1)` com resumo único — o operador vê todas as credenciais faltantes de uma vez, não uma por iteração.
- **Confirmação positiva:** no caminho feliz, emite "3/3 OK" — o operador tem feedback explícito de que o arranque está íntegro.
- **Segurança:** nenhum valor de credencial é impresso nos logs — apenas identidade/método/caminho.
- **Continuidade de sessão (R-1 fechado):** `--list-sessions` e `--resume-id` operam normalmente com `KIRO_API_KEY`; o `SessionIndex` da esteira funciona integralmente em container sem degradação.

---

### #35 — Integrar `preflight()` ao fluxo de boot da esteira

**Arquivo:** `src/__main__.py` (+2 linhas)  
**Testes criados:** `tests/test_startup.py` (612 linhas)

- Import de `preflight` adicionado em `__main__.py`.
- Chamada `preflight()` inserida no início de `startup()`, antes de `_setup_ssh`.
- Fluxo resultante: `check_config()` (valida YAML/SSH lazy) → `startup()` → `preflight()` (verifica as 3 credenciais fail-fast) → `_setup_ssh()` → clone.
- O preflight complementa — não substitui — a validação lazy existente (salvaguarda para expiração/revogação em runtime, conforme AC-06).

---

### #36 — Bump de versão MINOR pela adição do preflight de credenciais

**Arquivo:** `src/core/version.py`  
**Arquivo:** `CONTEXT.md` (+13 linhas)  
**Testes criados:** `tests/test_version_bump.py` (153 linhas)

- Versão bumpeada de `1.5.x` → `1.6.0` (MINOR: adição de comportamento).
- `CONTEXT.md` atualizado com registro da mudança de comportamento de boot introduzida pelo preflight.

---

## Critérios de aceitação — rastreabilidade

| AC | Descrição | Status |
|----|-----------|--------|
| AC-01 (RF-02) | SSH: chave montada read-only + `PIPE_SSH_KEY_FILE` → clone sem interação | ✅ Entregue (#33, #35) |
| AC-02 (RF-03) | gh: `GH_TOKEN` → `gh auth status` OK sem `gh auth login` | ✅ Entregue (#34) |
| AC-03 (RF-04) | kiro-cli: `KIRO_API_KEY` → executa sem prompt + `whoami` confirma método | ✅ Entregue (#34) |
| AC-04 (R-1) | Continuidade: `--list-sessions`/`--resume-id` operam com API key | ✅ Fechado (sem degradação) |
| AC-05 | Nenhuma credencial embutida na imagem (RNF-01) | ✅ Garantido (apenas env vars + volume) |
| AC-06 | Validação: preflight fail-fast no arranque + lazy como salvaguarda | ✅ Entregue (#34, #35) |

---

## Arquivos modificados/criados (escopo desta story)

| Arquivo | Tipo | Task |
|---------|------|------|
| `src/core/config.py` | modificado | #33 |
| `src/core/preflight.py` | **criado** | #34 |
| `src/__main__.py` | modificado | #35 |
| `src/core/version.py` | modificado | #36 |
| `CONTEXT.md` | modificado | #36 |
| `tests/test_autonomous_operation.py` | modificado | #33 |
| `tests/test_preflight.py` | **criado** | #34 |
| `tests/test_startup.py` | **criado** | #35 |
| `tests/test_version_bump.py` | **criado** | #36 |

> Nota: outros arquivos presentes na branch `epic` (Dockerfile, docker-compose, runbook, etc.)
> pertencem às stories #16, #18, #19, #20, #21 e não são parte do escopo de #17.

---

## Débitos e pontos de atenção

- **R-3 (pré-condição operacional):** `KIRO_API_KEY` exige Kiro Pro/Pro+/Pro Max/Power; em contas gerenciadas por admin, a geração de key precisa estar habilitada. Documentado como pré-requisito em US-06 (runbook, #21).
- **Subcomando de status do kiro-cli:** `preflight()` tenta `kiro-cli whoami` com fallback para `kiro-cli auth status`. Confirmar subcomando exato contra versão instalada na imagem (US-01, #16) durante integração final.

---

## Rastreabilidade

RF-02, RF-03, RF-04, D-01, D-03; ADR-01, ADR-02, ADR-03, ADR-04; riscos R-1, R-3.  
Ver `doc/stories/rodar-no-docker/user-stories.md` (US-02) e `doc/arch/rodar-no-docker/us-02-autenticacao-headless.md`.
