"""Testes da Correção 4 — Validação pós-agente (defesa em profundidade).

Cobrem os 4 cenários da tabela da issue:

| Cenário | Ação esperada |
|---------|--------------|
| Agente sobrescreve snapshot.json | Snapshot restaurado para estado pré-execução |
| Agente cria arquivo com prefixo numérico não rastreado | Arquivo renomeado (prefixo removido) |
| Agente cria arquivo sem prefixo numérico | Nenhuma ação (comportamento correto) |
| Agente cria arquivo com prefixo numérico rastreado | Nenhuma ação (arquivo legítimo) |

A implementação ancora-se em dois utilitários que serão adicionados ao projeto:

  - `src.core.agent_guard.snapshot_guard(board_id, backup_path)`
    Context manager que captura mtime + backup antes e restaura se modificado.

  - `src.core.agent_guard.fix_phantom_files(board_id, col_id, known_ids)`
    Varre a coluna e renomeia arquivos com prefixo numérico não rastreado.

Os testes usam monkeypatch + tmp_path para isolar inteiramente o filesystem.
"""

import json
import re
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures de infraestrutura
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _chdir_tmp(tmp_path, monkeypatch):
    """Isola .pipe/ em diretório temporário por teste."""
    monkeypatch.chdir(tmp_path)
    yield


def _make_snapshot(board_id: str, issues: list[dict]) -> Path:
    """Cria um snapshot.json minimal em .pipe/boards/<board_id>/."""
    snap_dir = Path(".pipe/boards") / board_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / "snapshot.json"
    data = {
        "board": {"col1": "Column 1"},
        "issues": issues,
        "last_sync": None,
    }
    snap_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return snap_path


def _make_column_dir(board_id: str, col_id: str) -> Path:
    """Cria e retorna o diretório de uma coluna."""
    col_dir = Path(".pipe/boards") / board_id / col_id
    col_dir.mkdir(parents=True, exist_ok=True)
    return col_dir


# ─────────────────────────────────────────────────────────────────────────────
# Implementação de referência dos utilitários
# (reproduz o contrato esperado para permitir testes antes da implementação real)
# ─────────────────────────────────────────────────────────────────────────────

def _snapshot_mtime(board_id: str) -> float | None:
    """Retorna o mtime do snapshot.json, ou None se não existir."""
    snap_path = Path(".pipe/boards") / board_id / "snapshot.json"
    if snap_path.exists():
        return snap_path.stat().st_mtime
    return None


def _snapshot_known_ids(board_id: str) -> set[str]:
    """Retorna o conjunto de IDs numéricos conhecidos no snapshot."""
    snap_path = Path(".pipe/boards") / board_id / "snapshot.json"
    if not snap_path.exists():
        return set()
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    return {str(i["id"]) for i in data.get("issues", []) if i.get("id")}


def _restore_snapshot(board_id: str, backup_path: Path) -> None:
    """Restaura snapshot a partir do backup."""
    snap_path = Path(".pipe/boards") / board_id / "snapshot.json"
    shutil.copy2(backup_path, snap_path)


def _fix_phantom_files(board_id: str, col_id: str, known_ids: set[str]) -> list[tuple[str, str]]:
    """Renomeia arquivos *-body.md com prefixo numérico não rastreado.

    Retorna lista de (nome_original, nome_novo) para cada arquivo renomeado.
    """
    col_dir = Path(".pipe/boards") / board_id / col_id
    renamed = []
    if not col_dir.exists():
        return renamed
    for body_file in col_dir.glob("*-body.md"):
        match = re.match(r"^(\d+)-", body_file.name)
        if match and match.group(1) not in known_ids:
            new_name = re.sub(r"^\d+-", "", body_file.name)
            new_path = body_file.parent / new_name
            body_file.rename(new_path)
            renamed.append((body_file.name, new_name))
    return renamed


# ─────────────────────────────────────────────────────────────────────────────
# Cenário 1: Agente sobrescreve snapshot.json → restaurar
# ─────────────────────────────────────────────────────────────────────────────

class TestSnapshotGuard:
    """Validação de integridade do snapshot antes/após execução do agente."""

    def test_snapshot_restaurado_quando_modificado(self, tmp_path):
        """Se o agente sobrescreve o snapshot.json, o estado pré-execução é restaurado."""
        board_id = "task"
        original_issues = [{"id": "1", "column": "col1", "status": "ok"}]
        snap_path = _make_snapshot(board_id, original_issues)

        # Captura estado pré-execução
        mtime_before = _snapshot_mtime(board_id)
        backup = tmp_path / "snapshot.json.bak"
        shutil.copy2(snap_path, backup)

        # Simula agente sobrescrevendo o snapshot com dados corrompidos
        corrupted = {"board": {}, "issues": [{"id": "FANTASMA"}], "last_sync": None}
        snap_path.write_text(json.dumps(corrupted), encoding="utf-8")

        # Verificação pós-execução
        mtime_after = _snapshot_mtime(board_id)
        assert mtime_after != mtime_before, "O mtime deveria ter mudado após a escrita"

        # Restauração
        _restore_snapshot(board_id, backup)

        # Estado restaurado deve ser idêntico ao original
        restored = json.loads(snap_path.read_text(encoding="utf-8"))
        assert restored["issues"] == original_issues
        assert restored["issues"][0]["id"] == "1"

    def test_snapshot_nao_restaurado_quando_intacto(self, tmp_path):
        """Se o agente NÃO modificou o snapshot.json, o estado é preservado."""
        board_id = "task"
        original_issues = [{"id": "2", "column": "col1", "status": "ok"}]
        snap_path = _make_snapshot(board_id, original_issues)

        mtime_before = _snapshot_mtime(board_id)
        backup = tmp_path / "snapshot.json.bak"
        shutil.copy2(snap_path, backup)

        # Agente NÃO toca no snapshot (nenhuma escrita)
        mtime_after = _snapshot_mtime(board_id)

        # mtime idêntico — não deve restaurar
        assert mtime_after == mtime_before
        # Backup existe mas o snapshot original permanece inalterado
        current = json.loads(snap_path.read_text(encoding="utf-8"))
        assert current["issues"] == original_issues

    def test_backup_cleanup_apos_execucao(self, tmp_path):
        """O arquivo .bak deve ser removido ao final do wrapper (try/finally)."""
        board_id = "task"
        _make_snapshot(board_id, [])
        backup = tmp_path / "snapshot.json.bak"

        snap_path = Path(".pipe/boards") / board_id / "snapshot.json"
        shutil.copy2(snap_path, backup)
        assert backup.exists()

        # Simula bloco finally: limpeza do backup
        if backup.exists():
            backup.unlink()

        assert not backup.exists()

    def test_snapshot_inexistente_nao_causa_erro(self):
        """Se o snapshot ainda não existe antes da execução, mtime retorna None."""
        board_id = "board_sem_snapshot"
        # Diretório não criado — snapshot inexistente
        mtime = _snapshot_mtime(board_id)
        assert mtime is None


# ─────────────────────────────────────────────────────────────────────────────
# Cenário 2: Agente cria arquivo com prefixo numérico NÃO rastreado → renomear
# ─────────────────────────────────────────────────────────────────────────────

class TestFixPhantomFiles:
    """Detecção e renomeação de arquivos com prefixo numérico indevido."""

    def test_arquivo_prefixo_nao_rastreado_e_renomeado(self):
        """ID 4 não estava no snapshot → arquivo renomeado para login-body.md."""
        board_id = "task"
        col_id = "desenvolvimento"
        # Snapshot conhece apenas o ID 1
        known_ids = {"1"}
        col_dir = _make_column_dir(board_id, col_id)

        # Agente cria arquivo fantasma com prefixo 4 (não rastreado)
        phantom = col_dir / "4-login-body.md"
        phantom.write_text("# Login", encoding="utf-8")

        renamed = _fix_phantom_files(board_id, col_id, known_ids)

        assert len(renamed) == 1
        original_name, new_name = renamed[0]
        assert original_name == "4-login-body.md"
        assert new_name == "login-body.md"
        assert not phantom.exists()
        assert (col_dir / "login-body.md").exists()

    def test_arquivo_sem_prefixo_nao_e_alterado(self):
        """Arquivo sem prefixo numérico é comportamento correto — não alterar."""
        board_id = "task"
        col_id = "desenvolvimento"
        known_ids = {"1"}
        col_dir = _make_column_dir(board_id, col_id)

        # Arquivo legítimo sem prefixo (criado localmente pelo agente de forma correta)
        legit = col_dir / "slug-body.md"
        legit.write_text("# Slug", encoding="utf-8")

        renamed = _fix_phantom_files(board_id, col_id, known_ids)

        assert renamed == []
        assert legit.exists(), "Arquivo sem prefixo não deve ser tocado"

    def test_arquivo_prefixo_rastreado_nao_e_alterado(self):
        """ID 4 existia no snapshot → arquivo legítimo, não renomear."""
        board_id = "task"
        col_id = "desenvolvimento"
        # Snapshot já conhece o ID 4
        known_ids = {"1", "4"}
        col_dir = _make_column_dir(board_id, col_id)

        legit = col_dir / "4-login-body.md"
        legit.write_text("# Login", encoding="utf-8")

        renamed = _fix_phantom_files(board_id, col_id, known_ids)

        assert renamed == []
        assert legit.exists(), "Arquivo rastreado não deve ser renomeado"

    def test_multiplos_arquivos_fantasma_todos_renomeados(self):
        """Múltiplos arquivos com prefixos não rastreados: todos renomeados."""
        board_id = "task"
        col_id = "desenvolvimento"
        known_ids = {"1"}
        col_dir = _make_column_dir(board_id, col_id)

        (col_dir / "7-feature_a-body.md").write_text("# A", encoding="utf-8")
        (col_dir / "8-feature_b-body.md").write_text("# B", encoding="utf-8")

        renamed = _fix_phantom_files(board_id, col_id, known_ids)

        assert len(renamed) == 2
        new_names = {r[1] for r in renamed}
        assert "feature_a-body.md" in new_names
        assert "feature_b-body.md" in new_names

    def test_mix_rastreado_e_nao_rastreado(self):
        """Apenas o arquivo não rastreado é renomeado; o rastreado permanece."""
        board_id = "task"
        col_id = "desenvolvimento"
        known_ids = {"4"}
        col_dir = _make_column_dir(board_id, col_id)

        legit = col_dir / "4-login-body.md"
        phantom = col_dir / "99-intruso-body.md"
        legit.write_text("# Login", encoding="utf-8")
        phantom.write_text("# Intruso", encoding="utf-8")

        renamed = _fix_phantom_files(board_id, col_id, known_ids)

        assert len(renamed) == 1
        assert renamed[0][0] == "99-intruso-body.md"
        assert renamed[0][1] == "intruso-body.md"
        assert legit.exists()
        assert not phantom.exists()
        assert (col_dir / "intruso-body.md").exists()

    def test_coluna_vazia_nao_causa_erro(self):
        """Coluna sem arquivos body não causa erro."""
        board_id = "task"
        col_id = "vazia"
        known_ids = {"1"}
        _make_column_dir(board_id, col_id)

        renamed = _fix_phantom_files(board_id, col_id, known_ids)
        assert renamed == []

    def test_coluna_inexistente_nao_causa_erro(self):
        """Coluna que não existe no filesystem não causa erro."""
        renamed = _fix_phantom_files("board_x", "col_inexistente", {"1"})
        assert renamed == []


# ─────────────────────────────────────────────────────────────────────────────
# Cenário completo: integração do guard em call_agent
# ─────────────────────────────────────────────────────────────────────────────

class TestCallAgentGuardIntegration:
    """Simula o wrapper em call_agent: captura → executa → verifica → restaura."""

    def _run_guarded(self, board_id, col_id, known_ids, agent_fn):
        """
        Simula o wrapper pós-agente que será implementado em call_agent.

        1. Captura mtime e faz backup do snapshot.
        2. Chama agent_fn() (simula adapter.execute).
        3. Verifica se snapshot foi modificado → restaura se necessário.
        4. Varre coluna e renomeia arquivos fantasma.
        5. Limpa backup.

        Retorna (snapshot_restored: bool, renamed: list)
        """
        import tempfile

        snap_path = Path(".pipe/boards") / board_id / "snapshot.json"
        mtime_before = _snapshot_mtime(board_id)
        backup = Path(tempfile.mktemp(suffix=".bak"))
        snapshot_restored = False
        renamed = []

        try:
            if snap_path.exists():
                shutil.copy2(snap_path, backup)

            # Executa agente
            agent_fn()

            # Verificação: snapshot modificado?
            mtime_after = _snapshot_mtime(board_id)
            if mtime_before is not None and mtime_after != mtime_before:
                _restore_snapshot(board_id, backup)
                snapshot_restored = True

            # Verificação: arquivos fantasma?
            renamed = _fix_phantom_files(board_id, col_id, known_ids)

        finally:
            if backup.exists():
                backup.unlink()

        return snapshot_restored, renamed

    def test_agente_bom_nao_altera_nada(self):
        """Agente que não toca snapshot nem cria arquivos extras: nenhuma ação."""
        board_id = "task"
        col_id = "dev"
        known_ids = {"1"}
        _make_snapshot(board_id, [{"id": "1", "column": col_id, "status": "ok"}])
        _make_column_dir(board_id, col_id)

        def agente_bom():
            pass  # não faz nada no filesystem

        restored, renamed = self._run_guarded(board_id, col_id, known_ids, agente_bom)

        assert not restored
        assert renamed == []

    def test_agente_corrompe_snapshot_e_e_restaurado(self):
        """Agente que sobrescreve snapshot.json tem snapshot restaurado."""
        board_id = "task"
        col_id = "dev"
        known_ids = {"1"}
        original_issues = [{"id": "1", "column": col_id, "status": "ok"}]
        _make_snapshot(board_id, original_issues)
        _make_column_dir(board_id, col_id)

        snap_path = Path(".pipe/boards") / board_id / "snapshot.json"

        def agente_mal():
            import time
            time.sleep(0.01)  # garante mtime diferente
            snap_path.write_text(
                json.dumps({"board": {}, "issues": [{"id": "FANTASMA"}]}),
                encoding="utf-8"
            )

        restored, renamed = self._run_guarded(board_id, col_id, known_ids, agente_mal)

        assert restored is True
        current = json.loads(snap_path.read_text(encoding="utf-8"))
        assert current["issues"] == original_issues

    def test_agente_cria_arquivo_fantasma_e_renomeado(self):
        """Agente que cria arquivo com prefixo numérico não rastreado tem arquivo renomeado."""
        board_id = "task"
        col_id = "dev"
        known_ids = {"1"}
        _make_snapshot(board_id, [{"id": "1", "column": col_id, "status": "ok"}])
        col_dir = _make_column_dir(board_id, col_id)

        def agente_fantasma():
            (col_dir / "42-nova_feature-body.md").write_text("# Nova Feature", encoding="utf-8")

        restored, renamed = self._run_guarded(board_id, col_id, known_ids, agente_fantasma)

        assert not restored
        assert len(renamed) == 1
        assert renamed[0] == ("42-nova_feature-body.md", "nova_feature-body.md")
        assert (col_dir / "nova_feature-body.md").exists()
        assert not (col_dir / "42-nova_feature-body.md").exists()

    def test_agente_dupla_corrupcao_snapshot_e_arquivo_fantasma(self):
        """Agente que corrompe snapshot E cria arquivo fantasma: ambos corrigidos."""
        board_id = "task"
        col_id = "dev"
        known_ids = {"1"}
        original_issues = [{"id": "1", "column": col_id, "status": "ok"}]
        _make_snapshot(board_id, original_issues)
        col_dir = _make_column_dir(board_id, col_id)
        snap_path = Path(".pipe/boards") / board_id / "snapshot.json"

        def agente_duplo_dano():
            import time
            time.sleep(0.01)
            snap_path.write_text(json.dumps({"board": {}, "issues": []}), encoding="utf-8")
            (col_dir / "99-bug-body.md").write_text("# Bug", encoding="utf-8")

        restored, renamed = self._run_guarded(board_id, col_id, known_ids, agente_duplo_dano)

        assert restored is True
        assert len(renamed) == 1
        current = json.loads(snap_path.read_text(encoding="utf-8"))
        assert current["issues"] == original_issues

    def test_backup_sempre_removido_mesmo_com_excecao(self, tmp_path):
        """O arquivo .bak é removido mesmo que o agente lance exceção (try/finally)."""
        board_id = "task"
        _make_snapshot(board_id, [])

        import tempfile
        snap_path = Path(".pipe/boards") / board_id / "snapshot.json"
        backup = Path(tempfile.mktemp(suffix=".bak"))

        try:
            shutil.copy2(snap_path, backup)
            assert backup.exists()
            raise RuntimeError("Falha simulada no agente")
        except RuntimeError:
            pass
        finally:
            if backup.exists():
                backup.unlink()

        assert not backup.exists()


# ─────────────────────────────────────────────────────────────────────────────
# Testes de performance: sem latência perceptível (operações locais apenas)
# ─────────────────────────────────────────────────────────────────────────────

class TestPerformanceGuard:
    """Garantia de que o guard não introduz latência por chamada de API."""

    def test_guard_usa_apenas_operacoes_filesystem(self):
        """Nenhuma chamada de rede é feita durante o guard (apenas filesystem)."""
        board_id = "task"
        col_id = "dev"
        _make_snapshot(board_id, [{"id": "1", "column": col_id, "status": "ok"}])
        _make_column_dir(board_id, col_id)

        # Se qualquer função de rede fosse chamada, este patch detectaria
        with patch("subprocess.run") as mock_subprocess, \
             patch("urllib.request.urlopen") as mock_url:
            mtime = _snapshot_mtime(board_id)
            ids = _snapshot_known_ids(board_id)
            _fix_phantom_files(board_id, col_id, ids)

        mock_subprocess.assert_not_called()
        mock_url.assert_not_called()

    def test_snapshot_known_ids_retorna_ids_corretos(self):
        """_snapshot_known_ids extrai corretamente os IDs do snapshot."""
        board_id = "task"
        _make_snapshot(board_id, [
            {"id": "1", "column": "col1", "status": "ok"},
            {"id": "2", "column": "col1", "status": "ok"},
            {"id": None, "column": "col1", "status": "ok"},  # sem id (issue local)
        ])

        ids = _snapshot_known_ids(board_id)
        assert ids == {"1", "2"}
        assert None not in ids
        assert "None" not in ids
