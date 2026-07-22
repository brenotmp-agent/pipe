# Rodar no Docker — documentação por fase

Documentação das stories do épico **Rodar no Docker**, organizada pela ordem das
fases da esteira.

## Fases

| Fase | Artefato | Descrição |
|------|----------|-----------|
| Requisitos | [`user-stories.md`](./user-stories.md) | User stories US-01..US-05. |
| Requisitos | [`requisitos-decisoes.md`](./requisitos-decisoes.md) | RF-06, D-04 e ADR-04. |
| UX | [`ux/README.md`](./ux/README.md) | Persona, jornadas, heurísticas, protótipos. |
| **Arquitetura** | [**`arquitetura.md`**](./arquitetura.md) | **Arquitetura de persistência (US-04): contrato de volumes, ciclo de vida do estado, ADR-05, ADR-06.** |
| Change File | [`change-file.md`](./change-file.md) | Registro de todas as alterações entregues na story #19. |

## US-04 — Persistir estado de runtime entre reinícios

A documentação **arquitetural** desta story está em
[`arquitetura.md`](./arquitetura.md). Resumo do que ela fixa:

- **Contrato de volumes (D-05):** `WORKDIR /app` e bind mounts por subdiretório
  (`/app/.pipe`, `/app/repo`, `/app/logs`), parametrizados por `.env` — nunca
  `/app` inteiro.
- **Ciclo de vida do estado:** cada artefato classificado em PRESERVAR /
  RECONSTRUIR / REUSAR / ACUMULAR (contrato que o `startup()` já cumpre).
- **ADR-05:** modo de persistência **observável a partir do sistema de
  arquivos** (sem flag nova), com a ordem obrigatória do `startup()`.
- **ADR-06:** invariante de **instância única** sobre os volumes de estado.
- **Anti-over-engineering:** sem banco, cache, store externo, lock distribuído,
  dependência ou flag novas — só FS + volumes Docker.

## Rastreabilidade

`arquitetura.md` consolida a rastreabilidade (Seção 11) entre RF-06 / D-04 /
ADR-04 (requisitos), H-1..H-5 / R-1..R-5 (UX) e as decisões novas D-05 / ADR-05
/ ADR-06.
