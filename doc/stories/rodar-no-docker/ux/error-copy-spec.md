# Especificação de copy — Mensagens de autenticação (US-02)

Status: prototype
Owner: ux (Talita Souza)
Story: #17 (US-02)

Copy é a "interface" de um produto headless. Esta spec define o padrão de
redação das mensagens que o operador lê no `docker logs`, com base nas boas
práticas de mercado (referências no README desta pasta). Conteúdo das fontes
foi reescrito para conformidade com licenciamento.

## Template de mensagem (3 partes + origem)

Toda mensagem de credencial segue a mesma estrutura, para o operador aprender o
formato uma vez e reconhecê-lo sempre:

```
✗ <credencial>  <resumo do estado numa linha>
    Causa:  por que isto impede a esteira de operar
    Ação:   o que fazer, no contexto Docker (.env / secret / compose)
    Onde:   URL para obter/corrigir a credencial
    Nota:   (opcional) pré-requisito ou ressalva
```

Regras de redação:
- **Uma linha de resumo**, sem jargão interno; enxuta (cortar palavras que não
  ajudam a corrigir).
- **Ação sempre acionável e Docker-aware**: fala em `.env`/secret/compose, nunca
  `export` no host.
- **Onde**: link direto para a origem da credencial.
- **Sem valor de segredo** em nenhuma hipótese — nem mascarado. Referência por
  nome da variável / identidade, nunca por conteúdo.
- Tom **neutro e cooperativo**: descreve o estado e o próximo passo; não culpa.

## Auditoria da copy atual

| Local (código) | Mensagem atual | Avaliação | Proposta |
|---|---|---|---|
| `config.py:_validate_env` (var ausente) | *"Variável de ambiente 'PIPE_SSH_KEY_FILE' não definida ou vazia. Defina com: export PIPE_SSH_KEY_FILE=~/.ssh/id_ed25519"* | Boa estrutura (nomeia + como corrigir), mas a dica é **host-oriented** (`export`), não Docker | Manter a 1ª frase; trocar a dica por orientação de `.env`/secret (ver M-01) |
| `config.py:_validate_env` (arquivo não existe) | *"Arquivo SSH não encontrado: `<caminho>`"* | Clara, mas sem próximo passo | Acrescentar ação: verificar o volume/secret montado (ver M-02) |
| `kiro_cli_agent.py:_run` | *"[ERRO] kiro-cli não encontrado no PATH"* | Técnica; parece erro de agente, não de setup | Reenquadrar como problema de imagem + ação (ver M-06 / cena G) |
| `kiro_cli_agent.py:_run` | *"[exit-code: N]"* cru anexado à saída | Sem tradução; operador não sabe se é auth, rede ou bug | Se a causa for auth (key ausente/inválida), emitir M-04/M-05 antes |

> A mensagem de SSH atual já acerta o mais importante segundo a pesquisa
> ([bomberbot](https://www.bomberbot.com/javascript/how-to-write-error-messages-that-dont-suck/)):
> dizer **como corrigir**. O ajuste é só de contexto (Docker), não de estrutura.

## Catálogo de mensagens propostas

### M-01 · SSH — variável ausente
```
✗ SSH  variável PIPE_SSH_KEY_FILE não definida ou vazia
    Causa:  o clone via SSH no arranque precisa saber onde está a chave privada.
    Ação:   defina PIPE_SSH_KEY_FILE no serviço apontando para o secret montado.
            ex.: PIPE_SSH_KEY_FILE=/run/secrets/ssh_key
    Onde:   monte a chave como Docker secret (ver docker-compose / runbook).
```

### M-02 · SSH — arquivo não encontrado no caminho
```
✗ SSH  arquivo de chave não encontrado em <caminho>
    Causa:  PIPE_SSH_KEY_FILE aponta para um caminho que não existe no container.
    Ação:   confira se o secret/volume da chave está montado nesse caminho.
    Onde:   seção 'secrets' do docker-compose (ver runbook).
```

### M-03 · GitHub — GH_TOKEN ausente
```
✗ GitHub  GH_TOKEN não definido — gh não autenticado
    Causa:  toda operação de board (GitHub Projects) exige um token.
    Ação:   defina GH_TOKEN no .env — PAT com escopos: repo, project.
    Onde:   github.com/settings/tokens
```

### M-04 · GitHub — escopo insuficiente
```
✗ GitHub  autenticado como @<user>, mas sem escopo de Projects
    Causa:  o PAT não inclui o escopo 'project' (necessário para mover cards).
    Ação:   regenere o PAT com 'repo' + 'project' e atualize GH_TOKEN no .env.
    Onde:   github.com/settings/tokens
```

### M-05 · kiro-cli — KIRO_API_KEY ausente
```
✗ kiro-cli  KIRO_API_KEY não definida — agente não autenticaria
    Causa:  sem sessão de browser no container, a API key é o único método
            headless do kiro-cli.
    Ação:   defina KIRO_API_KEY no .env (requer plano Kiro Pro ou superior).
    Onde:   app.kiro.dev → Settings → API keys
    Nota:   em conta gerenciada por admin, a geração de key precisa estar
            habilitada na governança (R-3).
```

### M-06 · kiro-cli — key rejeitada
```
✗ kiro-cli  KIRO_API_KEY presente, mas rejeitada
    Causa:  key inválida, revogada ou expirada.
    Ação:   gere uma nova em app.kiro.dev e atualize KIRO_API_KEY no .env.
```

### M-07 · Confirmação de sucesso (o "check verde")
```
✓ SSH       chave carregada de <caminho> → ~/.ssh/id_pipe
✓ GitHub    gh autenticado como @<user> (via GH_TOKEN)
✓ kiro-cli  método ativo: API key (via KIRO_API_KEY)
3/3 credenciais OK — modo headless pronto
```

## Microcopy — princípios rápidos

- Prefira **"defina X no .env"** a **"exporte X"** (contexto Docker).
- Use o **nome exato da variável** que o operador vai digitar (`GH_TOKEN`,
  `KIRO_API_KEY`, `PIPE_SSH_KEY_FILE`) — vira palavra-chave de busca no runbook.
- Mostre **identidade, nunca segredo**: `@user`, "método: API key", caminho da
  chave — jamais o token/chave.
- Em falhas múltiplas, **agregue** (cena F) em vez de uma-a-uma.
- Um só idioma nas mensagens (PT-BR), coerente com os logs atuais da esteira.
