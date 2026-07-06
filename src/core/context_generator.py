"""Gerador de CONTEXT.md — instrui agentes sobre regras e estrutura do sistema.

Gerado automaticamente no startup a partir do pipe.yml. O arquivo resultante
é incluído no prompt de cada execução do agente, prevenindo comportamentos
implícitos (ex: incidente Issue Fantasma).

Arquivo gerado: .pipe/CONTEXT.md
Regra de regeneração: recria se não existir OU se pipe.yml for mais novo.
"""

from pathlib import Path

CONTEXT_PATH = Path(".pipe") / "CONTEXT.md"
PIPEYML_PATH = Path("pipe.yml")

# Arquivos internos da esteira que o agente NUNCA deve tocar
_PROTECTED_FILES = [
    ".pipe/boards/*/snapshot.json",
    ".pipe/changeQueue.json",
    ".pipe/throttle.json",
    ".pipe/throttle",
    ".pipe/sessions.json",
]


def _needs_regeneration() -> bool:
    """Retorna True se o CONTEXT.md precisa ser (re)criado."""
    if not CONTEXT_PATH.exists():
        return True
    if not PIPEYML_PATH.exists():
        return False
    return PIPEYML_PATH.stat().st_mtime > CONTEXT_PATH.stat().st_mtime


def _section_restrictions() -> list[str]:
    """Seção de arquivos protegidos."""
    lines = [
        "## Restrições de sistema (NÃO VIOLAR)",
        "",
        "Os arquivos abaixo são memória interna da esteira. "
        "NUNCA leia, escreva, crie ou modifique esses arquivos protegidos:",
        "",
    ]
    for path in _PROTECTED_FILES:
        lines.append(f"- `{path}`")
    lines += [
        "",
        "Qualquer escrita nesses arquivos corrompe o estado da esteira e causa "
        "comportamentos imprevisíveis em toda a pipeline.",
        "",
    ]
    return lines


def _section_issue_naming() -> list[str]:
    """Seção de convenções de nomeação de issues."""
    return [
        "## Criação de issues",
        "",
        "Ao criar uma nova issue em um board, crie APENAS os seguintes arquivos:",
        "",
        "- `<slug>-body.md`",
        "- `<slug>-history.md` (opcional, pode ser vazio)",
        "- `<slug>-addcomment.md` (opcional)",
        "",
        "### Regras de nomeação (sem prefixo numérico)",
        "",
        "NÃO prefixe o nome com números.",
        "O padrão errado seria algo como `4-login-body.md` — isso está errado.",
        "O ID real é atribuído pelo GitHub após o sync; antes disso o arquivo "
        "não tem e não deve ter prefixo numérico.",
        "",
        "**Correto:** `implementar-login-body.md`",
        "**Errado:** `4-implementar-login-body.md`",
        "",
        "NÃO escreva IDs numéricos no nome do arquivo.",
        "",
    ]


def _section_boards(config: dict) -> list[str]:
    """Seção de boards e colunas derivada do pipe.yml."""
    lines = [
        "## Boards e colunas",
        "",
        "Estrutura de boards e colunas configurada no pipe.yml:",
        "",
    ]
    boards_cfg = config.get("boards", {})
    for board_id, board in boards_cfg.items():
        if board_id == "platform":
            continue
        if not isinstance(board, dict):
            continue
        board_name = board.get("name", board_id)
        board_flow = board.get("flow", "—")
        lines += [
            f"### Board: {board_name} (id: `{board_id}`)",
            "",
            f"- **Flow:** `{board_flow}`",
            "",
            "| Coluna (id) | Nome | Agente |",
            "|-------------|------|--------|",
        ]
        for col_id, col in board.get("columns", {}).items():
            if not isinstance(col, dict):
                continue
            col_name = col.get("name", col_id)
            agent = col.get("agent", "—")
            lines.append(f"| `{col_id}` | {col_name} | {agent} |")
        lines.append("")
    return lines


def _section_branches(config: dict) -> list[str]:
    """Seção de git flow e prefixos de branch."""
    lines = [
        "## Git flow e branches",
        "",
        "Flows disponíveis e seus prefixos de branch:",
        "",
        "| Flow | Prefixo | Origem | Merge em |",
        "|------|---------|--------|----------|",
    ]
    flow_cfg = config.get("git", {}).get("flow", {})
    base = flow_cfg.get("base", "main")
    for flow_id, flow in flow_cfg.items():
        if flow_id == "base" or not isinstance(flow, dict):
            continue
        prefix = flow.get("prefix", "—")
        create = flow.get("create", base)
        merge = flow.get("merge", base)
        lines.append(f"| `{flow_id}` | `{prefix}` | `{create}` | `{merge}` |")
    lines += [
        "",
        f"Branch base: `{base}`",
        "",
        "Ao criar uma branch, use o prefixo correspondente ao flow do board.",
        "Exemplo: flow `feature` → branch `feature/<id>-<slug>`.",
        "",
    ]
    return lines


def generate_context(config: dict) -> None:
    """Gera .pipe/CONTEXT.md a partir do config se necessário.

    Cria o arquivo se não existir. Regenera se pipe.yml foi modificado
    após o CONTEXT.md. Não sobrescreve se o CONTEXT.md já estiver atualizado.
    """
    if not _needs_regeneration():
        return

    CONTEXT_PATH.parent.mkdir(parents=True, exist_ok=True)

    sections: list[str] = [
        "# Contexto do sistema — gerado automaticamente",
        "",
        "Este arquivo é gerado pelo startup da esteira a partir do `pipe.yml` "
        "e incluído no prompt de cada execução do agente.",
        "**Não edite manualmente** — será sobrescrito ao reiniciar.",
        "",
    ]
    sections += _section_restrictions()
    sections += _section_issue_naming()
    sections += _section_boards(config)
    sections += _section_branches(config)

    CONTEXT_PATH.write_text("\n".join(sections), encoding="utf-8")
