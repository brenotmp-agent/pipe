"""Testes do comando /agent_level e da substituição de agente (override-agent).

Regra atual (pós-refatoração issue #28):
    - O `agent_level` é armazenado como label `agent-level-<nível>` no GitHub.
    - `agent_level()` lê `issue["labels"]` (não o arquivo body).
    - `resolve_agent_id()` usa o nível extraído das labels para selecionar o
      agente via `override-agent`; sem match, usa o `agent` default da coluna.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.commands import split_body, serialize_commands, parse_commands
from src.core.agent import agent_level, resolve_agent_id


# ── parse / serialize ─────────────────────────────────────────────────────────

def test_parse_agent_level():
    cmds = parse_commands("/agent_level high")
    assert cmds.agent_level == "high"


def test_parse_effort_nao_e_mais_reconhecido():
    """O token antigo /effort não deve mais preencher agent_level."""
    cmds = parse_commands("/effort high")
    assert cmds.agent_level is None


def test_serialize_agent_level():
    cmds = parse_commands("/agent_level medium")
    assert "/agent_level medium" in serialize_commands(cmds)


def test_roundtrip_agent_level():
    _, cmds = split_body("corpo\n\n@---\n/agent_level low\n/labels x")
    assert cmds.agent_level == "low"
    assert cmds.labels == ["x"]


# ── resolução de agente ───────────────────────────────────────────────────────

def _issue_with_labels(labels: list) -> dict:
    """Cria um dict de issue (formato snapshot) com as labels fornecidas."""
    return {"labels": list(labels), "body_path": ""}


def test_agent_level_le_de_labels():
    """agent_level() lê issue['labels'], não o arquivo body."""
    issue = _issue_with_labels(["agent-level-high"])
    assert agent_level(issue) == "high"


def test_agent_level_retorna_none_sem_label_de_nivel():
    """Sem label agent-level-*, agent_level retorna None (mesmo que body tenha /agent_level)."""
    # Garante que a função NÃO lê o body: uma issue sem labels e sem body_path
    # válido deve retornar None limpo.
    issue = _issue_with_labels([])
    assert agent_level(issue) is None


def test_agent_level_ignora_body_quando_sem_label(tmp_path):
    """Body com /agent_level não alimenta agent_level() — só labels do board importam."""
    body = tmp_path / "1-x-body.md"
    body.write_text("# titulo\n\n@---\n/agent_level high\n", encoding="utf-8")
    issue = {"labels": [], "body_path": str(body)}
    # Sem a label no board, retorna None (não lê o body)
    assert agent_level(issue) is None


def test_resolve_usa_override_quando_nivel_mapeado():
    col = {"agent": "engineering", "override-agent": {"high": "senior", "low": "generic"}}
    issue = _issue_with_labels(["agent-level-high"])
    assert resolve_agent_id(col, issue) == "senior"


def test_resolve_cai_no_default_sem_label_de_nivel():
    """Sem label agent-level-*, resolve_agent_id retorna o agente default."""
    col = {"agent": "engineering", "override-agent": {"high": "senior"}}
    issue = _issue_with_labels(["backend", "security"])
    assert resolve_agent_id(col, issue) == "engineering"


def test_resolve_cai_no_default_quando_nivel_nao_mapeado():
    """Label agent-level-medium sem entrada em override-agent → default."""
    col = {"agent": "engineering", "override-agent": {"high": "senior"}}
    issue = _issue_with_labels(["agent-level-medium"])
    assert resolve_agent_id(col, issue) == "engineering"


def test_resolve_sem_override_usa_default():
    """Coluna sem override-agent ignora qualquer nível e retorna o default."""
    col = {"agent": "engineering"}
    issue = _issue_with_labels(["agent-level-high"])
    assert resolve_agent_id(col, issue) == "engineering"
