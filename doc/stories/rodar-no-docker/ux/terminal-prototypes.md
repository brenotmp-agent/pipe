# Protótipos de terminal — Saída do arranque (US-02)

Status: prototype
Owner: ux (Talita Souza)
Story: #17 (US-02)

Estes são os "wireframes" da story: como o operador percebe autenticação num
produto sem tela. Cada cena é um estado que ele pode encontrar no `docker logs`.
Prefixos seguem o formato de log atual (`[Componente] mensagem`), visto em
`src/__main__.py` (`log.info("Startup", ...)`, `log.info("Config", ...)`).

Convenções de fidelidade:
- `✓ / ✗` marcam resultado por credencial (sem cor obrigatória; degrada para
  texto puro — o adapter já roda com `KIRO_LOG_NO_COLOR=1`).
- Valores de segredo **nunca** aparecem: mostra-se origem/identidade, nunca o
  valor. Ex.: usuário do `gh`, método do kiro-cli, caminho da chave — jamais o
  token ou a chave privada.

---

## Cena A — Happy path com preflight de credenciais (PROPOSTO)

Estado-alvo. Consolida as verificações que os critérios AC-02/AC-03 já pedem
(`gh auth status`, `kiro-cli whoami`) num resumo único no arranque.

```
[Config]  Validando pipe.yml
[Config]  pipe.yml válido
[Preflight] Verificando credenciais das dependências externas...
[Preflight] ✓ SSH       chave carregada de /run/secrets/ssh_key → ~/.ssh/id_pipe
[Preflight] ✓ GitHub    gh autenticado como @operador-bot (via GH_TOKEN)
[Preflight] ✓ kiro-cli  método ativo: API key (via KIRO_API_KEY)
[Preflight] 3/3 credenciais OK — modo headless pronto
[Startup] Verificando repositórios
[Startup] Clonando main
[Loop]    Ciclo iniciado
```

Por que funciona: dá o "check verde" que hoje falta (descoberta nº 2). O
operador confirma em 3 linhas que o headless autenticou de fato, e vê a
**identidade** de cada credencial (nome do usuário gh, método do kiro) sem
nenhum valor sensível.

---

## Cena B — Falta a chave SSH (comportamento ATUAL, já bom)

`check_config()` → `_validate_env()` já falha rápido. Único ajuste: copy
Docker-aware (ver `error-copy-spec.md`).

```
[Config]  Validando pipe.yml
[Config]  ERRO Variável de ambiente 'PIPE_SSH_KEY_FILE' não definida ou vazia.
          → Em Docker: defina no serviço (env) apontando para o secret montado,
            ex. PIPE_SSH_KEY_FILE=/run/secrets/ssh_key
```
```
(container encerra com exit code 1)
```

---

## Cena C — Falta GH_TOKEN (ATUAL × PROPOSTO)

**Atual (lazy) — pior ponto da jornada:**
```
[Config]  pipe.yml válido
[Startup] Clonando main
[Loop]    Ciclo iniciado
[Board]   Sincronizando backlog
... (dezenas de linhas depois) ...
[Board]   ERRO gh: exit status 1
```
O operador vê o erro minutos depois, sem pista de que a causa foi um token
ausente definido lá no `up`.

**Proposto (preflight):**
```
[Preflight] ✓ SSH       chave carregada
[Preflight] ✗ GitHub    GH_TOKEN não definido — gh não autenticado
            Causa:  o board (GitHub Projects) exige um token para toda operação.
            Ação:   defina GH_TOKEN no .env (PAT com escopos: repo, project).
            Onde:   github.com/settings/tokens
[Preflight] 2/3 credenciais OK — arranque abortado
```
```
(container encerra com exit code 1)
```

---

## Cena D — GH_TOKEN presente mas com escopo insuficiente

Falha previsível nº 1 da jornada (fase 2). Merece mensagem própria porque a
causa ("token existe mas não pode mexer em Projects") é diferente de "ausente".

```
[Preflight] ✗ GitHub    autenticado como @operador-bot, mas sem escopo de Projects
            Causa:  o PAT não tem o escopo 'project' (só 'repo').
            Ação:   regenere o PAT incluindo 'project' e atualize GH_TOKEN.
            Onde:   github.com/settings/tokens
```

---

## Cena E — Falta / inválida KIRO_API_KEY

```
[Preflight] ✗ kiro-cli  KIRO_API_KEY não definida — agente não autenticaria
            Causa:  sem sessão de browser no container, a API key é o único
                    método de autenticação headless do kiro-cli.
            Ação:   defina KIRO_API_KEY no .env (requer plano Kiro Pro ou superior).
            Onde:   app.kiro.dev — Settings → API keys
            Nota:   em conta gerenciada por admin, a geração de key precisa
                    estar habilitada na governança (ver runbook / R-3).
```

Variante — key presente mas rejeitada (`kiro-cli whoami` falha):
```
[Preflight] ✗ kiro-cli  KIRO_API_KEY presente, mas rejeitada pelo kiro-cli
            Causa:  key inválida, revogada ou expirada.
            Ação:   gere uma nova em app.kiro.dev e atualize KIRO_API_KEY.
```

---

## Cena F — Múltiplas credenciais faltando (resumo agregado)

O preflight verifica tudo e reporta **todas** as pendências de uma vez — evita o
ciclo frustrante de corrigir uma, subir, descobrir a próxima, corrigir, subir.

```
[Preflight] ✓ SSH       chave carregada
[Preflight] ✗ GitHub    GH_TOKEN não definido
[Preflight] ✗ kiro-cli  KIRO_API_KEY não definida
[Preflight] 1/3 credenciais OK — arranque abortado
            Faltam 2: defina GH_TOKEN e KIRO_API_KEY no .env e suba novamente.
            Detalhes de cada uma acima. Guia completo: doc/runbook/docker.md
```

---

## Cena G — kiro-cli não encontrado no PATH (defesa)

Não deveria ocorrer se US-01 (imagem) estiver correta, mas o adapter já trata
(`FileNotFoundError`). Melhora de copy para não parecer erro do agente:

```
[Preflight] ✗ kiro-cli  binário 'kiro-cli' não encontrado no PATH
            Causa:  a imagem provavelmente não instalou o kiro-cli (ver US-01).
            Ação:   reconstrua a imagem; valide com 'kiro-cli --version' no build.
```

---

## Nota de implementação para Engenharia (próximo estágio)

O preflight das cenas A/C-G é a materialização das descobertas 1 e 2 do README.
Ele **não substitui** a validação lazy existente (rede de segurança), apenas a
antecipa para o arranque com um resumo. Requisitos de comportamento sugeridos:

- Verifica as três credenciais **antes** do primeiro clone/ciclo; agrega o
  resultado e falha com `exit 1` se qualquer obrigatória faltar (fail-fast).
- Usa os próprios mecanismos de verificação já previstos nos ACs: presença de
  env + `gh auth status` + `kiro-cli whoami`. Não reinventa validação.
- Nunca imprime valor de segredo — só identidade/método/caminho.
- Degradação de sessão (AC-04) permanece no loop, não no preflight.

Isto fica registrado como recomendação; a decisão de implementar (e como) é da
etapa técnica seguinte, e será submetida à validação de protótipo.
