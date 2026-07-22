# ADR-04 — Preflight de credenciais no arranque (fail-fast) + lazy como salvaguarda

Status: Aceito
Data: 2026-07-07
Atualizado: 2026-07-22
Story: US-02 (#17)
Contexto relacionado: AC-06, cenas A/C-G de `terminal-prototypes.md`

## Contexto

A validação de credenciais é hoje **assimétrica** (documentado em AC-06):

| Credencial | Validada no arranque? | Falta → |
|---|---|---|
| `PIPE_SSH_KEY_FILE` | Sim (`_validate_env`) | `exit 1` claro |
| `GH_TOKEN` | Não — lazy | falha na 1ª op. de board, no meio do loop |
| `KIRO_API_KEY` | Não — lazy | falha na 1ª execução de agente |

Para um container autônomo, a falha lazy aparece tarde e enterrada nos logs. O
operador dá `up`, vê o log correr como se tudo estivesse bem, e só minutos
depois descobre que faltou um token — sem conseguir correlacionar o erro tardio
com a causa. A prototipação de UX marcou isto como o pior ponto da jornada
(descobertas 1 e 2; cenas A/C-G de `terminal-prototypes.md`), e recomendou um
preflight — alinhado ao padrão de mercado *fail-fast no arranque* e
*doctor/preflight* (`gh auth status`, `flutter doctor`).

## Decisão

Adotar um **preflight de credenciais** implementado em `src/core/preflight.py`
que verifica as três credenciais de uma vez, **antes do primeiro ciclo**, agrega
o resultado e falha rápido (`exit 1`) se qualquer obrigatória faltar. O preflight
**complementa** e não substitui a validação lazy — esta permanece como rede de
segurança para credenciais que expirem/sejam revogadas em runtime.

Contrato:

- Verifica SSH (presença + arquivo), `gh` (`gh auth status`) e kiro-cli
  (`kiro-cli whoami` — subcomando confirmado na versão instalada).
- **Agrega** todas as pendências num relatório único (não uma-a-uma).
- Emite confirmação positiva no caminho feliz (`3/3 credenciais OK`).
- **Nunca** imprime valor de segredo — só nome de variável, identidade
  (`@user`) ou método.
- Copy conforme `doc/stories/rodar-no-docker/ux/error-copy-spec.md`
  (Docker-aware, causa/ação/onde).
- A degradação graciosa de sessão (R-1) permanece no loop, fora do preflight.

## Alternativas consideradas

- **Manter só lazy (status quo)** — menor código, mas mantém o pior ponto da
  jornada; falha tardia e não correlacionável. Descartado.
- **Mover tudo para validação no arranque, removendo o lazy** — perde a rede de
  segurança contra expiração/revogação em runtime. Descartado; preflight +
  lazy é mais robusto.
- **Preflight completo com testes de escopo (detecção de `project` faltante)**
  — 1 chamada extra ao `gh`. Recomendado (cena D); a Engenharia pode optar por
  implementar ou deixar para o lazy, não é bloqueador para fechar a US-02.

## Consequências

- (+) Fecha o pior ponto de UX: falha rápida, agregada, correlacionável, com
  confirmação positiva de sucesso.
- (+) Evolui a assimetria de AC-06 para um comportamento uniforme no arranque,
  sem perder a salvaguarda lazy.
- (−) Adiciona um componente novo (`preflight()`) e 2 chamadas externas no
  arranque (`gh auth status`, `kiro-cli whoami`). Custo baixo, uma vez por boot.

## Fontes

Pacote UX: `doc/stories/rodar-no-docker/ux/` (terminal-prototypes.md,
error-copy-spec.md). Padrões de mercado citados no README do UX (fail-fast,
doctor/preflight). Conteúdo reescrito para conformidade com licenciamento.
