# Changelog

Todas as alterações relevantes deste projeto são documentadas neste arquivo.
Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

---

## [Não lançado] — US-03: Configurar a esteira via docker-compose sem rebuild

> Branch: `epic18-18-configurar_a_esteira_via_docker_compose_sem_rebuild`
> Issue: #18 | Epic: #1 (Rodar no Docker)
> Rastreabilidade: RF-05, RNF-01, RNF-03; ADR-01, ADR-02, ADR-03, ADR-07

### Adicionado

#### Documentação de Requisitos
- `doc/stories/rodar-no-docker/user-stories.md` — US-03 refinada com critérios
  de aceitação AC-01..AC-07 completos:
  - AC-01: `docker-compose.yml` versionado na raiz, formato `docker compose` V2
  - AC-02: Volumes `pipe.yml` e `contexts/` montados `:ro`
  - AC-03: Chave SSH injetada como Docker secret (não bind-mount)
  - AC-04: Variáveis `GH_TOKEN`, `KIRO_API_KEY`, `PIPE_SSH_KEY_FILE` declaradas
  - AC-05: `.env.example` + `.gitignore` garantindo que nada sensível é versionado
  - AC-06: Mecanismo "sem rebuild" explicitado com cenários concretos
  - AC-07: Volumes de estado `pipe-repo`, `pipe-logs`, `pipe-state`, `kiro-home`
    declarados no compose (validação de persistência pertence à US-04)
  - Correção: removido caminho `~/.local/share/kiro-cli/` não documentado
    oficialmente; apenas `~/.kiro/` confirmado como canônico pelo kiro-cli
  - Rastreabilidade completada (RF-05, RNF-01, RNF-03; ADR-01, ADR-02, ADR-03)
  - Escopo US-03 × US-04 × US-05 delimitado na matriz de dependências

#### Documentação de UX / Experiência do Operador
- `doc/ux/rodar-no-docker/us-03-experiencia-do-operador.md` — Documento de DX:
  persona operador, jornada "do zero ao loop rodando", benchmark de mercado
  (n8n, Metabase, Plausible, Gitea, Sentry), heurísticas de mensagens de erro
  (formato: o quê / onde / como corrigir), checklist de validação heurística
- `doc/ux/rodar-no-docker/prototipos/docker-compose.example.yml` — Protótipo
  anotado do compose com todos os blocos comentados; YAML validado; ênfase no
  valor "sem rebuild" em três pontos do arquivo
- `doc/ux/rodar-no-docker/prototipos/env.example` — Protótipo do arquivo de
  variáveis com descrição, origem e escopo de cada credencial
  (`SSH_KEY_FILE_HOST`, `GH_TOKEN`, `KIRO_API_KEY`)
- `doc/ux/rodar-no-docker/prototipos/quickstart.md` — Microtexto de onboarding
  em 4 passos para alimentar o runbook (US-06)

#### Documentação de Arquitetura
- `doc/arquitetura/rodar-no-docker/us-03-orquestracao-compose.md` — Documento
  arquitetural: modelo de injeção por natureza da entrada (config / segredo SSH /
  tokens / estado), estrutura de referência do `docker-compose.yml`, mecanismo
  "sem rebuild", rastreabilidade AC → decisão arquitetural, fronteiras de escopo
  US-03/04/05, riscos arquiteturais (RA-1..RA-4), roteiro de verificação
- `doc/arquitetura/rodar-no-docker/adr/ADR-07-orquestracao-docker-compose.md` —
  ADR-07 formalizando decisões de orquestração: serviço único, `env_file` +
  `environment:` para credenciais, Docker secret para SSH, volumes nomeados para
  estado, `PIPE_SSH_KEY_FILE` fixo no `environment:` (não no `.env`)

### Pendente (tasks em backlog — não entregues nesta etapa)

As tasks de engenharia aguardam execução sequencial:

| Task | Descrição | Status |
|------|-----------|--------|
| #37 | Criar `docker-compose.yml` na raiz com serviço, volumes, secret e envs | backlog |
| #38 | Criar `.env.example` e atualizar `.gitignore` | backlog |
| #39 | Validar `docker compose config`, `--volumes`, `git check-ignore` e aplicar bump PATCH | backlog |

> O `docker-compose.yml` canônico na raiz, o `.env.example` e o bump de versão
> PATCH serão entregues ao completar as tasks acima.

### Decisões de design registradas

- `PIPE_SSH_KEY_FILE` fixo no `environment:` do compose (valor `/run/secrets/ssh_key`),
  não no `.env` — evita redundância e ambiguidade de precedência
- Dois volumes kiro recomendados: `kiro-home` (`~/.kiro/`) obrigatório +
  `kiro-local` (`~/.local/share/kiro-cli/`) para retomada de sessão robusta
- Sem `restart`, `healthcheck` nem profiles — escopo de US-05
- Numeração de ADR canônica: diretório `doc/arquitetura/.../adr/`
  (ADR-07 é o novo; ADR-01..06 foram criados em US-01/US-02)

---

## Versões anteriores

Ver histórico de commits para alterações anteriores ao rastreamento por CHANGELOG.
