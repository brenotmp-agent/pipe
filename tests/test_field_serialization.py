"""Regressão: serialização de campos para o gh api (_field_arg).

Bug: bool era passado via -F como str(True) == "True". O gh só faz a conversão
mágica de tipo com os literais minúsculos true/false/null; "True" ia como string
e a API rejeitava com HTTP 422:
    Invalid property /replace_parent: "True" is not of type boolean.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.github_board import GitHubBoardAdapter as GH


def test_bool_true_vira_literal_minusculo():
    assert GH._field_arg("replace_parent", True) == ["-F", "replace_parent=true"]


def test_bool_false_vira_literal_minusculo():
    assert GH._field_arg("replace_parent", False) == ["-F", "replace_parent=false"]


def test_int_usa_field_tipado():
    assert GH._field_arg("sub_issue_id", 123) == ["-F", "sub_issue_id=123"]


def test_float_usa_field_tipado():
    assert GH._field_arg("ratio", 1.5) == ["-F", "ratio=1.5"]


def test_str_usa_raw_field():
    assert GH._field_arg("body", "olá") == ["-f", "body=olá"]


def test_bool_nunca_emite_valor_capitalizado():
    # Garante que nenhum valor "True"/"False" (capitalizado) seja emitido.
    for val in (True, False):
        _, kv = GH._field_arg("x", val)
        assert "True" not in kv and "False" not in kv
