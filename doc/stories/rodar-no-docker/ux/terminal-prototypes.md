# Terminal Prototypes — Preflight de Credenciais

Status: definido
Owner: UX/produto
Last updated: 2026-07-22
Contexto: US-02, ADR-04

Protótipos de saída de terminal para os cenários de preflight. Servem como
especificação de UX para a implementação de `src/core/preflight.py`.

---

## Cena A — Happy path (3/3 OK)

Todas as credenciais presentes e válidas. Sequência completa de boot.

```
[Config]    Validando pipe.yml
[Config]    pipe.yml válido
[Startup]   Verificando repositórios
[Preflight] Verificando credenciais das dependências externas...
[Preflight] ✓ SSH       chave carregada de /run/secrets/ssh_key → ~/.ssh/id_pipe
[Preflight] ✓ GitHub    gh autenticado como @brenotmp-agent (via GH_TOKEN)
[Preflight] ✓ kiro-cli  método ativo: API key (via KIRO_API_KEY)
[Preflight] 3/3 credenciais OK — modo headless pronto
[Startup]   Clonando main
```

---

## Cena B — GH_TOKEN ausente (1 falha)

```
[Config]    Validando pipe.yml
[Config]    pipe.yml válido
[Startup]   Verificando repositórios
[Preflight] Verificando credenciais das dependências externas...
[Preflight] ✓ SSH       chave carregada de /run/secrets/ssh_key → ~/.ssh/id_pipe
[Preflight] ✗ GitHub    GH_TOKEN não definido
             Causa:     variável de ambiente GH_TOKEN ausente
             Ação:      defina GH_TOKEN com um token válido do GitHub
             Onde:      docker-compose.yml → environment → GH_TOKEN
[Preflight] ✓ kiro-cli  método ativo: API key (via KIRO_API_KEY)
[Preflight] 2/3 credenciais OK — arranque abortado
```

---

## Cena C — KIRO_API_KEY ausente (1 falha)

```
[Preflight] Verificando credenciais das dependências externas...
[Preflight] ✓ SSH       chave carregada de /run/secrets/ssh_key → ~/.ssh/id_pipe
[Preflight] ✓ GitHub    gh autenticado como @brenotmp-agent (via GH_TOKEN)
[Preflight] ✗ kiro-cli  KIRO_API_KEY não definido
             Causa:     variável de ambiente KIRO_API_KEY ausente
             Ação:      defina KIRO_API_KEY com uma API key válida do Kiro
             Onde:      docker-compose.yml → environment → KIRO_API_KEY
[Preflight] 2/3 credenciais OK — arranque abortado
```

---

## Cena D — gh com escopo `project` faltando

```
[Preflight] ✗ GitHub    token sem escopo 'project'
             Causa:     GH_TOKEN definido mas sem permissão de projects
             Ação:      gere um novo token com escopo 'project' habilitado
             Onde:      https://github.com/settings/tokens
```

---

## Cena E — GH_TOKEN inválido (token rejeitado)

```
[Preflight] ✗ GitHub    token inválido ou expirado
             Causa:     gh auth status retornou erro: "token is invalid"
             Ação:      verifique se GH_TOKEN está correto e não expirou
             Onde:      docker-compose.yml → environment → GH_TOKEN
```

---

## Cena F — Múltiplas falhas (GH_TOKEN + KIRO_API_KEY ausentes)

O preflight verifica todas as três antes de abortar.

```
[Preflight] Verificando credenciais das dependências externas...
[Preflight] ✓ SSH       chave carregada de /run/secrets/ssh_key → ~/.ssh/id_pipe
[Preflight] ✗ GitHub    GH_TOKEN não definido
             Causa:     variável de ambiente GH_TOKEN ausente
             Ação:      defina GH_TOKEN com um token válido do GitHub
             Onde:      docker-compose.yml → environment → GH_TOKEN
[Preflight] ✗ kiro-cli  KIRO_API_KEY não definido
             Causa:     variável de ambiente KIRO_API_KEY ausente
             Ação:      defina KIRO_API_KEY com uma API key válida do Kiro
             Onde:      docker-compose.yml → environment → KIRO_API_KEY
[Preflight] 1/3 credenciais OK — arranque abortado
```

---

## Cena G — kiro-cli fora do PATH

```
[Preflight] ✗ kiro-cli  binário não encontrado
             Causa:     kiro-cli não está instalado ou não está no PATH
             Ação:      instale o kiro-cli ou verifique o Dockerfile
             Onde:      imagem Docker (PATH)
```

---

## Notas de implementação

- Símbolo `✓` para sucesso, `✗` para falha — usar literalmente no log.
- Linhas de detalhe (Causa / Ação / Onde) são emitidas como linhas de log
  separadas com recuo para legibilidade.
- O número `N/3` no resumo final reflete quantas das três tiveram sucesso.
- **Nunca** imprimir valores de segredo — apenas nome de variável, identidade
  (`@user`) ou método.
- `kiro-cli whoami` é o subcomando correto (confirmado 2026-07-22); não existe
  `kiro-cli auth status`.
- `gh auth status` com exit 0 = autenticado; exit ≠ 0 = falha (independente
  do conteúdo da saída, que pode listar múltiplas contas).
