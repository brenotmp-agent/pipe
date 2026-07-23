# UX — Rodar no Docker

Entregáveis de UX (etapa de Prototipação) para a feature "Rodar no Docker",
com foco na story-base **US-01 — Empacotar a esteira em imagem Docker** (issue
#16) e implicações para US-02..US-06.

Como a esteira é headless e sem GUI, "UX" aqui é **experiência do operador
(DevX)**: onboarding, configuração, saída de log, mensagens de erro e
documentação de operação.

## Documentos

1. [`descoberta.md`](descoberta.md) — enquadramento, roteiro de entrevista com
   respostas derivadas, lacunas abertas (L1–L5), referências de mercado e boas
   práticas de UX de CLI (com fontes).
2. [`jornada-operador.md`](jornada-operador.md) — personas e mapa da jornada
   ponta a ponta (Fases 0–6) com fricções e oportunidades × US.
3. [`prototipos.md`](prototipos.md) — protótipos de baixa fidelidade: banner de
   arranque, `.env.example` anotado, resumo de preflight, heartbeat de
   ociosidade, catálogo de mensagens de erro e wireframe do runbook.

## Princípio central

Nenhuma recomendação altera a lógica de negócio da esteira — são melhorias de
apresentação/saída e documentação. A US-01 (Dockerfile) permanece desbloqueada:
só o banner de arranque e a diretriz de log sem ANSI fora de TTY tocam a imagem.
