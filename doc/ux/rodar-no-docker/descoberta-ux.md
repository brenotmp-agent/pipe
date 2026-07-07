# Descoberta UX — Documentação da operação em Docker

Status: draft
Owner: ux (Talita Souza)
Etapa: Prototipação
Last updated: 2026-07-07

Rastreabilidade: RF-08, D-04; riscos R-3, R-4. Story US-06
(`doc/stories/rodar-no-docker/user-stories.md`). Complementa — não substitui — o
runbook em `doc/runbook/docker.md`.

---

## 1. Objetivo desta etapa

A documentação já foi escrita (runbook + user stories). Meu papel de UX na
Prototipação não é reescrever o conteúdo técnico, e sim **projetar a experiência
de leitura e execução** desse guia: garantir que um operador novo, sem
conhecimento do código, consiga sair do zero até "esteira rodando" com o mínimo
de atrito, dúvidas e retrabalho.

O produto aqui é **a própria documentação**. Portanto o objeto de design é:
arquitetura da informação, sequência de tarefas, pontos de decisão, prevenção e
recuperação de erros, e sinais de progresso/sucesso.

---

## 2. Entrevista com o usuário (discovery)

O fluxo agêntico não permite uma entrevista síncrona com uma pessoa real. Para
não bloquear a etapa, conduzi a descoberta como uma **entrevista simulada
baseada em evidências**: as perguntas que eu faria a um operador, respondidas a
partir das fontes já validadas do projeto (`vision.md`, `problem-space.md`,
`epicos.md`, `user-stories.md`, `README.md`) e do comportamento real do código.
As respostas marcadas como **[SUPOSIÇÃO]** precisam de confirmação humana e
estão consolidadas na seção 8 (Lacunas).

**P1. Quem é você e por que quer rodar a esteira em Docker?**
> Sou analista/operador. Quero rodar a esteira em qualquer host (servidor,
> nuvem, minha máquina) sem preparar o ambiente à mão. Fonte: `vision.md`
> (público-alvo e proposta de valor).

**P2. Qual seu nível com Docker?**
> Sei o básico: instalar Docker, rodar `docker compose up`, ler logs. Não quero
> aprender arquitetura interna para colocar no ar. Fonte: critério de sucesso da
> US-06 ("sem conhecimento prévio do código").

**P3. Em que momento você desiste ou trava hoje?**
> Nos segredos: gerar `KIRO_API_KEY` (ainda mais em conta gerenciada por admin),
> montar a chave SSH, e descobrir se o container subiu de verdade. Fonte:
> `problem-space.md` (setup manual de credenciais) + riscos R-3/R-4.

**P4. Como você sabe que "deu certo"?**
> Preciso ver nos logs que o loop começou a rodar sem erro de credencial. Fonte:
> AC-04 da US-06.

**P5. O que te dá segurança para parar e voltar depois?**
> Saber, sem ambiguidade, qual comando preserva o estado e qual apaga tudo.
> Fonte: AC-05 (diferença `down` vs `down -v`).

**P6. Onde você espera encontrar essa informação?**
> No repositório, num único documento, com passos copiáveis e um índice no topo.
> **[SUPOSIÇÃO]** sobre o formato de entrega preferido (página única vs. dividido).

**P7. Você vai operar sozinho ou em equipe?**
> **[SUPOSIÇÃO]** — não confirmado. Impacta se vale a pena um "modo produção"
> (secrets manager, múltiplos operadores). Escopo atual assume operador único.

---

## 3. Persona primária

**"Otávio, o operador que acabou de chegar"**

| Atributo | Descrição |
|----------|-----------|
| Papel | Analista/operador de infraestrutura leve |
| Contexto | Recebeu a tarefa de "colocar a esteira no ar" num host novo |
| Conhecimento | Docker básico; **nenhum** conhecimento do código da esteira |
| Ferramentas | Terminal, editor de texto, conta GitHub, conta Kiro |
| Objetivo | Do `git clone` até "loop rodando" sem pedir ajuda |
| Frustrações | Segredos espalhados, erros crípticos no arranque, medo de apagar estado |
| Métrica de sucesso | Sobe a esteira seguindo **apenas** o guia (métrica da vision) |

Persona secundária: **operador que retorna** — já subiu antes, volta para
reiniciar, rotacionar a `KIRO_API_KEY` ou diagnosticar uma parada. Otimiza por
velocidade e por não perder estado.

---

## 4. Mapa da jornada (as-is → to-be)

| Fase | Tarefa do operador | Emoção (as-is) | Risco de atrito | Alavanca de UX (to-be) |
|------|--------------------|----------------|-----------------|------------------------|
| 1. Preparar | Verificar Docker, Git | 😐 neutro | Versão errada do compose (V1 vs V2) | Checklist de pré-requisitos com comando de verificação e saída esperada |
| 2. Credenciais | Gerar SSH, PAT, `KIRO_API_KEY` | 😟 ansioso | R-3: admin bloqueia API key; escopos errados do PAT | Bloco "Reúna antes de começar" + aviso destacado de conta gerenciada |
| 3. Configurar | `.env`, `pipe.yml`, `contexts/` | 😕 confuso | Editar arquivo errado; commitar segredo | `.env.example` + aviso de `.gitignore`; separar "obrigatório" de "opcional" |
| 4. Subir | `build` + `up -d` | 🙂 esperançoso | Build longo sem feedback | Indicar tempo esperado e que o build é único |
| 5. Verificar | Ler logs, confirmar loop | 😰 inseguro | Não saber se "está ok" | Log de referência anotado + tabela sintoma→causa→solução |
| 6. Operar | Parar/reiniciar/rotacionar | 😨 receoso | Apagar estado com `down -v` | Aviso de destrutivo + tabela do que cada volume preserva |

O maior vale emocional está nas fases 2 e 5 (credenciais e verificação). São os
pontos onde a documentação precisa de mais cuidado de UX.

---

## 5. Referências de mercado (benchmark)

Analisei guias de self-hosting em Docker de produtos de referência e a
literatura de documentação para desenvolvedores.

- **Supabase — Self-Hosting with Docker.** Abre com estimativa de tempo
  ("menos de 15 minutos"), um **índice/Contents** navegável no topo, e uma seção
  **"Before you begin"** que declara pré-requisitos e o nível esperado do leitor.
  Oferece dois caminhos: **Quick start** (um comando) e **Manual**. Separa
  claramente "Starting and stopping" e um "Uninstalling" com aviso destacado de
  perda de dados. Fonte:
  [supabase.com/docs/guides/self-hosting/docker](https://supabase.com/docs/guides/self-hosting/docker).
  Conteúdo reescrito para conformidade de licenciamento.
- **Padrões de onboarding de dev docs.** A literatura converge em: um caminho de
  **quick-start** que leva ao primeiro sucesso em poucos minutos, **how-to
  guides** para tarefas reais, e **runbooks/troubleshooting** para operar e
  recuperar. Cada bloco deve ser explícito sobre comandos, premissas de ambiente
  e resultado esperado. Fontes:
  [techbuzzonline.com](https://techbuzzonline.com/developer-technical-writing-guide/)
  e [infrasity.com](https://www.infrasity.com/blog/product-documentation-best-practices).
  Conteúdo rephrasado para conformidade.

### O que trazer para o nosso guia

1. **Estimativa de tempo no topo** — calibra expectativa e reduz abandono.
2. **Índice navegável (Contents)** — o operador se localiza e pula direto ao
   ponto (ex.: quem volta só quer "Rotação da KIRO_API_KEY").
3. **"Antes de começar"** com pré-requisitos e nível esperado.
4. **Quickstart TL;DR** para quem já tem as credenciais em mãos.
5. **Seção destrutiva com aviso visual forte** (o `down -v` é o nosso
   equivalente ao "Uninstalling").

Conteúdo das fontes externas foi rephrasado para conformidade com restrições de
licenciamento.

---

## 6. Boas práticas de UX aplicadas à documentação

Princípios de referência aplicados ao runbook (heurísticas de usabilidade +
literatura de dev docs):

1. **Visibilidade do estado do sistema** → toda ação mostra o *resultado
   esperado* (saída de comando, linhas de log).
2. **Reconhecer em vez de lembrar** → comandos copiáveis e completos; nada de
   "configure a variável X" sem mostrar onde e como.
3. **Prevenção de erro** → avisos *antes* da ação destrutiva/irreversível
   (`down -v`, commit de segredo), não depois.
4. **Ajuda a reconhecer e recuperar de erros** → tabela sintoma → causa →
   solução na verificação.
5. **Divulgação progressiva** → caminho feliz primeiro; detalhes avançados
   (rotação, reset) depois, sem poluir o fluxo principal.
6. **Consistência** → sempre `docker compose` (V2), sempre o mesmo formato de
   passo (comando → o que esperar).
7. **Flexibilidade (atalhos)** → Quickstart TL;DR para o usuário experiente sem
   penalizar o iniciante.
8. **Estética e design minimalista** → cada passo carrega só o necessário para
   executá-lo.

---

## 7. Métricas de sucesso da experiência (verificáveis)

- **Time-to-first-run:** operador novo do `clone` ao loop rodando sem sair do
  guia. Meta de referência: **≤ 15 min** (excluindo o build da imagem).
- **Zero perguntas fora do guia:** nenhuma dúvida exige ler o código-fonte
  (critério de sucesso da US-06).
- **Recuperação autônoma:** todo erro de arranque tem entrada na tabela de
  troubleshooting.
- **Segurança de estado:** nenhuma perda acidental de estado por confundir
  `down` com `down -v`.

---

## 8. Lacunas / dúvidas para validação humana

Nenhuma bloqueia a entrega da prototipação, mas afetam refinamentos:

1. **[SUPOSIÇÃO] Formato de entrega:** página única (atual) vs. guia dividido
   (quickstart + referência). Recomendo manter **página única com índice**
   enquanto o guia couber numa leitura; dividir só se crescer.
2. **[SUPOSIÇÃO] Operador único vs. equipe:** se houver operação em equipe/
   produção, abre espaço para um "modo produção" (secrets manager) — hoje fora
   de escopo da US-06.
3. **Nomes exatos das linhas de log:** o runbook cita `[Config] pipe.yml
   válido`, `[Board] Sincronizando…`, `[Main] Dormindo N segundos`. Esses
   rótulos precisam bater com a implementação real de US-01…US-05 quando
   mergeada. Registrado como risco de manutenção no protótipo.

---

## 9. Entregáveis desta etapa

1. Este documento de descoberta (`descoberta-ux.md`).
2. Arquitetura de informação + wireframe anotado do runbook
   (`arquitetura-informacao.md`).
3. Aplicação das melhorias no runbook `doc/runbook/docker.md` (índice,
   estimativa de tempo, "antes de começar", quickstart TL;DR, avisos
   destrutivos, tabelas de verificação) — mantendo o conteúdo técnico validado.

— Talita Souza - User Experience
