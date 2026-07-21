"""Agent core - port para execução de agentes."""

import fnmatch
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from src.core.commands import annotations_doc, AGENT_LEVEL_PREFIX
from src.core.snapshot import BOARDS_DIR

REPO_DIR = Path("repo")

CONTEXTS_DIR = Path("contexts")

# ══════════════════════════════════════════════════════════════════════════════
# Proteção de arquivos de estado interno
# ══════════════════════════════════════════════════════════════════════════════

# Lista centralizada de padrões glob de arquivos de estado interno da esteira.
# Nenhum desses paths deve jamais aparecer em prompts enviados a agentes.
# Padrões seguem a sintaxe fnmatch (glob simples, sem separadores de diretório
# implícitos). Para paths absolutos, a verificação é feita comparando o
# sufixo do path com o padrão sem o prefixo de diretório variável.
#
# Referência: [Incidente Issue Fantasma] Correção 1 — issue #8.
PROTECTED_PATHS: list[str] = [
    ".pipe/boards/*/snapshot.json",
    ".pipe/changeQueue.json",
    ".pipe/throttle.json",
    ".pipe/throttle-*.json",
]


def _matches_protected(token: str, pattern: str) -> bool:
    """Verifica se um token de texto corresponde a um padrão protegido.

    Estratégia:
    - Teste direto com fnmatch (cobre paths relativos exatos).
    - Para padrões com ``*`` interno (ex.: ``boards/*/snapshot.json``), divide
      o padrão em prefixo fixo e sufixo fixo e verifica se o token contém o
      sufixo (cobre paths absolutos e relativos com subdiretórios variáveis).
    - Para padrões simples sem ``*`` no meio, verifica se o token termina com
      o padrão inteiro (cobre paths absolutos).
    """
    # Teste direto (path relativo exato ou com glob no nível de arquivo)
    if fnmatch.fnmatch(token, pattern):
        return True

    # Para cobertura de paths absolutos: verifica se o token contém uma
    # sequência que case com o padrão. Divide em segmentos e testa o sufixo.
    parts = pattern.split("/")
    # Pega a parte do padrão a partir do primeiro segmento com glob ou fixo
    # que identifica o arquivo de forma única (último segmento com extensão).
    # Estratégia: encontra o sufixo mais longo sem '*' no início.
    suffix_parts = []
    for part in reversed(parts):
        suffix_parts.insert(0, part)
        if "*" not in part:
            # Continua acumulando até encontrar um segmento com glob
            candidate = "/".join(suffix_parts)
            if fnmatch.fnmatch(token.split("/")[-len(suffix_parts):][0]
                               if len(token.split("/")) >= len(suffix_parts)
                               else "", suffix_parts[0]):
                # Verifica se o final do token casa com os últimos N segmentos
                token_parts = token.replace("\\", "/").split("/")
                n = len(suffix_parts)
                if len(token_parts) >= n:
                    tail = "/".join(token_parts[-n:])
                    if fnmatch.fnmatch(tail, candidate):
                        return True
            break
        else:
            # Há glob neste segmento; o que importa é o sufixo após o glob
            # Não continua acumulando para trás além desse ponto
            break

    return False


def _assert_no_protected(prompt: str) -> None:
    """Verifica que nenhum path protegido (PROTECTED_PATHS) aparece no prompt.

    Levanta ValueError identificando o arquivo protegido encontrado.

    A verificação tokeniza o prompt palavra a palavra e avalia cada token
    contra os padrões em PROTECTED_PATHS via fnmatch. Para padrões com
    componentes de diretório (ex.: ``.pipe/boards/*/snapshot.json``), o token
    é testado tanto diretamente quanto pela correspondência do sufixo — o que
    cobre tanto paths relativos quanto absolutos.

    Não dispara falsos positivos para substrings sem extensão .json ou nomes
    similares (ex.: ``snapshots/``, ``snap.py``, ``throttle-config.yaml``).
    """
    # Separa o prompt em tokens (palavras, paths, qualquer sequência não-espaço)
    tokens = prompt.split()

    for token in tokens:
        # Remove pontuação final que não faz parte do path (vírgula, ponto final…)
        token = token.rstrip(".,;:\"'`)")

        for pattern in PROTECTED_PATHS:
            if _matches_protected(token, pattern):
                # Extrai o nome do arquivo do padrão para a mensagem de erro.
                filename = pattern.rsplit("/", 1)[-1]
                raise ValueError(
                    f"Prompt contém referência a arquivo de estado protegido "
                    f"'{filename}' (padrão: '{pattern}'). "
                    f"Token encontrado: '{token}'"
                )


def agent_level(issue: dict) -> str | None:
    """Lê o nível de agente da issue a partir das labels do board.

    O nível é armazenado como label `agent-level-<nível>` no GitHub
    (ex.: agent-level-low, agent-level-medium, agent-level-high).
    Essa label é sincronizada nativamente pelo board, eliminando a
    dependência de estado local que causava o bug de preservação no sync-down.
    """
    for label in issue.get("labels", []) or []:
        if label.startswith(AGENT_LEVEL_PREFIX):
            return label[len(AGENT_LEVEL_PREFIX):]
    return None


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
    agent_id = resolve_agent_id(col, issue)
    gitevents = col.get("gitevents")  # create|use|merge|create-merge|no-branch

    # Resolver nome humanizado do agente a partir da config
    agent_display_name = agent_id
    for platform_agents in config.get("agents", {}).values():
        if agent_id in platform_agents:
            agent_display_name = platform_agents[agent_id].get("name", agent_id)
            break

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
    lines.append(f"Você é: {agent_display_name}.")
    lines.append("")
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
    lines.append(f"- Anote observações, dúvidas ou resumo em `{addcomment_file}` (assine com `— {agent_display_name}` no final)")
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

    prompt = "\n".join(lines)

    # Guard de segurança: garante que nenhum arquivo de estado interno da
    # esteira vaze no prompt enviado ao agente.
    _assert_no_protected(prompt)

    return prompt
