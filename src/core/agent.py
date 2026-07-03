"""Agent core - port para execução de agentes."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from src.core.commands import annotations_doc, split_body
from src.core.snapshot import BOARDS_DIR

REPO_DIR = Path("repo")

CONTEXTS_DIR = Path("contexts")


def agent_level(issue: dict) -> str | None:
    """Lê o nível de agente da issue (tag /agent_level no bloco @---).

    O nível funciona como um "planning poker" simplificado (low|medium|high
    por padrão, configurável pelo usuário). É persistido no body via
    /agent_level.
    """
    body_path = Path(issue.get("body_path", ""))
    if not body_path.exists():
        return None
    content = body_path.read_text(encoding="utf-8")
    raw_body = content.split("\n", 1)[1] if "\n" in content else ""
    _, cmds = split_body(raw_body)
    return cmds.agent_level


def resolve_agent_id(col: dict, issue: dict) -> str:
    """Resolve o agente efetivo de uma coluna conforme o nível da issue.

    Usa `override-agent[<nível>]` quando o nível (tag /agent_level) existe e
    está mapeado; caso contrário, cai no `agent` default da coluna.
    """
    overrides = col.get("override-agent") or {}
    level = agent_level(issue)
    if level and level in overrides:
        return overrides[level]
    return col.get("agent", "")


def resolve_repo_id(config: dict, board_cfg: dict) -> str:
    """Resolve o id do repositório alvo de um board.

    Usa board.repo se definido; caso contrário, o primeiro repo de git.repo.
    """
    repos = config["git"]["repo"]
    return board_cfg.get("repo") or next(iter(repos))


def resolve_work_dir(config: dict, board_cfg: dict) -> Path:
    """Diretório de trabalho (sandbox) do agente: repo/<repo_id> absoluto."""
    return (REPO_DIR / resolve_repo_id(config, board_cfg)).resolve()


@dataclass
class AgentParams:
    """Parâmetros para execução do agente."""
    platform: str
    agent_id: str          # id do agente resolvido (config)
    agent_name: str        # nome amigável (log)
    model: str
    issue_id: str
    board_id: str
    col_id: str
    prompt: str
    work_dir: str          # diretório de trabalho do agente (clone em repo/<repo_id>)
    repo_id: str = None    # id do repositório alvo (chave em git.repo)
    context: str = None


class AgentPort(ABC):
    """Port para adapters de agente (kiro-cli, etc)."""

    @abstractmethod
    def execute(self, params: AgentParams) -> None:
        """Executa o agente com os parâmetros fornecidos."""
        pass


# ══════════════════════════════════════════════════════════════════════════════
# build_prompt
# ══════════════════════════════════════════════════════════════════════════════

def build_prompt(config: dict, task: dict) -> str:
    """Monta o prompt completo para o agente executar.

    task: dict com board_id, issue, column, col_id, board (retornado por keep_task).
    """
    board_id = task["board_id"]
    board_cfg = task["board"]
    col = task["column"]
    col_id = task["col_id"]
    issue = task["issue"]
    agent_name = resolve_agent_id(col, issue)
    gitevents = col.get("gitevents")  # create|use|merge|create-merge|no-branch

    # Resolver diretório de trabalho (sandbox do agente).
    # O agente SEMPRE opera dentro de repo/<repo_id>; nunca no diretório da esteira.
    work_dir = resolve_work_dir(config, board_cfg)

    # Resolver dados da issue (caminhos ABSOLUTOS: os arquivos vivem em .pipe/,
    # fora do repo, e o agente roda com cwd no repo).
    body_path = Path(issue.get("body_path", "")).resolve()
    slug = body_path.stem.removesuffix("-body")
    issue_dir = body_path.parent
    history_file = issue_dir / f"{slug}-history.md"
    addcomment_file = issue_dir / f"{slug}-addcomment.md"

    # Título da issue
    title = ""
    if body_path.exists():
        first_line = body_path.read_text(encoding="utf-8").split("\n", 1)[0]
        title = first_line.lstrip("# ").strip()
    title = title or slug

    # Resolver branch
    flow_type = board_cfg.get("flow", "feature")
    flow = config["git"]["flow"]
    flow_cfg = flow.get(flow_type, {})
    branch_name = f"{flow_cfg.get('prefix', '')}{issue['id']}-{slug}"
    origin_branch = flow_cfg.get("create", flow.get("base", "main"))
    merge_branch = flow_cfg.get("merge", flow.get("base", "main"))
    base_branch = flow.get("base", "main")

    # Transições
    change = col.get("change", {})

    lines = []

    # ── Cabeçalho ──
    lines.append(f"**Tarefa:** {title}")
    lines.append(f"**Etapa:** {col.get('name', col_id)}")
    lines.append(f"**Objetivo:** {col.get('target-prompt', '')}")
    lines.append("")

    # ── Sandbox / regras de operação ──
    lines.append("## Diretório de trabalho (OBRIGATÓRIO)")
    lines.append("")
    lines.append(f"Seu diretório de trabalho é o repositório clonado em `{work_dir}`.")
    lines.append("")
    lines.append("Regras invioláveis:")
    lines.append(f"- TODOS os comandos `git` e TODA alteração de código devem ocorrer DENTRO de `{work_dir}`.")
    lines.append(f"- Comece executando `cd {work_dir}` e permaneça lá durante toda a tarefa.")
    lines.append("- NUNCA execute `git checkout`, `git stash`, `git reset` ou qualquer comando git fora desse diretório.")
    lines.append("- Os arquivos da issue (`-body.md`, `-history.md`, `-addcomment.md`) ficam em `.pipe/`, FORA do repositório, e são gerenciados pela esteira. Leia/escreva-os pelos caminhos absolutos indicados, mas NÃO os versione no git.")
    lines.append("")

    # ── Git Setup (create / create-merge) ──
    if gitevents in ("create", "create-merge"):
        lines.append("## Git Setup")
        lines.append("```bash")
        lines.append(f"cd {work_dir}")
        lines.append("git fetch origin")
        lines.append(f"git checkout {origin_branch} && git pull origin {origin_branch}")
        lines.append(f"git checkout -b {branch_name}")
        lines.append("```")
        lines.append("")

    # ── Git Setup (use / merge) ──
    if gitevents in ("use", "merge"):
        lines.append("## Git Setup")
        lines.append("```bash")
        lines.append(f"cd {work_dir}")
        lines.append("git fetch origin")
        lines.append(f"git checkout {branch_name} 2>/dev/null || git checkout -b {branch_name} origin/{branch_name}")
        lines.append(f"git pull origin {branch_name} 2>/dev/null || true")
        lines.append("```")
        lines.append("")

    # ── Executar tarefa ──
    lines.append("## Executar tarefa")
    lines.append("")
    lines.append(f"Leia a issue em `{body_path}` e o histórico em `{history_file}` para contexto completo.")
    lines.append("")
    lines.append("Realize o objetivo descrito acima. Ao concluir ou se houver bloqueio:")
    lines.append("")
    lines.append(f"- Anote observações, dúvidas ou resumo em `{addcomment_file}` (assine com `— {agent_name}` no final)")
    lines.append("")

    # ── Commit & Push (create / use / merge / create-merge) ──
    if gitevents in ("create", "use", "merge", "create-merge"):
        lines.append("## Commit e Push")
        lines.append("```bash")
        lines.append(f"cd {work_dir}")
        lines.append("git add -A")
        lines.append(f'git commit -m "{col.get("name", col_id)}: {title}"')
        lines.append(f"git push -u origin {branch_name}")
        lines.append("```")
        lines.append("")

    # ── Merge Request (merge / create-merge) ──
    if gitevents in ("merge", "create-merge"):
        lines.append("## Pull Request")
        lines.append("```bash")
        lines.append(f"gh pr create --base {merge_branch} --head {branch_name} "
                     f"--title \"merge: {branch_name} -> {merge_branch}\" "
                     f"--body \"Automated PR from agent\"")
        lines.append("```")
        lines.append("")

    # ── Cleanup ──
    if gitevents in ("create", "use", "merge", "create-merge"):
        lines.append("## Cleanup")
        lines.append("```bash")
        lines.append(f"cd {work_dir}")
        lines.append(f"git checkout {base_branch}")
        lines.append(f"git branch -D {branch_name} 2>/dev/null || true")
        lines.append("```")
        lines.append("")

    # ── Anotações no body (comandos @---) ──
    lines.append(annotations_doc())
    lines.append("")

    # ── Transição de coluna ──
    lines.append("## Transição de coluna")
    lines.append("")
    lines.append("Ao finalizar, mova os 3 arquivos da issue (`-body.md`, `-history.md`, `-addcomment.md`) para a coluna de destino.")
    lines.append("")
    for condition, target_col in change.items():
        target_dir = (BOARDS_DIR / board_id / target_col).resolve()
        lines.append(f"- **{condition}** → `mv {issue_dir}/{slug}-*.md {target_dir}/`")
    lines.append("")

    return "\n".join(lines)
