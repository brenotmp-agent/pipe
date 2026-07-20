"""Commands core - comandos anotados no final do body das issues.

O body de uma issue pode conter um bloco de comandos no final, separado do
conteúdo real por uma linha contendo apenas o separador `@---`.

Exemplo de body completo:

    Implementar o endpoint de login.

    Deve validar credenciais e retornar JWT.

    @---
    /parent #10
    /blocked_by #42, #58
    /labels backend, security
    /agent_level high
    /need_human

Regras:
- O separador é `@---` (linha contendo apenas isso, ignorando espaços).
- Se houver mais de um separador, o ÚLTIMO vence; os anteriores são removidos
  do body (desambiguação).
- Cada comando ocupa uma linha iniciada por `/`. Linhas sem `/` no bloco são
  ignoradas (permite comentários livres).
- Filosofia presença/ausência: o estado do comando reflete exatamente o que
  está escrito. Se o comando existe, a relação/atributo é garantido; se não
  existe, é removido. Não há comandos de "remover".

Comandos suportados:
- /parent #N            issue pai (sub-issue de N)
- /children #N, #M      filhos (N e M são sub-issues desta)
- /blocked_by #N, #M    esta issue está bloqueada por N e M
- /blocks #N, #M        esta issue bloqueia N e M
- /labels a, b, c       labels da issue (SET completo)
- /agent_level low|medium|high
- /close [completed|not_planned]
- /archive
- /need_human           label especial (não entra em /labels)
"""

import re
from dataclasses import dataclass, field

# Separador entre o body real e o bloco de comandos.
SEP = "@---"

# Label especial: no GitHub é apenas mais uma label, mas no domínio é tratada
# separadamente (não aparece na lista de /labels).
NEED_HUMAN_LABEL = "need_human"

# Prefixo das labels de nível de agente (ex.: agent-level-high).
AGENT_LEVEL_PREFIX = "agent-level-"


@dataclass
class IssueCommands:
    """Estado declarativo dos comandos anotados no body de uma issue."""
    parent: str | None = None
    children: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    agent_level: str | None = None
    close: str | None = None        # 'completed' | 'not_planned'
    reopen: bool = False
    archive: bool = False
    need_human: bool = False

    def is_empty(self) -> bool:
        """True se nenhum comando foi declarado."""
        return not (
            self.parent or self.children or self.blocked_by or self.blocks
            or self.labels or self.agent_level or self.close or self.reopen
            or self.archive or self.need_human
        )

    def all_labels(self) -> list[str]:
        """Labels efetivas no board, incluindo as especiais need_human e agent-level-*."""
        result = list(self.labels)
        if self.need_human and NEED_HUMAN_LABEL not in result:
            result.append(NEED_HUMAN_LABEL)
        if self.agent_level:
            agent_level_label = f"{AGENT_LEVEL_PREFIX}{self.agent_level}"
            if agent_level_label not in result:
                result.append(agent_level_label)
        return result


# ══════════════════════════════════════════════════════════════════════════════
# Construção a partir de uma Issue (fluxo down)
# ══════════════════════════════════════════════════════════════════════════════

def from_issue(issue) -> IssueCommands:
    """Constrói IssueCommands a partir de uma Issue do board (fluxo down).

    Labels especiais são extraídas para campos próprios e não aparecem na
    lista de labels:
    - need_human → campo need_human
    - agent-level-<nível> → campo agent_level
    """
    labels = list(issue.labels or [])
    need_human = NEED_HUMAN_LABEL in labels
    labels = [l for l in labels if l != NEED_HUMAN_LABEL]

    # Extrai agent_level a partir de labels com prefixo agent-level-
    agent_level_value = None
    filtered_labels = []
    for lbl in labels:
        if lbl.startswith(AGENT_LEVEL_PREFIX):
            if agent_level_value is None:  # usa a primeira encontrada
                agent_level_value = lbl[len(AGENT_LEVEL_PREFIX):]
        else:
            filtered_labels.append(lbl)

    return IssueCommands(
        parent=getattr(issue, "parent", None),
        children=list(getattr(issue, "children", None) or []),
        blocked_by=list(getattr(issue, "blocked_by", None) or []),
        blocks=list(getattr(issue, "blocks", None) or []),
        labels=filtered_labels,
        need_human=need_human,
        agent_level=agent_level_value,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Parsing
# ══════════════════════════════════════════════════════════════════════════════

def _parse_refs(arg: str) -> list[str]:
    """Extrai referências de issue (#N, owner/repo#N) de um argumento.

    Aceita separação por vírgula e/ou espaço. Remove o prefixo '#'.
    """
    refs = []
    for part in re.split(r"[,\s]+", arg.strip()):
        part = part.strip()
        if not part:
            continue
        # Mantém owner/repo#N inteiro; remove apenas '#' isolado de '#N'
        if part.startswith("#"):
            part = part[1:]
        if part:
            refs.append(part)
    return refs


def _parse_labels(arg: str) -> list[str]:
    """Extrai labels separadas por vírgula (labels podem conter espaços)."""
    labels = []
    for part in arg.split(","):
        part = part.strip()
        if part and part not in labels:
            labels.append(part)
    return labels


def parse_commands(text: str) -> IssueCommands:
    """Faz o parse de um bloco de comandos (já separado do body)."""
    cmds = IssueCommands()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("/"):
            continue
        parts = line[1:].split(None, 1)
        if not parts:
            continue
        name = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if name == "parent":
            refs = _parse_refs(arg)
            cmds.parent = refs[0] if refs else None
        elif name == "children":
            cmds.children = _parse_refs(arg)
        elif name == "blocked_by":
            cmds.blocked_by = _parse_refs(arg)
        elif name == "blocks":
            cmds.blocks = _parse_refs(arg)
        elif name == "labels":
            cmds.labels = _parse_labels(arg)
        elif name == "agent_level":
            cmds.agent_level = arg.split()[0] if arg else None
        elif name == "close":
            cmds.close = arg.split()[0] if arg else "completed"
        elif name == "reopen":
            cmds.reopen = True
        elif name == "archive":
            cmds.archive = True
        elif name == "need_human":
            cmds.need_human = True

    return cmds


def split_body(raw: str) -> tuple[str, IssueCommands]:
    """Separa o body limpo dos comandos.

    Retorna (body_limpo, IssueCommands). Se houver múltiplos separadores, o
    último vence e os anteriores são removidos do body.
    """
    raw = raw or ""
    lines = raw.splitlines()
    sep_idx = [i for i, l in enumerate(lines) if l.strip() == SEP]

    if not sep_idx:
        return raw.rstrip("\n"), IssueCommands()

    last = sep_idx[-1]
    body_lines = [l for l in lines[:last] if l.strip() != SEP]
    cmd_text = "\n".join(lines[last + 1:])

    body = "\n".join(body_lines).rstrip("\n")
    return body, parse_commands(cmd_text)


# ══════════════════════════════════════════════════════════════════════════════
# Serialization
# ══════════════════════════════════════════════════════════════════════════════

def serialize_commands(cmds: IssueCommands) -> str:
    """Serializa os comandos em texto canônico (ordem fixa)."""
    lines = []
    if cmds.parent:
        lines.append(f"/parent #{cmds.parent}")
    if cmds.children:
        lines.append("/children " + ", ".join(f"#{c}" for c in cmds.children))
    if cmds.blocked_by:
        lines.append("/blocked_by " + ", ".join(f"#{c}" for c in cmds.blocked_by))
    if cmds.blocks:
        lines.append("/blocks " + ", ".join(f"#{c}" for c in cmds.blocks))
    if cmds.labels:
        lines.append("/labels " + ", ".join(cmds.labels))
    if cmds.agent_level:
        lines.append(f"/agent_level {cmds.agent_level}")
    if cmds.need_human:
        lines.append("/need_human")
    if cmds.close:
        lines.append(f"/close {cmds.close}")
    if cmds.reopen:
        lines.append("/reopen")
    if cmds.archive:
        lines.append("/archive")
    return "\n".join(lines)


def compose_body(body: str, cmds: IssueCommands) -> str:
    """Reconstrói o body completo: conteúdo + bloco de comandos.

    Se não há comandos, retorna apenas o body (sem separador).
    """
    body = (body or "").rstrip("\n")
    block = serialize_commands(cmds)
    if not block:
        return body
    return f"{body}\n\n{SEP}\n{block}"


# ══════════════════════════════════════════════════════════════════════════════
# Documentação para agentes (usada em prompts e contexts)
# ══════════════════════════════════════════════════════════════════════════════

ANNOTATIONS_DOC = """\
## Anotações no body da issue

O arquivo `-body.md` pode conter um bloco de comandos no final, separado do \
conteúdo real por uma linha contendo apenas `@---`. Tudo antes do `@---` é o \
conteúdo da issue; tudo depois são comandos que a esteira aplica no board.

Regras:
- Use exatamente `@---` (linha isolada) como separador.
- Cada comando é uma linha iniciada por `/`.
- Filosofia presença/ausência: o que estiver escrito é o estado final. Se o \
comando existe, a relação/atributo é garantido; se não existe, é removido. \
Não há comandos de "remover".

Comandos disponíveis:
- `/parent #N`            esta issue é sub-issue (filha) de N
- `/children #N, #M`      N e M são sub-issues (filhas) desta
- `/blocked_by #N, #M`    esta issue está bloqueada por N e M (não avança até fecharem)
- `/blocks #N, #M`        esta issue bloqueia N e M
- `/labels a, b, c`       define as labels da issue (substitui todas)
- `/agent_level low|medium|high`  nível de agente para a issue (planning poker)
- `/need_human`           marca que precisa de intervenção humana
- `/close [completed|not_planned]`  fecha a issue
- `/archive`              arquiva a issue no board

Ao criar uma sub-issue, sempre anote o vínculo: no body da nova issue use \
`/parent #N` apontando para a issue pai. Quando a sub-issue ainda não tem id \
(foi criada localmente), registre o vínculo na issue que já possui id usando \
`/children`.

Para dependências: quando uma tarefa nova (sem id) depende de outra que já \
tem id, anote `/blocked_by #N` na tarefa nova; se a tarefa nova bloqueia \
outra que já tem id, anote `/blocks #N`.

Exemplo de bloco no final do body:

    @---
    /parent #10
    /blocked_by #42, #58
    /labels backend, security
    /agent_level high
    /need_human
"""


def annotations_doc() -> str:
    """Retorna a documentação das anotações para incluir em prompts/contexts."""
    return ANNOTATIONS_DOC


# ══════════════════════════════════════════════════════════════════════════════
# Eventos de coluna aplicados sobre IssueCommands (on_in / on_out)
# ══════════════════════════════════════════════════════════════════════════════

def apply_events_to_commands(cmds: IssueCommands, events: list[str]) -> IssueCommands:
    """Aplica tokens de evento de coluna sobre um IssueCommands (in-place).

    Reescreve o estado declarativo dos comandos conforme os tokens:
      'close'        -> close = 'completed'
      'open'         -> reopen = True, archive = False, close = None
      'archive'      -> archive = True
      '-archive'     -> archive = False
      'need_human'   -> need_human = True
      '-need_human'  -> need_human = False
      '<label>'      -> adiciona label
      '-<label>'     -> remove label

    Retorna o próprio cmds (mutado) para encadeamento.
    """
    for raw in events or []:
        token = str(raw).strip()
        if not token:
            continue

        if token == "close":
            cmds.close = "completed"
            cmds.reopen = False
        elif token == "open":
            cmds.reopen = True
            cmds.close = None
            cmds.archive = False
        elif token == "archive":
            cmds.archive = True
        elif token == "-archive":
            cmds.archive = False
        elif token == "need_human":
            cmds.need_human = True
        elif token == "-need_human":
            cmds.need_human = False
        elif token.startswith("-"):
            label = token[1:]
            cmds.labels = [l for l in cmds.labels if l != label]
        else:
            if token not in cmds.labels:
                cmds.labels.append(token)

    return cmds

