# Arquitetura de Informação & Wireframe — Runbook Docker

Status: draft
Owner: ux (Talita Souza)
Etapa: Prototipação
Last updated: 2026-07-07

Protótipo (baixa fidelidade) da experiência do guia `doc/runbook/docker.md`.
Como o produto é documentação em texto, o "protótipo" é a **estrutura navegável
+ wireframe anotado** que a versão final do runbook implementa. Ver decisões em
`descoberta-ux.md`.

---

## 1. Arquitetura de informação (mapa da página)

Ordenada pela jornada do operador (feliz primeiro, avançado depois):

```
Runbook — Rodar a esteira em Docker
│
├── [Cabeçalho]
│    ├── Para quem é este guia (1 linha)
│    └── ⏱ Tempo estimado: ~15 min (fora o build da imagem)
│
├── 0. Índice (Contents)            ← navegação; âncoras clicáveis
│
├── 1. Antes de começar
│    ├── O que você precisa saber (nível esperado)
│    ├── Pré-requisitos no host      (tabela: requisito → como verificar)
│    └── Credenciais a reunir ANTES  (SSH · GH_TOKEN · KIRO_API_KEY)
│         └── ⚠ Conta gerenciada por admin (R-3)
│
├── 2. Quickstart (TL;DR)           ← atalho p/ quem já tem credenciais
│    └── bloco único de comandos, do clone ao up -d
│
├── 3. Passo a passo detalhado      ← caminho feliz, 5 passos
│    └── cada passo: comando → o que esperar
│
├── 4. Verificar que está rodando
│    ├── Status do container
│    ├── Log de referência (arranque saudável, anotado)
│    └── ⚠ Sinais de problema  (tabela sintoma → causa → solução)
│
├── 5. Parar e reiniciar (preservar estado)
│    ├── Parar preservando estado    (down)
│    ├── Tabela: o que cada volume preserva
│    └── ⛔ Destruir o estado         (down -v — bloco de aviso forte)
│
├── 6. Rotação da KIRO_API_KEY (R-4)
│
└── 7. Referências
```

### Justificativa da ordem

- **Antes de começar** primeiro evita o erro nº1: começar sem as credenciais e
  travar no meio (vale emocional da jornada, seção 4 da descoberta).
- **Quickstart antes do passo a passo** dá atalho ao usuário que volta sem
  atrapalhar o novato (heurística: flexibilidade + divulgação progressiva).
- **Verificar** logo após subir responde "e agora, deu certo?" no momento exato
  da dúvida (visibilidade do estado do sistema).
- **Destrutivo por último e destacado** (o `down -v`), espelhando o
  "Uninstalling" isolado da referência Supabase.

---

## 2. Wireframe anotado (baixa fidelidade)

Anotações UX marcadas com ⟦…⟧.

```
┌───────────────────────────────────────────────────────────────┐
│  Runbook — Rodar a esteira em Docker                            │
│  Para analista/operador sem conhecimento do código.            │
│  ⏱ ~15 min (fora o build)          ⟦calibra expectativa⟧        │
├───────────────────────────────────────────────────────────────┤
│  CONTEÚDO                          ⟦âncoras; quem volta pula⟧    │
│  1·Antes de começar  2·Quickstart  3·Passo a passo              │
│  4·Verificar  5·Parar/reiniciar  6·Rotação  7·Referências      │
├───────────────────────────────────────────────────────────────┤
│  1 · ANTES DE COMEÇAR                                           │
│  ┌─ Pré-requisitos no host ───────────────────────────────┐    │
│  │ Requisito            │ Como verificar                   │    │
│  │ docker compose V2    │ docker compose version           │    │
│  │ git                  │ git --version                    │    │
│  └──────────────────────────────────────────────────────┘    │
│  📋 Reúna ANTES de começar:        ⟦checklist previne trava⟧    │
│    ☐ chave SSH   ☐ GH_TOKEN   ☐ KIRO_API_KEY                   │
│  ⚠ Conta gerenciada? admin precisa habilitar API key (R-3)     │
├───────────────────────────────────────────────────────────────┤
│  2 · QUICKSTART (já tenho as credenciais)  ⟦atalho experiente⟧  │
│  ┌───────────────────────────────────────────────────────┐    │
│  │ git clone … && cd pipe                                 │    │
│  │ cp .env.example .env   # preencha os 3 segredos        │    │
│  │ docker compose build && docker compose up -d           │    │
│  │ docker compose logs -f                                 │    │
│  └───────────────────────────────────────────────────────┘    │
├───────────────────────────────────────────────────────────────┤
│  3 · PASSO A PASSO           ⟦cada passo: comando→esperar⟧      │
│   1 Clonar → 2 .env → 3 pipe.yml/contexts → 4 build → 5 up      │
├───────────────────────────────────────────────────────────────┤
│  4 · VERIFICAR QUE ESTÁ RODANDO                                 │
│  docker compose ps            → STATUS: Up   ⟦resultado visível⟧ │
│  ┌─ log de arranque saudável (referência) ──────────────┐      │
│  │ [Config] pipe.yml válido                              │      │
│  │ [Board] Sincronizando…                                │      │
│  │ [Sleep] Nenhuma atividade - dormindo 60s ← loop ocioso│      │
│  └───────────────────────────────────────────────────────┘    │
│  ⚠ Sinais de problema  (sintoma → causa → solução)             │
├───────────────────────────────────────────────────────────────┤
│  5 · PARAR E REINICIAR                                          │
│  down   → preserva volumes   ⟦o esperado 90% das vezes⟧         │
│  ┌ o que cada volume preserva (tabela) ┐                        │
│  ╔═══════════════════════════════════════════════════════╗    │
│  ║ ⛔ down -v  APAGA TODO O ESTADO   ⟦bloco de alto risco⟧ ║    │
│  ╚═══════════════════════════════════════════════════════╝    │
├───────────────────────────────────────────────────────────────┤
│  6 · ROTAÇÃO DA KIRO_API_KEY   ⟦tarefa de quem volta⟧           │
│  7 · REFERÊNCIAS                                                │
└───────────────────────────────────────────────────────────────┘
```

---

## 3. Fluxo de decisão do operador (protótipo de navegação)

```
            ┌─────────────────────────┐
            │  Quero rodar a esteira  │
            └───────────┬─────────────┘
                        ▼
            ┌─────────────────────────┐   não   ┌────────────────────┐
            │ Já tenho SSH+GH+KIRO?   ├────────▶│ 1 · Antes de começar│
            └───────────┬─────────────┘         │ (reúna credenciais) │
                    sim │                        └─────────┬──────────┘
                        ▼                                  │
            ┌─────────────────────────┐                    │
            │ 2 · Quickstart (TL;DR)  │◀───────────────────┘
            └───────────┬─────────────┘
                        ▼
            ┌─────────────────────────┐  erro   ┌────────────────────┐
            │ 4 · Verificar (logs)    ├────────▶│ Tabela sintoma→ação │
            └───────────┬─────────────┘         └─────────┬──────────┘
                    ok  │                                  │ corrige
                        ▼                                  └────► volta a subir
            ┌─────────────────────────┐
            │  Esteira rodando 🎉     │
            └───────────┬─────────────┘
                        ▼
        ┌──────────────────────────────────┐
        │ Depois: 5 · parar/reiniciar        │
        │        6 · rotacionar KIRO_API_KEY │
        └──────────────────────────────────┘
```

---

## 4. Especificação de componentes de conteúdo

Padrões reutilizáveis que a versão final do runbook deve seguir:

| Componente | Regra de UX |
|------------|-------------|
| **Passo** | `### N. Título` → comando em bloco → frase "o que esperar" |
| **Comando** | Sempre copiável e completo; nunca fragmento ("configure X") |
| **Callout ⚠** | Antes da ação de risco, nunca depois |
| **Callout ⛔** | Reservado a ações irreversíveis (`down -v`) |
| **Tabela sintoma→causa→solução** | 3 colunas fixas; 1 linha por erro conhecido |
| **Checklist ☐** | Para reunir insumos (credenciais) antes de agir |
| **Estimativa ⏱** | No topo; separa build (uma vez) do restante |

---

## 5. Handoff para a implementação/refino

- A versão final do runbook (`doc/runbook/docker.md`) já foi ajustada nesta
  etapa para materializar esta AI: índice, estimativa de tempo, "antes de
  começar" com checklist, quickstart TL;DR e aviso destrutivo destacado.
- **Risco de manutenção (resolvido em 2026-07-20):** os rótulos de log
  (`[Config]`, `[Board]`, `[Sleep]`) foram conferidos contra o runtime existente
  (`__main__.py`) na etapa de arquitetura. Rótulos reais: `Pipe`, `Config`,
  `Startup`, `Board`, `KeepTask`, `Sleep` — não existe `[Main]`. Docs corrigidos.
- **Fora de escopo agora:** dividir em múltiplas páginas, "modo produção" com
  secrets manager, e vídeo walkthrough (candidatos a evolução futura, ver
  benchmark na descoberta).

— Talita Souza - User Experience
