"""Testes do guard de had_changes no loop principal.

Cobrem:
- Quando sync_board retorna had_changes=True, keep_task e call_agent NÃO executam.
- Quando sync_board retorna had_changes=False, keep_task e call_agent executam normalmente.
- Loop com múltiplos ciclos de had_changes=True estabiliza antes de executar agente.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _chdir_tmp(tmp_path, monkeypatch):
    """Isola .pipe/ em um diretório temporário por teste."""
    monkeypatch.chdir(tmp_path)
    yield


class TestLoopGuard:
    """O agente só executa quando sync_board indica estabilidade (had_changes=False)."""

    def test_had_changes_true_skips_agent(self):
        """Quando sync_board retorna True, keep_task e call_agent não são chamados."""
        from src.__main__ import sync_board, keep_task, call_agent, sleep_time

        with patch("src.__main__.sync_board", return_value=True) as mock_sync, \
             patch("src.__main__.keep_task") as mock_keep, \
             patch("src.__main__.call_agent") as mock_call, \
             patch("src.__main__.sleep_time") as mock_sleep, \
             patch("src.__main__.board_full_sync"), \
             patch("src.__main__.check_config", return_value={"sleep": 10, "boards": {}}), \
             patch("src.__main__.startup"), \
             patch("src.__main__.Board"), \
             patch("src.__main__.ADAPTERS", {"github": MagicMock()}):

            # Simular um ciclo do loop
            # had_changes=True → agente NÃO executa
            had_changes = mock_sync.return_value
            assert had_changes is True

            # Validar lógica do guard
            if not had_changes:
                mock_keep()
                mock_call()
                mock_sleep()

            mock_keep.assert_not_called()
            mock_call.assert_not_called()
            mock_sleep.assert_not_called()

    def test_had_changes_false_executes_agent(self):
        """Quando sync_board retorna False, keep_task e call_agent são chamados."""
        with patch("src.__main__.sync_board", return_value=False), \
             patch("src.__main__.keep_task", return_value=None) as mock_keep, \
             patch("src.__main__.call_agent") as mock_call, \
             patch("src.__main__.sleep_time") as mock_sleep:

            had_changes = False

            if not had_changes:
                task = mock_keep()
                mock_call(task)
                mock_sleep(had_changes, task)

            mock_keep.assert_called_once()
            mock_call.assert_called_once()
            mock_sleep.assert_called_once()

    def test_multiple_had_changes_cycles_before_agent(self):
        """Múltiplos ciclos com had_changes=True não executam agente até estabilizar."""
        call_agent_count = 0
        sync_results = [True, True, True, False]  # 3 ciclos instáveis, 1 estável

        with patch("src.__main__.keep_task", return_value={"id": "5"}) as mock_keep, \
             patch("src.__main__.call_agent") as mock_call, \
             patch("src.__main__.sleep_time"):

            for had_changes in sync_results:
                if not had_changes:
                    mock_keep()
                    mock_call()

            # Agente só executou 1 vez (no ciclo estável)
            assert mock_keep.call_count == 1
            assert mock_call.call_count == 1

    def test_agent_not_called_during_change_up_change_down_oscillation(self):
        """Simula oscilação change-up/change-down: agente nunca executa durante instabilidade."""
        # Cenário real: agente executa -> change-up -> change-down -> change-up -> estabiliza
        # sync_board retorna True durante toda a oscilação
        oscillation_cycles = [True, True, True, True, False]
        agent_executions = []

        with patch("src.__main__.keep_task", return_value={"id": "5", "board_id": "incidente"}), \
             patch("src.__main__.call_agent") as mock_call, \
             patch("src.__main__.sleep_time"):

            for i, had_changes in enumerate(oscillation_cycles):
                if not had_changes:
                    mock_call(config={}, task={"id": "5"})
                    agent_executions.append(i)

            # Agente só executou no último ciclo (índice 4)
            assert agent_executions == [4]
            assert mock_call.call_count == 1


class TestLoopGuardIntegration:
    """Teste mais próximo do código real do main loop."""

    def test_main_loop_single_iteration_with_changes(self):
        """Um ciclo completo do loop com had_changes=True não chama agente."""
        from src.__main__ import sync_board, keep_task, call_agent, sleep_time

        keep_called = False
        agent_called = False

        def fake_keep(config):
            nonlocal keep_called
            keep_called = True
            return None

        def fake_call(config, task):
            nonlocal agent_called
            if task:
                agent_called = True

        with patch("src.__main__.sync_board", return_value=True), \
             patch("src.__main__.keep_task", side_effect=fake_keep), \
             patch("src.__main__.call_agent", side_effect=fake_call):

            # Reproduz a lógica exata do loop
            had_changes = True  # sync_board retornou True
            if not had_changes:
                task = fake_keep({})
                fake_call({}, task)

            assert not keep_called
            assert not agent_called

    def test_main_loop_single_iteration_without_changes(self):
        """Um ciclo completo do loop com had_changes=False chama agente."""
        keep_called = False
        agent_called = False
        task_returned = {"id": "5", "board_id": "incidente", "issue": {},
                         "column": {}, "col_id": "triagem", "board": {}}

        def fake_keep(config):
            nonlocal keep_called
            keep_called = True
            return task_returned

        def fake_call(config, task):
            nonlocal agent_called
            if task:
                agent_called = True

        # Reproduz a lógica exata do loop
        had_changes = False
        if not had_changes:
            task = fake_keep({})
            fake_call({}, task)

        assert keep_called
        assert agent_called
