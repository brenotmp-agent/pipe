"""Testes das transições de limite do throttle (permitir chegar a 0).

Regras:
- Redução por cooldown (passou 1h): divide por 2; se valor for 1, vira 0.
- Aumento por rate-limit hit: multiplica por 2; se valor for 0, vira 1.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.github_board import GitHubBoardAdapter


@pytest.fixture
def adapter(monkeypatch):
    a = GitHubBoardAdapter()
    monkeypatch.setattr("src.adapters.github_board.time.sleep", lambda *_: None)
    monkeypatch.setattr(a, "_save_throttle", lambda: None)
    return a


# ── Aumento (_throttle_hit) ───────────────────────────────────────────────────

def test_hit_from_zero_becomes_one(adapter):
    adapter._throttle_value = 0
    adapter._throttle_hit()
    assert adapter._throttle_value == 1


def test_hit_doubles_when_positive(adapter):
    adapter._throttle_value = 1
    adapter._throttle_hit()
    assert adapter._throttle_value == 2

    adapter._throttle_value = 8
    adapter._throttle_hit()
    assert adapter._throttle_value == 16


# ── Redução por cooldown (_throttle) ──────────────────────────────────────────

def _force_cooldown_elapsed(adapter):
    adapter._throttle_cooldown = datetime.now() - timedelta(seconds=1)


def test_cooldown_one_becomes_zero(adapter):
    adapter._throttle_value = 1
    _force_cooldown_elapsed(adapter)
    adapter._throttle()
    assert adapter._throttle_value == 0


def test_cooldown_zero_stays_zero(adapter):
    adapter._throttle_value = 0
    _force_cooldown_elapsed(adapter)
    adapter._throttle()
    assert adapter._throttle_value == 0


def test_cooldown_halves_when_above_one(adapter):
    adapter._throttle_value = 8
    _force_cooldown_elapsed(adapter)
    adapter._throttle()
    assert adapter._throttle_value == 4


# ── Ciclo completo 0 → 1 → 0 ──────────────────────────────────────────────────

def test_zero_to_one_and_back_to_zero(adapter):
    adapter._throttle_value = 0
    adapter._throttle_hit()
    assert adapter._throttle_value == 1

    _force_cooldown_elapsed(adapter)
    adapter._throttle()
    assert adapter._throttle_value == 0
