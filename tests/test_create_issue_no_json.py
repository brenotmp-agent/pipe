"""
Regressão: 'gh issue create' NÃO suporta a flag --json.

Antes, create_issue chamava:
    gh issue create --repo ... --title ... --body ... --json number,title,body,updatedAt
o que falhava com "unknown flag: --json" e era engolido como
"Erro no ciclo (não fatal)", impedindo a criação de issues (ex.: stories).

'gh issue create' imprime a URL da issue criada no stdout; o número precisa
ser extraído da URL e os metadados obtidos via GraphQL.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.github_board import GitHubBoardAdapter as GH


def _make_adapter():
    gh = object.__new__(GH)
    gh._repo = "owner/repo"
    gh._throttle_value = 16
    return gh


def test_create_issue_nao_usa_flag_json():
    gh = _make_adapter()
    captured = {}

    def fake_gh(*args, stdin=None):
        captured["args"] = args
        # gh issue create imprime a URL no stdout
        return "https://github.com/owner/repo/issues/42"

    def fake_gql(query, **variables):
        if "addProjectV2ItemById" in query:
            return {"addProjectV2ItemById": {"item": {"id": "ITEM_ID"}}}
        if "updateProjectV2ItemFieldValue" in query:
            return {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "ITEM_ID"}}}
        # query da issue -> id + updatedAt
        return {"repository": {"issue": {"id": "NODE_ID", "updatedAt": "2026-07-06T12:01:00Z"}}}

    gh._penalty_check = lambda: None
    gh._gh = fake_gh
    gh._gql = fake_gql
    gh._board_meta = lambda board_id: {
        "project_id": "PID",
        "status_field_id": "FID",
        "options": {"criacao-stories": "OPT"},
    }

    issue = gh.create_issue("story", "Empacotar a esteira", "corpo", "criacao-stories")

    assert "--json" not in captured["args"], "create_issue não deve usar --json"
    assert issue.id == "42"
    assert issue.title == "Empacotar a esteira"
    assert issue.updated_at == "2026-07-06T12:01:00Z"


def test_create_issue_falha_se_url_invalida():
    gh = _make_adapter()

    gh._penalty_check = lambda: None
    gh._gh = lambda *a, **k: "algo inesperado sem numero"

    try:
        gh.create_issue("story", "t", "b", "col")
    except Exception as e:
        assert "gh issue create" in str(e)
    else:
        raise AssertionError("esperava exceção quando a saída não contém número de issue")
