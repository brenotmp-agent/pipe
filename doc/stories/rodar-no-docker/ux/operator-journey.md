# Mapa de jornada — Operador no primeiro `docker compose up`

Status: prototype
Owner: ux (Talita Souza)
Story: #17 (US-02)

## Persona

**Operador/Analista** — quer subir a esteira num host qualquer (servidor, nuvem,
CI) sem prender-se a uma máquina preparada à mão. Conhece Docker, tem conta no
GitHub e assinatura Kiro Pro. **Não** conhece o código da esteira. Fonte:
`vision.md` (público-alvo) e US-06.

Objetivo dele: *"quero dar um comando e ver a esteira trabalhando, com confiança
de que não esqueci nada."*

## A jornada (headless, primeira execução)

Legenda de emoção: 🙂 confiante · 😐 neutro · 😟 inseguro · 😖 travado

| # | Fase | Ação do operador | O que ele vê hoje | Emoção | Dor / oportunidade |
|---|------|------------------|-------------------|--------|--------------------|
| 1 | Descoberta | Lê o runbook, entende que precisa de 3 credenciais | Lista de pré-requisitos (US-06) | 🙂 | Precisa deixar claro **onde obter** cada uma e o **escopo** exigido |
| 2 | Coleta | Gera PAT do GitHub, API key do Kiro, localiza a chave SSH | 3 sistemas diferentes | 😐 | PAT com escopo errado (`repo`/`project`) é a falha nº 1 previsível |
| 3 | Setup | Preenche o `.env` / secret da chave SSH | `.env.example` | 😐→😟 | Se o exemplo não explicar cada variável inline, ele adivinha |
| 4 | Subida | `docker compose up` | Logs correndo | 🙂 | Momento de maior expectativa — é aqui que a confiança se ganha ou perde |
| 5a | **Sucesso** | Aguarda confirmação | *(hoje)* logs de sync, **sem** um "auth OK" | 😟 | **Falta o "check verde"**: ele não sabe se autenticou de verdade |
| 5b | **Falta SSH** | — | `SystemExit(1)` com mensagem clara | 🙂 | Bom: falha rápida e explica. Só falta ser Docker-aware |
| 5c | **Falta GH_TOKEN** | — | *(hoje)* erro cru no meio do loop, minutos depois | 😖 | **Pior ponto da jornada**: falha tardia, difícil correlacionar à causa |
| 5d | **Falta/《inválida》KIRO_API_KEY** | — | *(hoje)* erro cru do kiro-cli no 1º card | 😖 | Idem 5c + risco de confundir com bug do agente |
| 6 | Correção | Ajusta `.env` e sobe de novo | — | 😐 | Só é rápido se a mensagem disser exatamente qual variável e como |
| 7 | Operação | Deixa rodando | `docker logs` | 🙂 | Confia que os gates `need_human` acontecem no board, não na máquina |

## Onde a experiência se decide

Dois momentos concentram quase toda a satisfação/frustração:

- **Fase 4→5 (o arranque):** é o "primeiro contato". A diferença entre 😖 e 🙂
  aqui é ter (a) validação das três credenciais no mesmo instante e (b) um
  resumo de confirmação. Ver cena A em `terminal-prototypes.md`.
- **Fase 6 (a correção):** o custo de recuperação é definido pela copy da
  mensagem. Uma linha de causa + uma de ação + onde obter = um ciclo de
  correção; mensagem crua = tentativa e erro. Ver `error-copy-spec.md`.

## Princípios de design derivados

1. **Falhar cedo, junto e uma vez.** As três credenciais são pré-requisito do
   mesmo objetivo; devem ser verificadas juntas no arranque, não pingadas ao
   longo do loop.
2. **Confirmar o invisível.** Em headless, o que não é dito não existe para o
   operador. Sucesso de autenticação precisa ser afirmado explicitamente.
3. **Falar a língua do contexto.** Rodando em Docker, a correção é no `.env` /
   compose — a copy deve apontar para lá, não para `export` no host.
4. **Nunca vazar segredo.** Confirmar presença e validade sem ecoar valor —
   nem em log de sucesso, nem em erro.
5. **Um gate humano é no board, não na máquina.** Reforçar no runbook que
   esperar humano não exige acesso ao container (alinha com `vision.md`).
