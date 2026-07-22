# ADR-05 — Usuário não-root: pipe (uid 1000)

Status: aprovado
Owner: arquitetura
Last updated: 2026-07-22
Autora: Rafael Martins — Analista de Requisitos

---

## Contexto

Por padrão, containers Docker executam como `root`. Isso é um risco de
segurança: se houver vulnerabilidade no processo, o atacante obtém acesso root
ao sistema de arquivos do container. Além disso, o kiro-cli precisa de um
diretório `$HOME` gravável para persistir estado de sessão, e o `_setup_ssh`
escreve em `~/.ssh/`.

## Decisão

Criar o usuário `pipe` (uid 1000) com home `/home/pipe` e executar o container
com esse usuário.

```dockerfile
RUN useradd --create-home --uid 1000 pipe
WORKDIR /app
RUN chown pipe:pipe /app
USER pipe
```

## Justificativa

- **Segurança**: processo não-root limita o impacto de uma exploração.
- **Compatibilidade**: `_setup_ssh` escreve em `~/.ssh/`; o kiro-cli escreve
  estado de sessão em `~/`. Ambos funcionam com `/home/pipe` gravável.
- **uid 1000**: é o uid padrão do primeiro usuário comum em sistemas Linux.
  Evita colisão com UIDs de sistema (< 1000).
- **HOME gravável**: o `--create-home` garante que `/home/pipe` existe e é
  gravável pelo usuário `pipe`.

## Implicações para o PATH do kiro-cli

O `install.sh` do kiro-cli instala o binário em `~/.local/bin/kiro-cli`
(i.e., `/home/pipe/.local/bin/kiro-cli`). A camada de instalação do kiro-cli
(camada 6) é executada **antes** da declaração do `ENV PATH` (camada 7).

Para o smoke test na camada 6 (`kiro-cli --version`) funcionar, o binário deve
ser referenciado pelo **caminho absoluto**:

```dockerfile
RUN ... && ~/.local/bin/kiro-cli --version
```

O `ENV PATH=/home/pipe/.local/bin:$PATH` na camada 7 garante que nas camadas
seguintes e em runtime o binário seja acessível via `kiro-cli` diretamente.

## Implicações para o docker-compose.yml

Com o usuário `pipe` (home `/home/pipe`), os volumes do compose que montam
credenciais devem usar os caminhos corretos:

| Volume | Path no container |
|--------|-------------------|
| Chave SSH | `/home/pipe/.ssh/id_ed25519` |
| Config gh | `/home/pipe/.config/gh` |

A variável de ambiente `PIPE_SSH_KEY_FILE` deve apontar para
`/home/pipe/.ssh/id_ed25519`.

> A atualização do `docker-compose.yml` é escopo da issue #41.

## Consequências

- O processo dentro do container é `pipe` (uid 1000), não `root`.
- `/app` pertence ao usuário `pipe` (via `chown pipe:pipe /app`).
- O `WORKDIR /app` é definido após a criação do usuário para que o `chown`
  seja aplicável.
- Arquivos copiados com `--chown=pipe:pipe` na camada de código pertencem
  ao usuário correto.
