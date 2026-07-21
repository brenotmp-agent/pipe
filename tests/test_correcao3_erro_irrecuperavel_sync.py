"""
Casos de Teste — Correção 3: Tratamento de erro irrecuperável no sync

Contexto: Durante o incidente "Issue Fantasma", a esteira entrou em loop
infinito tentando fechar/atualizar issues que não existiam no GitHub. O erro
"Could not resolve to an issue or pull request with the number of N" era
tratado como erro transitório e o evento permanecia na fila at-least-once
indefinidamente.

Esta suíte valida que:
  - _apply_delete_up descarta o evento e limpa o snapshot ao receber o erro
    "Could not resolve..." de close_issue.
  - _apply_change_up descarta o evento e limpa o snapshot ao receber o mesmo
    erro de update_issue.
  - O snapshot não contém mais a entrada da issue fantasma após o tratamento.
  - Um log de warning é emitido identificando a issue fantasma e o board.
  - Outras exceções continuam propagando normalmente (sem regressão).

Estratégia: os testes exercem _apply_delete_up e _apply_change_up diretamente,
usando um diretório temporário para simular o BOARDS_DIR e mocks para board_obj.
Não há chamadas reais à API do GitHub.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from src.core.board import ChangeItem, PenaltyException, SyncEvent
from src.core import sync as sync_module
from src.core.sync import _apply_delete_up, _apply_change_up


# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

GHOST_ERROR = "Could not resolve to an issue or pull request with the number of 42"
OTHER_ERROR = "Network timeout: conexão recusada"

BOARD_ID = "task"
ISSUE_ID = "42"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_snapshot_data(issue_id: str = ISSUE_ID) -> dict:
    """Retorna um dict de snapshot com uma única issue."""
    return {
        "board": {"todo": "To Do", "doing": "Doing"},
        "issues": [
            {
                "id": issue_id,
                "column": "doing",
                "body_path": f".pipe/boards/{BOARD_ID}/doing/{issue_id}-slug-body.md",
                "body_mtime": "1720000000.0",
                "status": "delete-up",
            }
        ],
        "last_sync": None,
        "last_board_update": None,
    }


def _make_change_item(event: SyncEvent = SyncEvent.DELETE_UP,
                      issue_id: str = ISSUE_ID) -> ChangeItem:
    return ChangeItem.of(event, id=issue_id, board=BOARD_ID)


class SnapshotFixture:
    """Cria um diretório temporário com snapshot.json e helpers de leitura."""

    def __init__(self, tmp_path: Path, issue_id: str = ISSUE_ID):
        self.board_dir = tmp_path / BOARD_ID
        self.board_dir.mkdir(parents=True, exist_ok=True)
        self.snap_path = self.board_dir / "snapshot.json"
        self.snap_path.write_text(
            json.dumps(_make_snapshot_data(issue_id), indent=2), encoding="utf-8"
        )

    def read(self) -> dict:
        return json.loads(self.snap_path.read_text(encoding="utf-8"))

    def issue_ids(self) -> list[str]:
        return [str(i["id"]) for i in self.read().get("issues", [])]


def _patches(tmp_path: Path):
    """Retorna context manager com os dois patches de BOARDS_DIR."""
    import contextlib
    p1 = patch.object(sync_module, "BOARDS_DIR", tmp_path)
    p2 = patch("src.core.snapshot.BOARDS_DIR", tmp_path)
    return contextlib.ExitStack(), p1, p2


# ─────────────────────────────────────────────────────────────────────────────
# CT-C3-01: _apply_delete_up — issue fantasma → descarte sem re-raise
# ─────────────────────────────────────────────────────────────────────────────

class TestApplyDeleteUpIssueFantasma(unittest.TestCase):
    """CT-C3-01: close_issue falha com 'Could not resolve...' → descarte silencioso."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.fixture = SnapshotFixture(self.tmp_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, board_obj):
        item = _make_change_item(SyncEvent.DELETE_UP)
        with patch.object(sync_module, "BOARDS_DIR", self.tmp_path), \
             patch("src.core.snapshot.BOARDS_DIR", self.tmp_path):
            _apply_delete_up(BOARD_ID, item, board_obj)

    def test_nao_propaga_excecao_de_issue_fantasma(self):
        """_apply_delete_up não deve levantar exceção quando issue é fantasma."""
        board_obj = MagicMock()
        board_obj.close_issue.side_effect = Exception(GHOST_ERROR)

        try:
            self._run(board_obj)
        except Exception as exc:
            self.fail(
                f"_apply_delete_up propagou exceção para issue fantasma: {exc}"
            )

    def test_remove_issue_do_snapshot_apos_erro_fantasma(self):
        """Snapshot não deve conter mais o id da issue fantasma após o tratamento."""
        board_obj = MagicMock()
        board_obj.close_issue.side_effect = Exception(GHOST_ERROR)

        self._run(board_obj)

        ids = self.fixture.issue_ids()
        self.assertNotIn(
            ISSUE_ID, ids,
            f"Issue #{ISSUE_ID} ainda está no snapshot após tratamento de fantasma: {ids}",
        )

    def test_snapshot_vazio_apos_unica_issue_fantasma(self):
        """Com apenas uma issue no snapshot, a lista fica vazia após o tratamento."""
        board_obj = MagicMock()
        board_obj.close_issue.side_effect = Exception(GHOST_ERROR)

        self._run(board_obj)

        data = self.fixture.read()
        self.assertEqual(
            data["issues"], [],
            f"Lista de issues deveria estar vazia, mas contém: {data['issues']}",
        )

    def test_emite_warning_ao_tratar_issue_fantasma(self):
        """Um log de warning deve ser emitido identificando a issue fantasma e o board."""
        board_obj = MagicMock()
        board_obj.close_issue.side_effect = Exception(GHOST_ERROR)

        warning_calls = []
        original_warning = sync_module.log.warning

        def capture_warning(module, msg, *args, **kwargs):
            warning_calls.append(msg)
            original_warning(module, msg, *args, **kwargs)

        with patch.object(sync_module.log, "warning", side_effect=capture_warning):
            self._run(board_obj)

        self.assertTrue(
            warning_calls,
            "Nenhum log.warning foi emitido ao tratar issue fantasma",
        )
        mensagem_completa = " ".join(warning_calls)
        self.assertTrue(
            ISSUE_ID in mensagem_completa or "fantasma" in mensagem_completa.lower(),
            f"Warning não menciona a issue #{ISSUE_ID} ou 'fantasma'. "
            f"Mensagens: {warning_calls}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# CT-C3-02: _apply_delete_up — outra exceção → re-raise (sem regressão)
# ─────────────────────────────────────────────────────────────────────────────

class TestApplyDeleteUpOutraExcecao(unittest.TestCase):
    """CT-C3-02: close_issue falha com erro transitório → re-raise obrigatório."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.fixture = SnapshotFixture(self.tmp_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, board_obj):
        item = _make_change_item(SyncEvent.DELETE_UP)
        with patch.object(sync_module, "BOARDS_DIR", self.tmp_path), \
             patch("src.core.snapshot.BOARDS_DIR", self.tmp_path):
            _apply_delete_up(BOARD_ID, item, board_obj)

    def test_propaga_excecao_nao_relacionada_a_issue_fantasma(self):
        """Erros que não são 'Could not resolve...' devem ser propagados normalmente."""
        board_obj = MagicMock()
        board_obj.close_issue.side_effect = Exception(OTHER_ERROR)

        with self.assertRaises(Exception) as ctx:
            self._run(board_obj)

        self.assertIn(
            OTHER_ERROR, str(ctx.exception),
            "A exceção propagada deve ser a original (sem alteração da mensagem)",
        )

    def test_snapshot_permanece_inalterado_ao_re_raise(self):
        """Quando a exceção é re-raised, o snapshot não deve ser alterado."""
        board_obj = MagicMock()
        board_obj.close_issue.side_effect = Exception(OTHER_ERROR)

        ids_antes = self.fixture.issue_ids()
        try:
            self._run(board_obj)
        except Exception:
            pass

        ids_depois = self.fixture.issue_ids()
        self.assertEqual(
            ids_antes, ids_depois,
            "Snapshot foi modificado indevidamente quando a exceção deveria ser re-raised",
        )

    def test_propaga_penalty_exception(self):
        """PenaltyException deve ser propagada (comportamento inalterado do caller)."""
        board_obj = MagicMock()
        board_obj.close_issue.side_effect = PenaltyException(wait_seconds=64)

        item = _make_change_item(SyncEvent.DELETE_UP)
        with patch.object(sync_module, "BOARDS_DIR", self.tmp_path), \
             patch("src.core.snapshot.BOARDS_DIR", self.tmp_path):
            with self.assertRaises(PenaltyException):
                _apply_delete_up(BOARD_ID, item, board_obj)


# ─────────────────────────────────────────────────────────────────────────────
# CT-C3-03: _apply_change_up — issue fantasma → descarte sem re-raise
# ─────────────────────────────────────────────────────────────────────────────

class TestApplyChangeUpIssueFantasma(unittest.TestCase):
    """CT-C3-03: update_issue falha com 'Could not resolve...' → descarte silencioso."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        # Criar estrutura de arquivo body para _apply_change_up encontrar
        col_dir = self.tmp_path / BOARD_ID / "doing"
        col_dir.mkdir(parents=True)
        self.body_file = col_dir / f"{ISSUE_ID}-slug-body.md"
        self.body_file.write_text(
            f"# Título da Issue Fantasma\n\nConteúdo da issue #{ISSUE_ID}.",
            encoding="utf-8",
        )
        # Snapshot aponta para o arquivo body
        snap_path = self.tmp_path / BOARD_ID / "snapshot.json"
        snap_data = _make_snapshot_data(ISSUE_ID)
        snap_data["issues"][0]["body_path"] = str(self.body_file)
        snap_data["issues"][0]["status"] = "change-up"
        snap_path.write_text(json.dumps(snap_data, indent=2), encoding="utf-8")
        self.snap_path = snap_path

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, board_obj):
        item = _make_change_item(SyncEvent.CHANGE_UP)
        with patch.object(sync_module, "BOARDS_DIR", self.tmp_path), \
             patch("src.core.snapshot.BOARDS_DIR", self.tmp_path):
            _apply_change_up(BOARD_ID, item, board_obj)

    def _snapshot_ids(self) -> list[str]:
        data = json.loads(self.snap_path.read_text(encoding="utf-8"))
        return [str(i["id"]) for i in data.get("issues", [])]

    def test_nao_propaga_excecao_de_issue_fantasma(self):
        """_apply_change_up não deve levantar exceção quando issue é fantasma."""
        board_obj = MagicMock()
        board_obj.update_issue.side_effect = Exception(GHOST_ERROR)

        try:
            self._run(board_obj)
        except Exception as exc:
            self.fail(
                f"_apply_change_up propagou exceção para issue fantasma: {exc}"
            )

    def test_remove_issue_do_snapshot_apos_erro_fantasma(self):
        """Snapshot não deve conter mais o id da issue fantasma após o tratamento."""
        board_obj = MagicMock()
        board_obj.update_issue.side_effect = Exception(GHOST_ERROR)

        self._run(board_obj)

        ids = self._snapshot_ids()
        self.assertNotIn(
            ISSUE_ID, ids,
            f"Issue #{ISSUE_ID} ainda está no snapshot após tratamento de fantasma: {ids}",
        )

    def test_emite_warning_ao_tratar_issue_fantasma(self):
        """Um log de warning deve ser emitido identificando a issue fantasma e o board."""
        board_obj = MagicMock()
        board_obj.update_issue.side_effect = Exception(GHOST_ERROR)

        warning_calls = []
        original_warning = sync_module.log.warning

        def capture_warning(module, msg, *args, **kwargs):
            warning_calls.append(msg)
            original_warning(module, msg, *args, **kwargs)

        with patch.object(sync_module.log, "warning", side_effect=capture_warning):
            self._run(board_obj)

        self.assertTrue(
            warning_calls,
            "Nenhum log.warning foi emitido ao tratar issue fantasma",
        )
        mensagem_completa = " ".join(warning_calls)
        self.assertTrue(
            ISSUE_ID in mensagem_completa or "fantasma" in mensagem_completa.lower(),
            f"Warning não menciona a issue #{ISSUE_ID} ou 'fantasma'. "
            f"Mensagens: {warning_calls}",
        )

    def test_nao_chama_operacoes_de_board_apos_erro_fantasma(self):
        """Após detectar issue fantasma, não deve tentar aplicar comandos ou mover no board."""
        board_obj = MagicMock()
        board_obj.update_issue.side_effect = Exception(GHOST_ERROR)

        self._run(board_obj)

        board_obj.apply_commands.assert_not_called()
        board_obj.move_issue.assert_not_called()
        board_obj.add_comment.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# CT-C3-04: _apply_change_up — outra exceção → re-raise (sem regressão)
# ─────────────────────────────────────────────────────────────────────────────

class TestApplyChangeUpOutraExcecao(unittest.TestCase):
    """CT-C3-04: update_issue falha com erro transitório → re-raise obrigatório."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        col_dir = self.tmp_path / BOARD_ID / "doing"
        col_dir.mkdir(parents=True)
        self.body_file = col_dir / f"{ISSUE_ID}-slug-body.md"
        self.body_file.write_text(
            f"# Título da Issue\n\nConteúdo.", encoding="utf-8"
        )
        self.snap_path = self.tmp_path / BOARD_ID / "snapshot.json"
        snap_data = _make_snapshot_data(ISSUE_ID)
        snap_data["issues"][0]["body_path"] = str(self.body_file)
        snap_data["issues"][0]["status"] = "change-up"
        self.snap_path.write_text(json.dumps(snap_data, indent=2), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, board_obj):
        item = _make_change_item(SyncEvent.CHANGE_UP)
        with patch.object(sync_module, "BOARDS_DIR", self.tmp_path), \
             patch("src.core.snapshot.BOARDS_DIR", self.tmp_path):
            _apply_change_up(BOARD_ID, item, board_obj)

    def test_propaga_excecao_nao_relacionada_a_issue_fantasma(self):
        """Erros que não são 'Could not resolve...' devem ser propagados normalmente."""
        board_obj = MagicMock()
        board_obj.update_issue.side_effect = Exception(OTHER_ERROR)

        with self.assertRaises(Exception) as ctx:
            self._run(board_obj)

        self.assertIn(
            OTHER_ERROR, str(ctx.exception),
            "A exceção propagada deve ser a original",
        )

    def test_snapshot_nao_alterado_ao_re_raise(self):
        """Snapshot não deve ser alterado quando a exceção é re-raised."""
        board_obj = MagicMock()
        board_obj.update_issue.side_effect = Exception(OTHER_ERROR)

        data_antes = json.loads(self.snap_path.read_text(encoding="utf-8"))
        ids_antes = [str(i["id"]) for i in data_antes["issues"]]

        try:
            self._run(board_obj)
        except Exception:
            pass

        data_depois = json.loads(self.snap_path.read_text(encoding="utf-8"))
        ids_depois = [str(i["id"]) for i in data_depois["issues"]]

        self.assertEqual(
            ids_antes, ids_depois,
            "Snapshot foi modificado indevidamente no path de re-raise",
        )

    def test_propaga_penalty_exception(self):
        """PenaltyException deve ser propagada (comportamento inalterado do caller)."""
        board_obj = MagicMock()
        board_obj.update_issue.side_effect = PenaltyException(wait_seconds=32)

        item = _make_change_item(SyncEvent.CHANGE_UP)
        with patch.object(sync_module, "BOARDS_DIR", self.tmp_path), \
             patch("src.core.snapshot.BOARDS_DIR", self.tmp_path):
            with self.assertRaises(PenaltyException):
                _apply_change_up(BOARD_ID, item, board_obj)


# ─────────────────────────────────────────────────────────────────────────────
# CT-C3-05: Múltiplas issues no snapshot — apenas a fantasma é removida
# ─────────────────────────────────────────────────────────────────────────────

class TestIsolamentoRemocaoSnapshot(unittest.TestCase):
    """CT-C3-05: Apenas a issue fantasma é removida; outras permanecem intactas."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        board_dir = self.tmp_path / BOARD_ID
        board_dir.mkdir(parents=True)
        self.snap_path = board_dir / "snapshot.json"
        snap_data = {
            "board": {"todo": "To Do", "doing": "Doing"},
            "issues": [
                {"id": "42", "column": "doing", "body_path": "p1", "status": "delete-up"},
                {"id": "43", "column": "doing", "body_path": "p2", "status": "ok"},
                {"id": "44", "column": "todo",  "body_path": "p3", "status": "ok"},
            ],
            "last_sync": None,
            "last_board_update": None,
        }
        self.snap_path.write_text(json.dumps(snap_data, indent=2), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_apenas_issue_fantasma_removida_do_snapshot(self):
        """Após delete-up fantasma de #42, as issues #43 e #44 devem permanecer."""
        board_obj = MagicMock()
        board_obj.close_issue.side_effect = Exception(GHOST_ERROR)

        item = _make_change_item(SyncEvent.DELETE_UP, issue_id="42")
        with patch.object(sync_module, "BOARDS_DIR", self.tmp_path), \
             patch("src.core.snapshot.BOARDS_DIR", self.tmp_path):
            _apply_delete_up(BOARD_ID, item, board_obj)

        data = json.loads(self.snap_path.read_text(encoding="utf-8"))
        ids = [str(i["id"]) for i in data["issues"]]

        self.assertNotIn("42", ids, "Issue fantasma #42 deveria ter sido removida")
        self.assertIn("43", ids, "Issue #43 foi removida indevidamente")
        self.assertIn("44", ids, "Issue #44 foi removida indevidamente")
        self.assertEqual(
            len(ids), 2,
            f"Esperado 2 issues restantes, encontrado {len(ids)}: {ids}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# CT-C3-06: Caminho feliz — _apply_delete_up sem erro
# ─────────────────────────────────────────────────────────────────────────────

class TestApplyDeleteUpCaminhoFeliz(unittest.TestCase):
    """CT-C3-06: delete_up sem erro → issue fechada e removida do snapshot normalmente."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.fixture = SnapshotFixture(self.tmp_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_issue_fechada_e_removida_do_snapshot_no_caminho_feliz(self):
        """Sem exceção, close_issue é chamado e a issue sai do snapshot."""
        board_obj = MagicMock()
        board_obj.close_issue.return_value = None  # Sucesso

        item = _make_change_item(SyncEvent.DELETE_UP)
        with patch.object(sync_module, "BOARDS_DIR", self.tmp_path), \
             patch("src.core.snapshot.BOARDS_DIR", self.tmp_path):
            _apply_delete_up(BOARD_ID, item, board_obj)

        board_obj.close_issue.assert_called_once_with(BOARD_ID, ISSUE_ID)

        ids = self.fixture.issue_ids()
        self.assertNotIn(
            ISSUE_ID, ids,
            f"Issue #{ISSUE_ID} deveria ter sido removida do snapshot no caminho feliz",
        )


# ─────────────────────────────────────────────────────────────────────────────
# CT-C3-07: Discriminação da substring do erro fantasma
# ─────────────────────────────────────────────────────────────────────────────

class TestDiscriminacaoErroFantasma(unittest.TestCase):
    """CT-C3-07: Apenas a substring exata discrimina o erro irrecuperável."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.fixture = SnapshotFixture(self.tmp_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _run_delete(self, board_obj):
        item = _make_change_item(SyncEvent.DELETE_UP)
        with patch.object(sync_module, "BOARDS_DIR", self.tmp_path), \
             patch("src.core.snapshot.BOARDS_DIR", self.tmp_path):
            _apply_delete_up(BOARD_ID, item, board_obj)

    def test_mensagem_sem_substring_fantasma_e_re_raised(self):
        """Mensagem de erro de rede (sem 'Could not resolve to an issue...') → re-raise."""
        board_obj = MagicMock()
        # "Could not resolve hostname" é um erro de DNS, não de issue inexistente
        board_obj.close_issue.side_effect = Exception(
            "Could not resolve hostname: api.github.com"
        )

        with self.assertRaises(Exception) as ctx:
            self._run_delete(board_obj)

        self.assertIn("hostname", str(ctx.exception))

    def test_mensagem_exata_do_github_e_tratada_como_fantasma(self):
        """A mensagem exata retornada pelo GitHub é tratada como erro irrecuperável."""
        board_obj = MagicMock()
        board_obj.close_issue.side_effect = Exception(
            "Could not resolve to an issue or pull request with the number of 42"
        )

        try:
            self._run_delete(board_obj)
        except Exception as exc:
            self.fail(
                f"Mensagem exata do GitHub deveria ser tratada como fantasma: {exc}"
            )

    def test_mensagem_com_numero_diferente_tambem_e_tratada(self):
        """O número da issue na mensagem pode variar; a substring é o discriminador."""
        board_obj = MagicMock()
        board_obj.close_issue.side_effect = Exception(
            "Could not resolve to an issue or pull request with the number of 999"
        )

        try:
            self._run_delete(board_obj)
        except Exception as exc:
            self.fail(
                f"Erro de issue inexistente (número diferente) deveria ser tratado: {exc}"
            )

    def test_variante_uppercase_nao_e_tratada(self):
        """Verificação é case-sensitive: substring uppercase não deve ser tratada como fantasma."""
        board_obj = MagicMock()
        # A API do GitHub retorna lowercase; uppercase não deve ser capturado
        board_obj.close_issue.side_effect = Exception(
            "COULD NOT RESOLVE TO AN ISSUE OR PULL REQUEST WITH THE NUMBER OF 42"
        )

        # Deve re-raise porque a substring exata (lowercase) não está presente
        with self.assertRaises(Exception):
            self._run_delete(board_obj)


if __name__ == "__main__":
    unittest.main(verbosity=2)
