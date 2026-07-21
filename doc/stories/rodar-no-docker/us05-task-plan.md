# Plano de Tasks — US-05: Operar de forma autônoma sem intervenção no runtime

Status: planejado
Owner: tech-lead (Isabela Gomes)
Created: 2026-07-21
Story: #20 (board `story`)
Board de tasks: Pipe - Tasks (#16)

## Resumo do planejamento

A US-05 verifica e garante o comportamento autônomo do runtime sem alterar
lógica de negócio (RNF-04/ADR-06). O código já está adequado; as tasks cobrem:
- Testes automatizados que comprovam os critérios AC-01, AC-02 e AC-05
- Artefatos de infraestrutura Docker (Dockerfile + docker-compose.yml)
- Documentação de operação (runbook)

## Mapa de tasks × critérios de aceitação

| Task | Issue | AC cobertos | Bloqueada por |
|------|-------|-------------|---------------|
| Testes: `--no-interactive` | #37 | AC-01 | — |
| Testes: fail-fast `SystemExit(1)` | #38 | AC-02 | #37 |
| Testes: `need_human` não trava | #39 | AC-05, AC-06 | #38 |
| Dockerfile com `PYTHONUNBUFFERED=1` | #40 | AC-04 (US-01) | #39 |
| docker-compose com `restart: unless-stopped` | #41 | AC-03 (US-03, US-04) | #40 |
| Runbook de operação Docker | #42 | RF-08 (US-06) | #41 |

## Ordem de execução

```
#37 (testes --no-interactive)
  └─► #38 (testes fail-fast)
        └─► #39 (testes need_human)
              └─► #40 (Dockerfile)
                    └─► #41 (docker-compose)
                          └─► #42 (runbook)
```

## Rastreabilidade

- US-05 story: #20
- US-01 (empacotamento): #16 → coberta pela task #40
- US-02 (autenticação headless): #17 → coberta pelo compose (#41) + runbook (#42)
- US-03 (compose sem rebuild): #18 → coberta pela task #41
- US-04 (persistência): #19 → coberta pela task #41
- US-06 (runbook): #21 → coberta pela task #42
