# UX — Rodar no Docker

Artefatos de experiência do usuário (operador) para o épico "Rodar no Docker".

## US-04 — Persistir estado de runtime entre reinícios

- [`us-04-experiencia-persistencia.md`](./us-04-experiencia-persistencia.md) —
  persona, jornadas, avaliação heurística, recomendações, entrevista de
  descoberta e referências de mercado/UX.
- `prototipos/` — protótipos de baixa fidelidade (mockups anotados):
  - `docker-compose.prototipo.yml` — compose com persistência por default.
  - `compose.ephemeral.prototipo.yml` — override efêmero explícito.
  - `.env.prototipo` — caminhos de estado parametrizados, com impacto de cada um.
  - `startup-feedback.md` — wireframe do feedback de arranque (4 cenários).

> Os protótipos usam o sufixo `.prototipo` para não serem confundidos com os
> artefatos finais de deploy, que são responsabilidade das etapas de engenharia.
