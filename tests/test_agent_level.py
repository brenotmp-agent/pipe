"""Testes do comando /agent_level e da substituição de agente (override-agent).

Regra atual:
    - `/agent_level <nível>` no bloco @--- da issue.
    - Se `<nível>` for chave de `override-agent` da coluna, usa o agente do
      valor; senão, usa o `agent` default da coluna.
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

def _issue_with_body(tmp_path, body_block: str) -> dict:
    p = tmp_path / "1-x-body.md"
    p.write_text(f"# titulo\n\n@---\n{body_block}", encoding="utf-8")
    return {"body_path": str(p)}


def test_agent_level_le_do_body(tmp_path):
    """Após refatoração: agent_level lê de issue['labels'], não do arquivo body."""
    issue = {"labels": ["agent-level-high"], "body_path": ""}
    assert agent_level(issue) == "high"


def test_resolve_usa_override_quando_nivel_mapeado(tmp_path):
    col = {"agent": "engineering", "override-agent": {"high": "senior", "low": "generic"}}
    issue = {"labels": ["agent-level-high"], "body_path": ""}
    assert resolve_agent_id(col, issue) == "senior"


def test_resolve_cai_no_default_sem_agent_level(tmp_path):
    col = {"agent": "engineering", "override-agent": {"high": "senior"}}
    issue = _issue_with_body(tmp_path, "/labels x")
    assert resolve_agent_id(col, issue) == "engineering"


def test_resolve_cai_no_default_quando_nivel_nao_mapeado(tmp_path):
    col = {"agent": "engineering", "override-agent": {"high": "senior"}}
    issue = _issue_with_body(tmp_path, "/agent_level medium")
    assert resolve_agent_id(col, issue) == "engineering"


def test_resolve_sem_override_usa_default(tmp_path):
    col = {"agent": "engineering"}
    issue = _issue_with_body(tmp_path, "/agent_level high")
    assert resolve_agent_id(col, issue) == "engineering"
