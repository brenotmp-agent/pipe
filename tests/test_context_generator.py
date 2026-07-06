"""Testes do gerador de CONTEXT.md (src/core/context_generator.py).

Cobrem os critérios de aceitação da Correção 2 — CONTEXT.md gerado no startup:

1. generate_context() cria .pipe/CONTEXT.md se não existir.
2. generate_context() regenera se pipe.yml foi modificado após o CONTEXT.md.
3. generate_context() não sobrescreve se pipe.yml não foi modificado (sem mudança).
4. O CONTEXT.md gerado lista todos os arquivos protegidos (snapshot.json,
   changeQueue.json, throttle.json, sessions.json).
5. O CONTEXT.md instrui explicitamente sobre nomeação sem prefixo numérico.
6. O CONTEXT.md documenta boards, colunas e flows derivados do pipe.yml.
7. O CONTEXT.md documenta prefixos de branch.
8. build_prompt inclui o conteúdo do CONTEXT.md como seção de contexto.
9. generate_context() com config vazio (sem boards) não levanta exceção.
10. Múltiplos boards são documentados corretamente.
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ── Fixture de config mínima ──────────────────────────────────────────────────

def _minimal_config() -> dict:
    """Config mínima com um board e um flow para testes gerais."""
    return {
        "sleep": 60,
        "git": {
            "repo": {"main": "git@github.com:user/repo.git"},
            "flow": {
                "base": "main",
                "feature": {
                    "prefix": "feature/",
                    "create": "main",
                    "merge": "main",
                },
            },
        },
        "agents": {
            "kiro-cli": {
                "engineering": {"name": "Engenharia", "model": "claude-sonnet-4"},
            }
        },
        "boards": {
            "platform": "github",
            "backlog": {
                "name": "Backlog",
                "flow": "feature",
                "columns": {
                    "todo": {"name": "To Do"},
                    "doing": {
                        "name": "Em Desenvolvimento",
                        "agent": "engineering",
                        "gitevents": "create",
                    },
                    "done": {"name": "Concluído", "archive": True},
                },
            },
        },
    }


def _multi_board_config() -> dict:
    """Config com dois boards para testar documentação múltipla."""
    cfg = _minimal_config()
    cfg["boards"]["task"] = {
        "name": "Task Board",
        "flow": "feature",
        "columns": {
            "casos-de-teste": {"name": "Casos de Teste", "agent": "engineering"},
            "desenvolvimento": {"name": "Desenvolvimento", "agent": "engineering"},
        },
    }
    cfg["git"]["flow"]["hotfix"] = {
        "prefix": "hotfix/",
        "create": "main",
        "merge": "main",
    }
    return cfg


@pytest.fixture(autouse=True)
def _chdir_tmp(tmp_path, monkeypatch):
    """Isola .pipe/ e pipe.yml em diretório temporário por teste."""
    monkeypatch.chdir(tmp_path)
    # Cria um pipe.yml mínimo para que as funções que o precisam encontrem
    import yaml
    (tmp_path / "pipe.yml").write_text(
        yaml.dump(_minimal_config()), encoding="utf-8"
    )
    yield


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pipe_dir(tmp_path=None) -> Path:
    return Path(".pipe")


def _context_path() -> Path:
    return Path(".pipe") / "CONTEXT.md"


def _write_context(content: str = "# old"):
    path = _context_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ── 1. Criação quando não existe ──────────────────────────────────────────────

def test_generate_cria_context_se_nao_existir():
    """generate_context() deve criar .pipe/CONTEXT.md quando ele não existe."""
    from src.core.context_generator import generate_context

    assert not _context_path().exists()
    generate_context(_minimal_config())
    assert _context_path().exists()
    assert _context_path().stat().st_size > 0


# ── 2. Regenera quando pipe.yml é mais novo ───────────────────────────────────

def test_generate_regenera_quando_pipeyml_modificado(tmp_path):
    """generate_context() deve sobrescrever .pipe/CONTEXT.md se pipe.yml mudou depois."""
    from src.core.context_generator import generate_context

    _write_context("# conteudo antigo")
    old_content = _context_path().read_text(encoding="utf-8")

    # Garante que pipe.yml seja mais novo que o CONTEXT.md existente
    time.sleep(0.01)
    (tmp_path / "pipe.yml").touch()

    generate_context(_minimal_config())
    new_content = _context_path().read_text(encoding="utf-8")

    assert new_content != old_content, "Deve sobrescrever quando pipe.yml é mais novo"


# ── 3. Não sobrescreve quando já atualizado ───────────────────────────────────

def test_generate_nao_sobrescreve_se_atualizado(tmp_path):
    """generate_context() NÃO deve sobrescrever se CONTEXT.md é mais novo que pipe.yml."""
    from src.core.context_generator import generate_context

    # CONTEXT.md existe e é mais novo que pipe.yml
    time.sleep(0.01)
    _write_context("# conteudo atual valido")

    generate_context(_minimal_config())
    content = _context_path().read_text(encoding="utf-8")

    assert content == "# conteudo atual valido", "Não deve sobrescrever CONTEXT.md atualizado"


# ── 4. Arquivos protegidos listados ──────────────────────────────────────────

class TestArquivosProtegidos:
    """O CONTEXT.md gerado deve listar todos os arquivos de estado interno proibidos."""

    def _get_content(self):
        from src.core.context_generator import generate_context
        generate_context(_minimal_config())
        return _context_path().read_text(encoding="utf-8")

    def test_snapshot_json_listado(self):
        assert "snapshot.json" in self._get_content()

    def test_changequeue_json_listado(self):
        content = self._get_content()
        # Pode aparecer como changeQueue.json ou change_queue.json
        assert "changeQueue.json" in content or "change_queue.json" in content.lower()

    def test_throttle_json_listado(self):
        assert "throttle.json" in self._get_content()

    def test_sessions_json_listado(self):
        assert "sessions.json" in self._get_content()

    def test_secao_restricoes_presente(self):
        """Deve haver uma seção clara de restrições/arquivos proibidos."""
        content = self._get_content()
        # A seção pode ter variações de nome, mas deve haver menção explícita
        has_restrictions = any(
            keyword in content.lower()
            for keyword in ["restri", "proibid", "nunca", "jamais", "não modif", "protegid"]
        )
        assert has_restrictions, "Deve conter seção com restrições explícitas"


# ── 5. Nomeação de issues sem prefixo numérico ───────────────────────────────

class TestNomeacaoIssues:
    """O CONTEXT.md deve instruir explicitamente sobre nomeação sem prefixo numérico."""

    def _get_content(self):
        from src.core.context_generator import generate_context
        generate_context(_minimal_config())
        return _context_path().read_text(encoding="utf-8")

    def test_instrucao_sem_prefixo_numerico(self):
        """Deve mencionar explicitamente que não se usa prefixo numérico no nome."""
        content = self._get_content()
        # Deve haver instrução proibindo padrão como "4-login-body.md"
        has_no_numeric = any(
            keyword in content.lower()
            for keyword in ["sem prefixo", "sem número", "sem numero", "não prefixe",
                            "nao prefixe", "without numeric", "no numeric prefix"]
        )
        assert has_no_numeric, "Deve instruir explicitamente contra prefixo numérico"

    def test_formato_correto_slug_body(self):
        """Deve documentar o formato correto: <slug>-body.md."""
        content = self._get_content()
        assert "-body.md" in content, "Deve documentar padrão <slug>-body.md"

    def test_formato_correto_slug_history(self):
        content = self._get_content()
        assert "-history.md" in content, "Deve documentar padrão <slug>-history.md"

    def test_formato_correto_slug_addcomment(self):
        content = self._get_content()
        assert "-addcomment.md" in content, "Deve documentar padrão <slug>-addcomment.md"

    def test_exemplo_errado_mencionado(self):
        """Deve dar exemplo do padrão errado (ex: 4-login-body.md) para deixar claro."""
        content = self._get_content()
        # Pode estar em formato como "4-login-body.md" ou "N-slug-body.md"
        has_bad_example = any(
            pattern in content
            for pattern in ["4-", "N-slug", "N-login", "<N>-", "errado", "incorreto", "wrong"]
        )
        assert has_bad_example, "Deve ilustrar o padrão errado para maior clareza"


# ── 6. Boards e colunas documentados ─────────────────────────────────────────

class TestBoardsEColunas:
    """O CONTEXT.md deve documentar boards e colunas derivados do pipe.yml."""

    def _get_content(self, config=None):
        from src.core.context_generator import generate_context
        generate_context(config or _minimal_config())
        return _context_path().read_text(encoding="utf-8")

    def test_nome_board_presente(self):
        assert "Backlog" in self._get_content()

    def test_id_board_presente(self):
        assert "backlog" in self._get_content()

    def test_colunas_do_board_presentes(self):
        content = self._get_content()
        assert "To Do" in content
        assert "Em Desenvolvimento" in content
        assert "Concluído" in content

    def test_multiplos_boards_documentados(self):
        content = self._get_content(_multi_board_config())
        assert "Backlog" in content
        assert "Task Board" in content

    def test_colunas_de_ambos_boards_presentes(self):
        content = self._get_content(_multi_board_config())
        assert "Casos de Teste" in content
        assert "Desenvolvimento" in content

    def test_flow_associado_ao_board(self):
        content = self._get_content()
        assert "feature" in content


# ── 7. Branches e prefixos documentados ──────────────────────────────────────

class TestBranchesPrefixos:
    """O CONTEXT.md deve documentar os prefixos de branch e flows disponíveis."""

    def _get_content(self, config=None):
        from src.core.context_generator import generate_context
        generate_context(config or _minimal_config())
        return _context_path().read_text(encoding="utf-8")

    def test_prefixo_feature_documentado(self):
        assert "feature/" in self._get_content()

    def test_branch_base_documentada(self):
        assert "main" in self._get_content()

    def test_multiplos_flows_documentados(self):
        content = self._get_content(_multi_board_config())
        assert "feature/" in content
        assert "hotfix/" in content

    def test_secao_de_branches_presente(self):
        content = self._get_content()
        has_branch_section = any(
            kw in content.lower()
            for kw in ["branch", "git flow", "flow"]
        )
        assert has_branch_section, "Deve ter seção sobre branches/flows"


# ── 8. build_prompt inclui CONTEXT.md ────────────────────────────────────────

class TestBuildPromptIncluyContexto:
    """build_prompt deve incluir o conteúdo do CONTEXT.md no prompt enviado ao agente."""

    def _build(self, tmp_path, context_content: str | None = None) -> str:
        from src.core.agent import build_prompt
        from src.core.snapshot import BOARDS_DIR

        # Criar estrutura mínima de board/issue
        board_dir = Path(".pipe/boards/backlog/doing")
        board_dir.mkdir(parents=True, exist_ok=True)

        issue_slug = "implementar-login"
        body_path = board_dir / f"{issue_slug}-body.md"
        body_path.write_text("# Implementar Login\n\nDescrição.", encoding="utf-8")

        if context_content is not None:
            ctx_path = Path(".pipe/CONTEXT.md")
            ctx_path.parent.mkdir(parents=True, exist_ok=True)
            ctx_path.write_text(context_content, encoding="utf-8")

        config = _minimal_config()
        task = {
            "board_id": "backlog",
            "board": config["boards"]["backlog"],
            "column": config["boards"]["backlog"]["columns"]["doing"],
            "col_id": "doing",
            "issue": {
                "id": "42",
                "body_path": str(body_path),
            },
        }
        return build_prompt(config, task)

    def test_context_presente_no_prompt(self, tmp_path):
        """Quando .pipe/CONTEXT.md existe, seu conteúdo deve aparecer no prompt."""
        marker = "## MARCADOR_UNICO_PARA_TESTE_DE_CONTEXTO"
        prompt = self._build(tmp_path, context_content=marker)
        assert marker in prompt, "O conteúdo do CONTEXT.md deve ser incluído no prompt"

    def test_prompt_funciona_sem_context_file(self, tmp_path):
        """build_prompt não deve falhar se .pipe/CONTEXT.md não existir."""
        # Não cria o arquivo CONTEXT.md
        try:
            prompt = self._build(tmp_path, context_content=None)
            assert isinstance(prompt, str)
        except Exception as e:
            pytest.fail(f"build_prompt não deve falhar sem CONTEXT.md: {e}")

    def test_context_nao_duplicado_no_prompt(self, tmp_path):
        """O conteúdo do CONTEXT.md não deve aparecer mais de uma vez no prompt."""
        marker = "SECAO_CONTEXTO_UNICA"
        prompt = self._build(tmp_path, context_content=f"# Contexto\n{marker}")
        count = prompt.count(marker)
        assert count == 1, f"CONTEXT.md deve aparecer exatamente 1 vez no prompt, apareceu {count}"


# ── 9. Config vazia não levanta exceção ──────────────────────────────────────

def test_generate_com_config_sem_boards_nao_falha():
    """generate_context() com config mínima sem boards não deve levantar exceção."""
    from src.core.context_generator import generate_context

    config_minimal = {
        "sleep": 60,
        "git": {
            "repo": {"main": "git@github.com:user/repo.git"},
            "flow": {"base": "main"},
        },
        "agents": {},
        "boards": {"platform": "github"},
    }
    try:
        generate_context(config_minimal)
    except Exception as e:
        pytest.fail(f"generate_context não deve falhar com config sem boards: {e}")


# ── 10. Múltiplos boards completamente documentados ──────────────────────────

def test_todos_boards_e_colunas_de_config_multi_board():
    """Todos os boards e suas colunas devem aparecer no CONTEXT.md gerado."""
    from src.core.context_generator import generate_context

    config = _multi_board_config()
    generate_context(config)
    content = _context_path().read_text(encoding="utf-8")

    # Board 1
    assert "Backlog" in content
    assert "To Do" in content
    assert "Em Desenvolvimento" in content

    # Board 2
    assert "Task Board" in content
    assert "Casos de Teste" in content
    assert "Desenvolvimento" in content

    # Flows
    assert "feature/" in content
    assert "hotfix/" in content
