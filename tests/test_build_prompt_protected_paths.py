"""Testes de proteção de paths sensíveis no prompt gerado por build_prompt.

Correção 1 — Snapshot como memória interna (read-only para agentes):
- O prompt enviado ao agente NÃO deve conter referências a arquivos de estado
  interno: snapshot.json, changeQueue.json, throttle.json (e variantes).
- A lista de padrões protegidos (PROTECTED_PATHS) deve ser centralizada no
  código (src/core/agent.py) e importável.
- O guard _assert_no_protected deve lançar ValueError se algum path protegido
  aparecer no prompt.

Os testes desta classe estão agrupados em:
  - TestProtectedPathsConstant   → verifica PROTECTED_PATHS (pós-implementação)
  - TestAssertNoProtected        → verifica _assert_no_protected (pós-implementação)
  - TestBuildPromptNaoExpoePaths → verifica o prompt gerado (parte já passa hoje;
                                   parte depende do guard implementado)
  - TestBuildPromptRegressao     → garantias de não-regressão (já devem passar hoje)
  - TestAgentToolsConfig         → documentação de interface para generate_native_agents

Referência: issue #8 — [Incidente Issue Fantasma] Correção 1.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.core.agent as _agent_module
from src.core.agent import build_prompt

# Importações condicionais: existem após a implementação da Correção 1.
PROTECTED_PATHS = getattr(_agent_module, "PROTECTED_PATHS", None)
_assert_no_protected = getattr(_agent_module, "_assert_no_protected", None)


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures compartilhadas
# ══════════════════════════════════════════════════════════════════════════════

def _minimal_config(tmp_path: Path) -> dict:
    """Config mínima válida para build_prompt."""
    return {
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
                "dev": {"name": "engineering", "model": "claude-sonnet-4"},
            }
        },
    }


def _minimal_task(tmp_path: Path, board_id: str = "myboard", col_id: str = "doing",
                  gitevents: str = "create") -> dict:
    """Task mínima com body e issue para build_prompt."""
    issue_dir = tmp_path / ".pipe" / "boards" / board_id / col_id
    issue_dir.mkdir(parents=True, exist_ok=True)

    body_path = issue_dir / "42-my-feature-body.md"
    body_path.write_text("# My Feature\n\nDescrição da tarefa.\n", encoding="utf-8")

    return {
        "board_id": board_id,
        "board": {
            "flow": "feature",
            "repo": "main",
        },
        "col_id": col_id,
        "column": {
            "name": "Doing",
            "agent": "dev",
            "gitevents": gitevents,
            "target-prompt": "Execute a tarefa",
            "change": {"advance": "done"},
        },
        "issue": {
            "id": "42",
            "body_path": str(body_path),
        },
    }


def _build_prompt(tmp_path, gitevents="create"):
    """Helper: constrói prompt com BOARDS_DIR mockado para tmp_path."""
    config = _minimal_config(tmp_path)
    task = _minimal_task(tmp_path, gitevents=gitevents)
    boards_dir = tmp_path / ".pipe" / "boards"
    with patch("src.core.agent.BOARDS_DIR", boards_dir):
        return build_prompt(config, task)


# ══════════════════════════════════════════════════════════════════════════════
# Testes de PROTECTED_PATHS — existência e completude
# ══════════════════════════════════════════════════════════════════════════════

class TestProtectedPathsConstant:
    """Verifica que PROTECTED_PATHS existe, é importável e contém os padrões
    mínimos definidos na issue.

    ESTADO: falham até a implementação da Correção 1.
    """

    def test_protected_paths_existe(self):
        assert PROTECTED_PATHS is not None, \
            "PROTECTED_PATHS deve ser definida em src/core/agent.py"

    def test_protected_paths_e_lista(self):
        assert PROTECTED_PATHS is not None, "PROTECTED_PATHS não implementada ainda"
        assert isinstance(PROTECTED_PATHS, (list, tuple, set)), \
            "PROTECTED_PATHS deve ser uma coleção (list, tuple ou set)"

    def test_protected_paths_nao_e_vazia(self):
        assert PROTECTED_PATHS is not None, "PROTECTED_PATHS não implementada ainda"
        assert len(PROTECTED_PATHS) > 0, "PROTECTED_PATHS não deve ser vazia"

    @pytest.mark.parametrize("padrao", [
        ".pipe/boards/*/snapshot.json",
        ".pipe/changeQueue.json",
        ".pipe/throttle.json",
        ".pipe/throttle-*.json",
    ])
    def test_protected_paths_contem_padroes_minimos(self, padrao):
        assert PROTECTED_PATHS is not None, "PROTECTED_PATHS não implementada ainda"
        assert padrao in PROTECTED_PATHS, \
            f"PROTECTED_PATHS deve conter o padrão obrigatório: '{padrao}'"


# ══════════════════════════════════════════════════════════════════════════════
# Testes de _assert_no_protected — guard de segurança
# ══════════════════════════════════════════════════════════════════════════════

class TestAssertNoProtected:
    """Verifica o comportamento do guard que detecta paths protegidos no prompt.

    ESTADO: falham até a implementação da Correção 1.
    """

    def test_guard_importavel(self):
        assert _assert_no_protected is not None, \
            "_assert_no_protected deve ser importável de src.core.agent"
        assert callable(_assert_no_protected)

    def test_guard_nao_levanta_para_prompt_limpo(self):
        if _assert_no_protected is None:
            pytest.skip("_assert_no_protected não implementada ainda")
        prompt = "Execute a tarefa.\n\nUse o arquivo /home/user/repo/src/main.py."
        _assert_no_protected(prompt)  # não deve levantar

    def test_guard_levanta_para_snapshot_json(self):
        if _assert_no_protected is None:
            pytest.skip("_assert_no_protected não implementada ainda")
        prompt = "Leia .pipe/boards/myboard/snapshot.json para descobrir os ids."
        with pytest.raises(ValueError, match="snapshot.json"):
            _assert_no_protected(prompt)

    def test_guard_levanta_para_changequeue_json(self):
        if _assert_no_protected is None:
            pytest.skip("_assert_no_protected não implementada ainda")
        prompt = "Arquivo: .pipe/changeQueue.json contém a fila."
        with pytest.raises(ValueError, match="changeQueue.json"):
            _assert_no_protected(prompt)

    def test_guard_levanta_para_throttle_json(self):
        if _assert_no_protected is None:
            pytest.skip("_assert_no_protected não implementada ainda")
        prompt = "Verifique .pipe/throttle.json antes de continuar."
        with pytest.raises(ValueError, match="throttle"):
            _assert_no_protected(prompt)

    def test_guard_levanta_para_throttle_variante(self):
        if _assert_no_protected is None:
            pytest.skip("_assert_no_protected não implementada ainda")
        prompt = "Config em .pipe/throttle-myboard.json."
        with pytest.raises(ValueError, match="throttle"):
            _assert_no_protected(prompt)

    def test_guard_levanta_com_path_absoluto_snapshot(self):
        if _assert_no_protected is None:
            pytest.skip("_assert_no_protected não implementada ainda")
        prompt = "Arquivo: /home/user/.pipe/boards/myboard/snapshot.json."
        with pytest.raises(ValueError):
            _assert_no_protected(prompt)

    def test_guard_nao_falso_positivo_para_nomes_similares(self):
        """Substrings como 'snap' ou 'snapshots/' não devem disparar o guard."""
        if _assert_no_protected is None:
            pytest.skip("_assert_no_protected não implementada ainda")
        prompt = "Leia snapshots/ e o arquivo snap.py — não é sensível."
        _assert_no_protected(prompt)  # não deve levantar

    def test_guard_nao_falso_positivo_para_throttle_yaml(self):
        """throttle-config.yaml não deve disparar (padrão é throttle-*.json)."""
        if _assert_no_protected is None:
            pytest.skip("_assert_no_protected não implementada ainda")
        prompt = "Ajuste throttle-config.yaml na pasta de configurações."
        _assert_no_protected(prompt)  # não deve levantar

    def test_guard_mensagem_identifica_arquivo(self):
        """A mensagem de erro deve identificar qual arquivo protegido foi encontrado."""
        if _assert_no_protected is None:
            pytest.skip("_assert_no_protected não implementada ainda")
        prompt = "Path: .pipe/boards/x/snapshot.json"
        with pytest.raises(ValueError) as exc_info:
            _assert_no_protected(prompt)
        assert "snapshot.json" in str(exc_info.value)


# ══════════════════════════════════════════════════════════════════════════════
# Testes de build_prompt — prompt real não expõe paths protegidos
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildPromptNaoExpoePaths:
    """Verifica que o prompt gerado por build_prompt não vaza paths internos.

    ESTADO: testes de ausência de strings já passam hoje (o código atual não
    menciona esses arquivos diretamente). O teste que usa _assert_no_protected
    passa após a implementação da Correção 1.
    """

    def test_prompt_nao_contem_snapshot_json(self, tmp_path):
        prompt = _build_prompt(tmp_path)
        assert "snapshot.json" not in prompt, \
            "O prompt não deve referenciar snapshot.json"

    def test_prompt_nao_contem_changequeue_json(self, tmp_path):
        prompt = _build_prompt(tmp_path)
        assert "changeQueue.json" not in prompt, \
            "O prompt não deve referenciar changeQueue.json"

    def test_prompt_nao_contem_throttle_json(self, tmp_path):
        prompt = _build_prompt(tmp_path)
        assert "throttle.json" not in prompt, \
            "O prompt não deve referenciar throttle.json"

    def test_prompt_guard_nao_levanta(self, tmp_path):
        """_assert_no_protected não deve levantar para o prompt gerado.

        ESTADO: passa após a implementação do guard na Correção 1.
        """
        if _assert_no_protected is None:
            pytest.skip("_assert_no_protected não implementada ainda")
        prompt = _build_prompt(tmp_path)
        _assert_no_protected(prompt)

    @pytest.mark.parametrize("gitevents", ["create", "use", "merge", "create-merge", "no-branch"])
    def test_prompt_limpo_para_todos_os_gitevents(self, tmp_path, gitevents):
        """Para qualquer valor de gitevents, o prompt não expõe paths protegidos."""
        prompt = _build_prompt(tmp_path, gitevents=gitevents)
        assert "snapshot.json" not in prompt
        assert "changeQueue.json" not in prompt
        assert "throttle.json" not in prompt

    def test_prompt_contem_path_da_issue_mas_nao_do_snapshot(self, tmp_path):
        """O path do body da issue DEVE aparecer; o snapshot NÃO deve."""
        prompt = _build_prompt(tmp_path)
        assert "42-my-feature-body.md" in prompt, \
            "O path do body da issue deve estar no prompt (legítimo)"
        assert "snapshot.json" not in prompt

    def test_prompt_contem_path_de_coluna_alvo_sem_expor_snapshot(self, tmp_path):
        """O path da coluna alvo (change/advance) aparece no prompt, mas o snapshot não."""
        prompt = _build_prompt(tmp_path)
        assert "done" in prompt, "A seção de transição deve conter a coluna alvo"
        assert "snapshot.json" not in prompt


# ══════════════════════════════════════════════════════════════════════════════
# Testes de regressão — build_prompt ainda funciona após a correção
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildPromptRegressao:
    """Verifica que build_prompt mantém o comportamento existente após a correção.

    ESTADO: todos devem passar agora e continuar passando após a implementação.
    """

    def test_prompt_contem_titulo_da_issue(self, tmp_path):
        prompt = _build_prompt(tmp_path)
        assert "My Feature" in prompt

    def test_prompt_contem_nome_da_etapa(self, tmp_path):
        prompt = _build_prompt(tmp_path)
        assert "Doing" in prompt

    def test_prompt_contem_target_prompt(self, tmp_path):
        prompt = _build_prompt(tmp_path)
        assert "Execute a tarefa" in prompt

    def test_prompt_contem_git_setup_para_create(self, tmp_path):
        prompt = _build_prompt(tmp_path, gitevents="create")
        assert "git checkout -b" in prompt

    def test_prompt_nao_contem_git_setup_para_no_branch(self, tmp_path):
        prompt = _build_prompt(tmp_path, gitevents="no-branch")
        assert "git checkout -b" not in prompt

    def test_prompt_contem_path_addcomment(self, tmp_path):
        prompt = _build_prompt(tmp_path)
        assert "addcomment.md" in prompt

    def test_prompt_contem_secao_transicao_coluna(self, tmp_path):
        prompt = _build_prompt(tmp_path)
        assert "Transição de coluna" in prompt

    def test_prompt_contem_nome_do_agente(self, tmp_path):
        prompt = _build_prompt(tmp_path)
        assert "engineering" in prompt

    def test_prompt_e_string_nao_vazia(self, tmp_path):
        prompt = _build_prompt(tmp_path)
        assert isinstance(prompt, str) and len(prompt) > 100

    def test_prompt_contem_secao_executar_tarefa(self, tmp_path):
        prompt = _build_prompt(tmp_path)
        assert "## Executar tarefa" in prompt

    def test_prompt_contem_secao_diretorio_de_trabalho(self, tmp_path):
        prompt = _build_prompt(tmp_path)
        assert "## Diretório de trabalho" in prompt

    def test_prompt_contem_secao_anotacoes_body(self, tmp_path):
        prompt = _build_prompt(tmp_path)
        assert "Anotações no body" in prompt

    def test_prompt_contem_commit_e_push_para_create(self, tmp_path):
        prompt = _build_prompt(tmp_path, gitevents="create")
        assert "## Commit e Push" in prompt

    def test_prompt_contem_pr_para_merge(self, tmp_path):
        prompt = _build_prompt(tmp_path, gitevents="merge")
        assert "## Pull Request" in prompt

    def test_prompt_nao_contem_pr_para_create(self, tmp_path):
        prompt = _build_prompt(tmp_path, gitevents="create")
        assert "## Pull Request" not in prompt

    def test_prompt_contem_cleanup_para_create(self, tmp_path):
        prompt = _build_prompt(tmp_path, gitevents="create")
        assert "## Cleanup" in prompt

    def test_prompt_nao_contem_commit_para_no_branch(self, tmp_path):
        prompt = _build_prompt(tmp_path, gitevents="no-branch")
        assert "## Commit e Push" not in prompt


# ══════════════════════════════════════════════════════════════════════════════
# Testes de geração de configuração do agente — tools
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentToolsConfig:
    """Verifica a geração da configuração de tools do agente (generate_native_agents).

    A issue pede avaliação de substituição de ["*"] por lista explícita.
    Estes testes documentam a interface esperada após a correção.

    ESTADO: os testes que dependem de generate_native_agents fazem skip até a
    implementação existir.
    """

    def test_generate_native_agents_importavel(self):
        """generate_native_agents (ou equivalente) deve ser importável."""
        generate_native_agents = getattr(_agent_module, "generate_native_agents", None)
        if generate_native_agents is None:
            pytest.skip("generate_native_agents não existe ainda (pré-implementação)")
        assert callable(generate_native_agents)

    def test_generate_native_agents_retorna_lista_de_dicts(self):
        """Quando existir, deve retornar lista de dicts com chave 'tools'."""
        generate_native_agents = getattr(_agent_module, "generate_native_agents", None)
        if generate_native_agents is None:
            pytest.skip("generate_native_agents não existe ainda")

        agents = generate_native_agents(
            {"kiro-cli": {"dev": {"name": "engineering", "model": "x"}}}
        )
        assert isinstance(agents, list)
        for agent in agents:
            assert "tools" in agent, "Cada agente deve ter a chave 'tools'"

    def test_generate_native_agents_tools_nao_e_wildcard_irrestrito(self):
        """Após a correção, tools não deve ser apenas ['*'] sem restrição de path.

        Este teste documenta a meta da Correção 1; falha até a implementação.
        """
        generate_native_agents = getattr(_agent_module, "generate_native_agents", None)
        if generate_native_agents is None:
            pytest.skip("generate_native_agents não existe ainda")

        agents = generate_native_agents(
            {"kiro-cli": {"dev": {"name": "engineering", "model": "x"}}}
        )
        for agent in agents:
            tools = agent.get("tools", [])
            assert tools != ["*"], \
                "Após Correção 1, tools não deve ser ['*']; use lista explícita ou restrição de path"
