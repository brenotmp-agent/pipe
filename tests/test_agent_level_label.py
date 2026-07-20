"""Casos de teste para a refatoração: persistir agent_level via label
agent-level-<nível> no GitHub.

Issue #25 — Refatoração: Persistir `agent_level` via label
`agent-level-<nível>` no GitHub.

Estes testes cobrem o comportamento ESPERADO após a refatoração:

1. `from_issue()` extrai agent_level a partir de labels `agent-level-*`.
2. Labels `agent-level-*` são excluídas do conjunto gerenciado por `/labels`
   (não sobrescritas pela semântica SET, análogo ao `need_human`).
3. `all_labels()` não inclui a label `agent-level-*` na lista gerenciada.
4. `agent_level()` em `agent.py` lê diretamente `issue["labels"]` (campo do
   snapshot/dict) em vez de parsear o arquivo body.
5. `resolve_agent_id()` usa o nível extraído de labels para escolher o agente.
6. Round-trip board → `from_issue` → arquivo preserva agent_level via label.
7. Múltiplas labels `agent-level-*` → apenas o último/único nível é considerado
   (comportamento defensivo).
8. Label `agent-level-*` não aparece em `/labels` no `serialize_commands`.
9. A lógica de `all_labels()` emite a label `agent-level-<nível>` para o board
   (necessário para o sync-up gravar a label corretamente).

Status: RED (falham antes da refatoração; devem passar após).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.commands import (
    IssueCommands,
    from_issue,
    parse_commands,
    serialize_commands,
    split_body,
    compose_body,
)
from src.core.agent import agent_level, resolve_agent_id

# ══════════════════════════════════════════════════════════════════════════════
# Prefixo canônico
# ══════════════════════════════════════════════════════════════════════════════

AGENT_LEVEL_PREFIX = "agent-level-"


def _make_issue(labels: list[str], **kwargs):
    """Cria um objeto Issue-like mínimo com as labels fornecidas."""
    issue = MagicMock()
    issue.labels = list(labels)
    issue.parent = kwargs.get("parent", None)
    issue.children = kwargs.get("children", [])
    issue.blocked_by = kwargs.get("blocked_by", [])
    issue.blocks = kwargs.get("blocks", [])
    return issue


def _make_issue_dict(labels: list[str], body_path: str = "") -> dict:
    """Cria um dict de issue (formato snapshot) com as labels fornecidas."""
    return {
        "labels": list(labels),
        "body_path": body_path,
        "id": "99",
    }


# ══════════════════════════════════════════════════════════════════════════════
# 1. from_issue() extrai agent_level a partir de labels agent-level-*
# ══════════════════════════════════════════════════════════════════════════════

def test_from_issue_extrai_agent_level_high():
    """from_issue deve popular agent_level quando a label agent-level-high existe."""
    issue = _make_issue(["backend", "agent-level-high", "security"])
    cmds = from_issue(issue)
    assert cmds.agent_level == "high"


def test_from_issue_extrai_agent_level_low():
    issue = _make_issue(["agent-level-low"])
    cmds = from_issue(issue)
    assert cmds.agent_level == "low"


def test_from_issue_extrai_agent_level_medium():
    issue = _make_issue(["agent-level-medium", "backend"])
    cmds = from_issue(issue)
    assert cmds.agent_level == "medium"


def test_from_issue_sem_label_agent_level_retorna_none():
    """Sem label agent-level-*, agent_level deve ser None."""
    issue = _make_issue(["backend", "security"])
    cmds = from_issue(issue)
    assert cmds.agent_level is None


def test_from_issue_label_agent_level_nao_aparece_em_labels():
    """A label agent-level-* não deve aparecer em cmds.labels após from_issue."""
    issue = _make_issue(["backend", "agent-level-high", "security"])
    cmds = from_issue(issue)
    for lbl in cmds.labels:
        assert not lbl.startswith(AGENT_LEVEL_PREFIX), (
            f"Label '{lbl}' não deve aparecer em cmds.labels"
        )


def test_from_issue_labels_normais_preservadas():
    """Labels comuns não devem ser afetadas pelo filtro de agent-level-*."""
    issue = _make_issue(["backend", "agent-level-medium", "security"])
    cmds = from_issue(issue)
    assert "backend" in cmds.labels
    assert "security" in cmds.labels
    assert len([l for l in cmds.labels if not l.startswith(AGENT_LEVEL_PREFIX)]) == 2


# ══════════════════════════════════════════════════════════════════════════════
# 2. all_labels() inclui a label agent-level-<nível> para sync-up com o board
# ══════════════════════════════════════════════════════════════════════════════

def test_all_labels_inclui_agent_level_label():
    """all_labels() deve emitir a label agent-level-<nível> para o board."""
    cmds = IssueCommands(labels=["backend"], agent_level="high")
    all_lbs = cmds.all_labels()
    assert "agent-level-high" in all_lbs


def test_all_labels_sem_agent_level_nao_emite_prefixo():
    """Sem agent_level definido, all_labels não emite nenhuma label agent-level-*."""
    cmds = IssueCommands(labels=["backend"])
    all_lbs = cmds.all_labels()
    for lbl in all_lbs:
        assert not lbl.startswith(AGENT_LEVEL_PREFIX)


def test_all_labels_agent_level_e_need_human_juntos():
    """all_labels deve emitir tanto need_human quanto agent-level-<nível>."""
    cmds = IssueCommands(labels=["backend"], agent_level="low", need_human=True)
    all_lbs = cmds.all_labels()
    assert "need_human" in all_lbs
    assert "agent-level-low" in all_lbs
    assert "backend" in all_lbs


def test_all_labels_nao_duplica_agent_level_label():
    """Se o usuário já colocou agent-level-X em labels, não deve duplicar."""
    cmds = IssueCommands(labels=["agent-level-high"], agent_level="high")
    all_lbs = cmds.all_labels()
    assert all_lbs.count("agent-level-high") == 1


# ══════════════════════════════════════════════════════════════════════════════
# 3. /labels não sobrescreve a label agent-level-*
# ══════════════════════════════════════════════════════════════════════════════

def test_labels_cmd_nao_remove_agent_level_via_set():
    """/labels não pode remover a label agent-level-* (semântica SET limitada).

    O sync-up usa all_labels() para calcular o conjunto final. A label
    agent-level-* deriva de agent_level, não de cmds.labels. Portanto, se o
    usuário escrever /labels backend, a label agent-level-high deve sobreviver
    caso agent_level == 'high'.
    """
    cmds = IssueCommands(labels=["backend"], agent_level="high")
    all_lbs = cmds.all_labels()
    # Mesmo com /labels definindo apenas 'backend', agent-level-high persiste.
    assert "agent-level-high" in all_lbs
    assert "backend" in all_lbs


def test_parse_labels_nao_popula_agent_level_diretamente():
    """/labels agent-level-high não deve preencher cmds.agent_level.

    A label agent-level-* só deve ser populada via from_issue (fluxo down)
    ou via /agent_level (fluxo up); não via /labels.
    """
    cmds = parse_commands("/labels agent-level-high, backend")
    # agent_level não deve ser preenchido por /labels
    assert cmds.agent_level is None
    # A label vai para cmds.labels (será filtrada pelo all_labels no momento certo)
    assert "agent-level-high" in cmds.labels


# ══════════════════════════════════════════════════════════════════════════════
# 4. agent_level() em agent.py lê de issue["labels"] (não do arquivo body)
# ══════════════════════════════════════════════════════════════════════════════

def test_agent_level_le_de_labels_no_dict():
    """agent_level() deve ler issue['labels'] e não o arquivo body."""
    issue = _make_issue_dict(labels=["backend", "agent-level-high"])
    assert agent_level(issue) == "high"


def test_agent_level_le_medium_de_labels():
    issue = _make_issue_dict(labels=["agent-level-medium"])
    assert agent_level(issue) == "medium"


def test_agent_level_retorna_none_sem_label():
    """Sem label agent-level-*, agent_level retorna None (não lê mais do body)."""
    issue = _make_issue_dict(labels=["backend", "security"])
    assert agent_level(issue) is None


def test_agent_level_ignora_body_path_quando_label_presente(tmp_path):
    """Mesmo que o body tenha /agent_level low, se a label diz high, usa high."""
    body = tmp_path / "1-x-body.md"
    body.write_text("# titulo\n\n@---\n/agent_level low\n", encoding="utf-8")
    issue = _make_issue_dict(labels=["agent-level-high"], body_path=str(body))
    # Após refatoração: lê label, não body
    assert agent_level(issue) == "high"


def test_agent_level_sem_labels_retorna_none(tmp_path):
    """issue sem labels retorna None."""
    issue = _make_issue_dict(labels=[])
    assert agent_level(issue) is None


# ══════════════════════════════════════════════════════════════════════════════
# 5. resolve_agent_id() usa nível via label
# ══════════════════════════════════════════════════════════════════════════════

def test_resolve_agent_id_via_label_high():
    col = {"agent": "engineering", "override-agent": {"high": "senior", "low": "generic"}}
    issue = _make_issue_dict(labels=["agent-level-high"])
    assert resolve_agent_id(col, issue) == "senior"


def test_resolve_agent_id_via_label_low():
    col = {"agent": "engineering", "override-agent": {"high": "senior", "low": "generic"}}
    issue = _make_issue_dict(labels=["agent-level-low"])
    assert resolve_agent_id(col, issue) == "generic"


def test_resolve_agent_id_sem_label_usa_default():
    col = {"agent": "engineering", "override-agent": {"high": "senior"}}
    issue = _make_issue_dict(labels=["backend"])
    assert resolve_agent_id(col, issue) == "engineering"


def test_resolve_agent_id_nivel_nao_mapeado_usa_default():
    col = {"agent": "engineering", "override-agent": {"high": "senior"}}
    issue = _make_issue_dict(labels=["agent-level-medium"])
    assert resolve_agent_id(col, issue) == "engineering"


def test_resolve_agent_id_sem_override_usa_default():
    col = {"agent": "engineering"}
    issue = _make_issue_dict(labels=["agent-level-high"])
    assert resolve_agent_id(col, issue) == "engineering"


# ══════════════════════════════════════════════════════════════════════════════
# 6. Round-trip board → from_issue → serialize_commands
# ══════════════════════════════════════════════════════════════════════════════

def test_roundtrip_board_to_file_preserva_agent_level():
    """from_issue → serialize_commands preserva o agent_level como /agent_level."""
    issue = _make_issue(["backend", "agent-level-high"])
    cmds = from_issue(issue)
    serialized = serialize_commands(cmds)
    assert "/agent_level high" in serialized


def test_roundtrip_nao_serializa_agent_level_label_em_labels():
    """serialize_commands não deve emitir agent-level-high em /labels."""
    issue = _make_issue(["backend", "agent-level-high"])
    cmds = from_issue(issue)
    serialized = serialize_commands(cmds)
    # /labels não deve conter agent-level-high
    for line in serialized.splitlines():
        if line.startswith("/labels"):
            assert "agent-level" not in line, (
                f"label agent-level-* não deve aparecer em /labels: '{line}'"
            )


def test_roundtrip_completo_body_preserva_nivel():
    """Ciclo completo: from_issue → compose_body → split_body retorna agent_level."""
    issue = _make_issue(["backend", "agent-level-medium", "security"])
    cmds = from_issue(issue)
    body = compose_body("Conteúdo da issue.", cmds)
    _, parsed = split_body(body)
    assert parsed.agent_level == "medium"


# ══════════════════════════════════════════════════════════════════════════════
# 7. Comportamento defensivo: múltiplas labels agent-level-*
# ══════════════════════════════════════════════════════════════════════════════

def test_multiplas_labels_agent_level_usa_primeira_encontrada():
    """Com múltiplas labels agent-level-*, deve usar uma delas sem crash."""
    issue = _make_issue(["agent-level-low", "agent-level-high"])
    cmds = from_issue(issue)
    # Não deve falhar; deve retornar um nível válido
    assert cmds.agent_level in ("low", "high")


def test_multiplas_labels_agent_level_dict_usa_uma():
    issue = _make_issue_dict(labels=["agent-level-low", "agent-level-medium"])
    level = agent_level(issue)
    assert level in ("low", "medium")


# ══════════════════════════════════════════════════════════════════════════════
# 8. serialize_commands: /agent_level não gera label em /labels
# ══════════════════════════════════════════════════════════════════════════════

def test_serialize_agent_level_gera_campo_proprio():
    """serialize_commands emite /agent_level separado, não em /labels."""
    cmds = IssueCommands(labels=["backend"], agent_level="high")
    serialized = serialize_commands(cmds)
    assert "/agent_level high" in serialized
    # /labels deve conter apenas 'backend'
    for line in serialized.splitlines():
        if line.startswith("/labels"):
            assert "agent-level" not in line


def test_serialize_sem_agent_level_nao_emite_campo():
    cmds = IssueCommands(labels=["backend"])
    serialized = serialize_commands(cmds)
    assert "/agent_level" not in serialized


# ══════════════════════════════════════════════════════════════════════════════
# 9. Regressão: need_human não é afetado pela refatoração
# ══════════════════════════════════════════════════════════════════════════════

def test_need_human_nao_interfere_com_agent_level():
    """need_human e agent_level coexistem sem interferência."""
    issue = _make_issue(["need_human", "agent-level-high", "backend"])
    cmds = from_issue(issue)
    assert cmds.need_human is True
    assert cmds.agent_level == "high"
    assert "backend" in cmds.labels
    # need_human não aparece em cmds.labels
    assert "need_human" not in cmds.labels
    # agent-level-high não aparece em cmds.labels
    assert "agent-level-high" not in cmds.labels


def test_all_labels_com_need_human_e_agent_level():
    """all_labels emite need_human e agent-level-* corretamente."""
    cmds = IssueCommands(labels=["backend"], agent_level="medium", need_human=True)
    all_lbs = cmds.all_labels()
    assert "need_human" in all_lbs
    assert "agent-level-medium" in all_lbs
    assert "backend" in all_lbs
    # agent-level não aparece também como label normal (não duplicar)
    assert all_lbs.count("agent-level-medium") == 1


# ══════════════════════════════════════════════════════════════════════════════
# 10. IssueCommands.is_empty() reconhece agent_level como campo não-vazio
# ══════════════════════════════════════════════════════════════════════════════

def test_is_empty_falso_quando_agent_level_definido():
    cmds = IssueCommands(agent_level="low")
    assert cmds.is_empty() is False


def test_is_empty_verdadeiro_sem_campos():
    cmds = IssueCommands()
    assert cmds.is_empty() is True
