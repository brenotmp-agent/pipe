# Change File — Documentar a operação em Docker

**Story:** #21 — Documentar a operação em Docker  
**Épico pai:** #1 — Rodar no Docker  
**Branch:** `epic21-21-documentar_a_operacao_em_docker`  
**Data:** 2026-07-22  
**Rastreabilidade:** RF-08, D-04; riscos R-3, R-4

---

## Resumo

Esta story entregou toda a documentação necessária para que um usuário novo,
sem conhecimento prévio do código, consiga colocar a esteira para rodar em
Docker seguindo apenas o guia operacional. É a última story de documentação da
feature "Rodar no Docker" (US-06) e consolida as definições materializadas nas
stories anteriores.

---

## Alterações entregues

### 1. `doc/runbook/docker.md` — Guia operacional (entregável principal)

Guia completo para operadores. Cobre todos os 6 critérios de aceitação da US-06:

| AC | Cobertura no runbook |
|----|----------------------|
| AC-01 — Pré-requisitos | Seção "Antes de começar": Docker V2, checklist de credenciais (SSH, GH_TOKEN, KIRO_API_KEY), aviso de conta gerenciada por admin (R-3) |
| AC-02 — Estrutura do docker-compose.yml | Seção "Passo a passo de subida" > Passo 2 e 3: envs, volumes, Docker secret ssh_key, referência ao .env.example |
| AC-03 — Passo a passo de subida | Passos 1–5: clone → .env → pipe.yml/contexts → build → up -d |
| AC-04 — Como verificar que está rodando | Seção dedicada: `docker compose ps`, `docker compose logs -f`, saída esperada dos rótulos de log reais (`[Config]`, `[Startup]`, `[Board]`, `[Sleep]`) |
| AC-05 — Parar e reiniciar preservando estado | Seção "Parar a esteira": `down` vs `down -v` com aviso ⛔ de ação irreversível; preservação de volumes |
| AC-06 — Rotação da KIRO_API_KEY | Seção "Rotação da KIRO_API_KEY": procedimento de 5 passos sem downtime (R-4) |

**Melhorias de UX aplicadas:**
- Estimativa de tempo (~15 min) no topo
- Índice navegável
- Seção "Antes de começar" com checklist de credenciais
- Aviso explícito para contas Kiro gerenciadas por administrador (R-3)
- Quickstart (TL;DR) para operadores com credenciais já em mãos
- Aviso ⛔ de ação irreversível no `docker compose down -v`
- Tabela de erros comuns de arranque com causa e solução

**Correção crítica aplicada:** os rótulos de log citados como "saída esperada"
foram corrigidos para bater com o código real (`__main__.py`). O rótulo
`[Main] Dormindo N segundos` **não existe**; o correto é
`[Sleep] Nenhuma atividade - dormindo Ns (retorna às HH:MM)`. Os rótulos reais
são: `Pipe`, `Config`, `Startup`, `Board`, `KeepTask`, `Sleep`.

---

### 2. `doc/architecture/rodar-no-docker/arquitetura.md` — Documentação arquitetural interna

Documentação técnica da arquitetura Docker, complementar ao runbook. Cobre:

- **Princípio de projeto** ("o simples que funciona"): único serviço no compose,
  imagem single-stage, Docker secrets + env, volumes nomeados. Documenta
  explicitamente o que foi evitado (Kubernetes, Swarm, multi-stage, Vault).
- **Visão de contexto** host × container (diagrama ASCII).
- **6 ADRs** (ADR-01 a ADR-06): autenticação headless (KIRO_API_KEY, GH_TOKEN,
  SSH), deps pinadas, usuário não-root, configuração externa.
- **Modelo de estado e persistência**: tabela de montagens (bind ro × volume
  nomeado); justificativa do volume `kiro-home` como artefato de primeira classe
  (dupla dependência `.pipe/sessions.json` ↔ SQLite `~/.kiro/`).
- **Modelo de autenticação headless**: assimetria intencional fail-fast × lazy
  confirmada contra o código (`check_config`, `_validate_env`).
- **Sequência de arranque** (diagrama de fluxo).
- **Segurança**: segredos nunca na imagem, SSH via Docker secret, usuário
  não-root, PAT de menor privilégio, rotação de KIRO_API_KEY.
- **Matriz de rastreabilidade** RF/RNF/ADR/riscos.

Todas as afirmações técnicas foram validadas contra o código real
(`src/__main__.py`, `src/core/config.py`, `src/adapters/kiro_cli_agent.py`).

---

### 3. `doc/stories/rodar-no-docker/user-stories.md` — User stories consolidadas

US-01 a US-06 com critérios de aceitação completos. A US-06 foi expandida com
os 6 ACs correspondentes aos critérios da issue #21, rastreando RF-08, D-04 e
riscos R-3/R-4. Inclui matriz de requisitos não-funcionais e ADRs.

**Correção aplicada:** AC-04 da US-06 atualizado com os rótulos de log corretos
(mesmo ajuste aplicado no runbook e na arquitetura).

---

### 4. `doc/ux/rodar-no-docker/descoberta-ux.md` — Entrevista de descoberta UX

Entrevista simulada baseada em evidências, persona ("Otávio, o operador que
acabou de chegar"), mapa da jornada as-is→to-be, benchmark (Supabase), boas
práticas e métricas de experiência.

**Correção aplicada:** risco de manutenção dos rótulos de log marcado como
resolvido após validação contra `__main__.py`.

---

### 5. `doc/ux/rodar-no-docker/arquitetura-informacao.md` — Protótipo de baixa fidelidade

Arquitetura de informação (mapa da página), wireframe anotado do runbook, fluxo
de decisão do operador e especificação de componentes de conteúdo.

**Correção aplicada:** wireframe atualizado com rótulo de log correto (`[Sleep]`
no lugar de `[Main]`).

---

## Tarefas filhas criadas (planejamento técnico)

| # | Título | Status |
|---|--------|--------|
| #42 | Validar e finalizar o runbook de operação Docker (US-06, RF-08) | Backlog (`/blocked_by #40, #41`) |

A task #42 é o único trabalho pendente desta story: validar o runbook contra os
artefatos reais (Dockerfile de #40 e docker-compose.yml de #41) quando eles
existirem. O runbook já está estruturalmente completo — o trabalho é de
validação e ajuste fino.

---

## Critérios de aceitação — status final

| AC | Status | Evidência |
|----|--------|-----------|
| AC-01 — Pré-requisitos no host | ✅ Coberto | `doc/runbook/docker.md` § "Antes de começar" |
| AC-02 — Estrutura docker-compose.yml | ✅ Coberto | `doc/runbook/docker.md` § Passo 2/3 + `doc/stories/.../user-stories.md` US-03 |
| AC-03 — Passo a passo de subida | ✅ Coberto | `doc/runbook/docker.md` § "Passo a passo de subida" (5 passos) |
| AC-04 — Como verificar que está rodando | ✅ Coberto | `doc/runbook/docker.md` § "Como verificar que está rodando" |
| AC-05 — Parar e reiniciar preservando estado | ✅ Coberto | `doc/runbook/docker.md` § "Parar a esteira" |
| AC-06 — Rotação da KIRO_API_KEY | ✅ Coberto | `doc/runbook/docker.md` § "Rotação da KIRO_API_KEY" |

**Critério de sucesso:** um usuário novo, sem conhecimento prévio do código,
pode colocar a esteira para rodar seguindo apenas `doc/runbook/docker.md`
(RF-08 e métrica de sucesso da vision).

---

## Dependências observadas

O runbook está estruturalmente completo, mas contém referências a artefatos
que ainda não existem no repositório (`Dockerfile`, `docker-compose.yml`,
`.env.example`) — entregues pelas stories US-01 (#16), US-02 (#17) e US-03
(#18). A story #18 já está concluída. A task #42 (`/blocked_by #40, #41`)
fará a validação final quando os artefatos de #16 e #17 estiverem prontos.

---

## Fora de escopo (confirmado)

- Implementação do Dockerfile, docker-compose.yml, .env.example (stories #16, #17, #18)
- Publicação de imagem em registry
- CI/CD de build
- Gestão avançada de segredos (Vault, AWS Secrets Manager)
