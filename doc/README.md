# Documentação

Índice geral da documentação do projeto, organizada por fase.

## Produto

Visão, espaço-problema e épicos (o "porquê" e o "o quê" de negócio).

- [`product/rodar-no-docker/vision.md`](./product/rodar-no-docker/vision.md)
- [`product/rodar-no-docker/problem-space.md`](./product/rodar-no-docker/problem-space.md)
- [`product/rodar-no-docker/epicos.md`](./product/rodar-no-docker/epicos.md)

## Stories (por épico)

Requisitos, UX e **arquitetura** de cada story (o "como").

- [`stories/rodar-no-docker/`](./stories/rodar-no-docker/README.md) — épico
  **Rodar no Docker**. Contém a documentação arquitetural em
  [`stories/rodar-no-docker/arquitetura.md`](./stories/rodar-no-docker/arquitetura.md).

## Como navegar

Cada épico em `stories/<épico>/` traz um `README.md` que indexa os artefatos por
fase (requisitos → UX → arquitetura). A documentação **arquitetural** de cada
story fica em `stories/<épico>/arquitetura.md`.

Documentação técnica transversal (decisões do core, estado do projeto) vive em
[`../CONTEXT.md`](../CONTEXT.md) na raiz do repositório.
