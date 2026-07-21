"""Testes para o log de execução descritivo do agente (etapa + título).

Issue #31 — Tornar log de execução de agente descritivo (etapa + título)

Cobertura:
  (a) AgentParams aceita os novos campos opcionais `col_name` e `title`.
  (b) Formatação da linha de log com os novos campos preenchidos.
  (c) Comportamento com campos vazios (fallback: campos ausentes não quebram).
  (d) `model` e `cwd` não aparecem mais na linha de log do terminal.
  (e) `call_agent` popula `col_name` e `title` corretamente em AgentParams.
"""

import sys
from pathlib import Path
from dataclasses import fields
from unittest.mock import MagicMock, patch, call
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.agent import AgentParams


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_params(**overrides) -> AgentParams:
    """Cria AgentParams minimal válido com campos opcionais defaults."""
    defaults = dict(
        platform="kiro-cli",
        agent_id="engineering",
        agent_name="Sofia Carvalho - Engenheira de Software PL",
        model="claude-sonnet-4.6",
        issue_id="25",
        board_id="task",
        col_id="analise-tecnica",
        prompt="Execute a tarefa.",
        work_dir="/home/user/repo/main",
    )
    defaults.update(overrides)
    return AgentParams(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# (a) AgentParams: novos campos opcionais
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentParamsCamposOpcionais:
    """AgentParams deve aceitar col_name e title como campos opcionais."""

    def test_col_name_tem_default_vazio(self):
        """`col_name` deve ter valor padrão '' quando não fornecido."""
        params = _make_params()
        assert params.col_name == ""

    def test_title_tem_default_vazio(self):
        """`title` deve ter valor padrão '' quando não fornecido."""
        params = _make_params()
        assert params.title == ""

    def test_col_name_pode_ser_preenchido(self):
        """`col_name` deve aceitar valor fornecido."""
        params = _make_params(col_name="Análise Técnica")
        assert params.col_name == "Análise Técnica"

    def test_title_pode_ser_preenchido(self):
        """`title` deve aceitar valor fornecido."""
        params = _make_params(title="Log não descritivo")
        assert params.title == "Log não descritivo"

    def test_ambos_preenchidos(self):
        """Ambos os campos preenchidos simultaneamente."""
        params = _make_params(col_name="Análise Técnica", title="Log não descritivo")
        assert params.col_name == "Análise Técnica"
        assert params.title == "Log não descritivo"

    def test_campos_existem_em_agentparams(self):
        """Os campos `col_name` e `title` devem existir na dataclass AgentParams."""
        field_names = {f.name for f in fields(AgentParams)}
        assert "col_name" in field_names, "AgentParams deve ter o campo `col_name`"
        assert "title" in field_names, "AgentParams deve ter o campo `title`"

    def test_codigo_existente_sem_novos_campos_nao_quebra(self):
        """Código existente que não passa col_name/title continua funcionando."""
        # Simula construção antiga de AgentParams (sem os novos campos)
        params = AgentParams(
            platform="kiro-cli",
            agent_id="engineering",
            agent_name="Sofia",
            model="claude-sonnet-4.6",
            issue_id="1",
            board_id="task",
            col_id="doing",
            prompt="prompt",
            work_dir="/repo",
        )
        # Não deve lançar TypeError ou AttributeError
        assert params.col_name == ""
        assert params.title == ""


# ─────────────────────────────────────────────────────────────────────────────
# (b) Formatação da linha de log com novos campos
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatoLogDescritivo:
    """A linha de log de terminal deve incluir título e col_name."""

    def _capture_log_info(self, params: AgentParams) -> str:
        """Executa KiroCliAgent.execute mockando tudo exceto o log.info."""
        from src.adapters.kiro_cli_agent import KiroCliAgent

        captured = []

        def fake_log_info(tag, msg, **kwargs):
            if tag == "Agent" and "agent=" in msg:
                captured.append(msg)

        with TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            params = AgentParams(
                platform=params.platform,
                agent_id=params.agent_id,
                agent_name=params.agent_name,
                model=params.model,
                issue_id=params.issue_id,
                board_id=params.board_id,
                col_id=params.col_id,
                prompt=params.prompt,
                work_dir=str(work_dir),
                col_name=params.col_name,
                title=params.title,
            )

            agent = KiroCliAgent()
            with patch("src.adapters.kiro_cli_agent.log") as mock_log, \
                 patch.object(agent, "_run", return_value="output ok"), \
                 patch.object(agent, "_append_log"), \
                 patch.object(agent, "_create_log", return_value=Path(tmp) / "log.md"):
                mock_log.info.side_effect = fake_log_info
                agent.execute(params)

        return captured[0] if captured else ""

    def test_log_contem_titulo(self):
        """Linha de log deve conter o título da issue entre aspas."""
        params = _make_params(
            title="Log não descritivo",
            col_name="Análise Técnica",
        )
        msg = self._capture_log_info(params)
        assert '"Log não descritivo"' in msg, f"Título não encontrado no log: {msg}"

    def test_log_contem_col_name_apos_arroba(self):
        """Linha de log deve conter o nome da coluna no formato '@ <col_name>'."""
        params = _make_params(
            title="Log não descritivo",
            col_name="Análise Técnica",
        )
        msg = self._capture_log_info(params)
        assert "@ Análise Técnica" in msg, f"col_name não encontrado no log: {msg}"

    def test_log_contem_board_e_issue(self):
        """Linha de log deve conter [board_id] e #issue_id."""
        params = _make_params(
            title="Minha tarefa",
            col_name="Desenvolvimento",
            board_id="task",
            issue_id="25",
        )
        msg = self._capture_log_info(params)
        assert "[task]" in msg, f"board_id não encontrado: {msg}"
        assert "#25" in msg, f"issue_id não encontrado: {msg}"

    def test_log_contem_agent_name(self):
        """Linha de log deve conter o nome do agente."""
        params = _make_params(
            title="Tarefa X",
            col_name="Etapa Y",
            agent_name="Sofia Carvalho - Engenheira de Software PL",
        )
        msg = self._capture_log_info(params)
        assert "Sofia Carvalho - Engenheira de Software PL" in msg, \
            f"agent_name não encontrado: {msg}"

    def test_log_contem_log_path(self):
        """Linha de log deve conter o caminho do arquivo de log."""
        params = _make_params(title="Tarefa", col_name="Etapa")
        msg = self._capture_log_info(params)
        assert "log=" in msg, f"log= não encontrado: {msg}"

    def test_log_nao_contem_model(self):
        """Linha de log do terminal NÃO deve exibir o model."""
        params = _make_params(
            title="Tarefa",
            col_name="Etapa",
            model="claude-sonnet-4.6",
        )
        msg = self._capture_log_info(params)
        assert "model=" not in msg, \
            f"model= não deve aparecer no log do terminal: {msg}"

    def test_log_nao_contem_cwd(self):
        """Linha de log do terminal NÃO deve exibir o cwd."""
        params = _make_params(
            title="Tarefa",
            col_name="Etapa",
        )
        msg = self._capture_log_info(params)
        assert "cwd=" not in msg, \
            f"cwd= não deve aparecer no log do terminal: {msg}"

    def test_formato_completo(self):
        """Valida o formato completo esperado da linha de log.

        Formato esperado:
          [task] #25 "Log não descritivo" @ Análise Técnica agent='...' log='...'
        """
        params = _make_params(
            title="Log não descritivo",
            col_name="Análise Técnica",
            board_id="task",
            issue_id="25",
            agent_name="Sofia Carvalho - Engenheira de Software PL",
        )
        msg = self._capture_log_info(params)
        # Verifica ordem dos elementos principais
        assert msg.index("[task]") < msg.index("#25") < msg.index('"Log não descritivo"') \
               < msg.index("@ Análise Técnica") < msg.index("agent="), \
            f"Formato da linha de log fora da ordem esperada: {msg}"


# ─────────────────────────────────────────────────────────────────────────────
# (c) Fallback com campos vazios
# ─────────────────────────────────────────────────────────────────────────────

class TestLogFallbackCamposVazios:
    """Quando col_name e title estão vazios, o log não deve quebrar."""

    def _capture_log_info(self, params: AgentParams) -> str:
        from src.adapters.kiro_cli_agent import KiroCliAgent

        captured = []

        def fake_log_info(tag, msg, **kwargs):
            if tag == "Agent" and "agent=" in msg:
                captured.append(msg)

        with TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            p = AgentParams(
                platform=params.platform,
                agent_id=params.agent_id,
                agent_name=params.agent_name,
                model=params.model,
                issue_id=params.issue_id,
                board_id=params.board_id,
                col_id=params.col_id,
                prompt=params.prompt,
                work_dir=str(work_dir),
                col_name=params.col_name,
                title=params.title,
            )
            agent = KiroCliAgent()
            with patch("src.adapters.kiro_cli_agent.log") as mock_log, \
                 patch.object(agent, "_run", return_value="ok"), \
                 patch.object(agent, "_append_log"), \
                 patch.object(agent, "_create_log", return_value=Path(tmp) / "log.md"):
                mock_log.info.side_effect = fake_log_info
                agent.execute(p)

        return captured[0] if captured else ""

    def test_campos_vazios_nao_lancam_excecao(self):
        """execute() com title='' e col_name='' não deve lançar exceção."""
        from src.adapters.kiro_cli_agent import KiroCliAgent

        params = _make_params(title="", col_name="")
        with TemporaryDirectory() as tmp:
            p = AgentParams(
                platform=params.platform,
                agent_id=params.agent_id,
                agent_name=params.agent_name,
                model=params.model,
                issue_id=params.issue_id,
                board_id=params.board_id,
                col_id=params.col_id,
                prompt=params.prompt,
                work_dir=str(tmp),
            )
            agent = KiroCliAgent()
            with patch("src.adapters.kiro_cli_agent.log") as mock_log, \
                 patch.object(agent, "_run", return_value="ok"), \
                 patch.object(agent, "_append_log"), \
                 patch.object(agent, "_create_log", return_value=Path(tmp) / "log.md"):
                # Não deve lançar
                agent.execute(p)

    def test_title_vazio_ainda_loga_board_e_issue(self):
        """Mesmo com title vazio, log deve conter board e issue."""
        params = _make_params(title="", col_name="")
        msg = self._capture_log_info(params)
        assert "[task]" in msg
        assert "#25" in msg

    def test_title_vazio_aspas_presentes_ou_ausentes_sem_erro(self):
        """Com title vazio, execução completa sem erros independente do formato."""
        params = _make_params(title="", col_name="Desenvolvimento")
        # Apenas valida que não lança exceção e retorna alguma mensagem
        msg = self._capture_log_info(params)
        assert isinstance(msg, str)

    def test_apenas_col_name_vazio(self):
        """Apenas col_name vazio: título aparece normalmente."""
        params = _make_params(title="Minha tarefa", col_name="")
        msg = self._capture_log_info(params)
        assert "Minha tarefa" in msg

    def test_apenas_title_vazio(self):
        """Apenas title vazio: col_name aparece normalmente."""
        params = _make_params(title="", col_name="Desenvolvimento")
        msg = self._capture_log_info(params)
        assert "Desenvolvimento" in msg


# ─────────────────────────────────────────────────────────────────────────────
# (d) model e cwd removidos do log do terminal
# ─────────────────────────────────────────────────────────────────────────────

class TestModelECwdRemovidosDoTerminal:
    """model e cwd devem continuar no log Markdown mas não no terminal."""

    def _capture_all_log_info_calls(self, params: AgentParams) -> list[str]:
        """Retorna todas as mensagens de log.info com tag 'Agent'."""
        from src.adapters.kiro_cli_agent import KiroCliAgent

        captured = []

        def fake_log_info(tag, msg, **kwargs):
            if tag == "Agent":
                captured.append(msg)

        with TemporaryDirectory() as tmp:
            p = AgentParams(
                platform=params.platform,
                agent_id=params.agent_id,
                agent_name=params.agent_name,
                model=params.model,
                issue_id=params.issue_id,
                board_id=params.board_id,
                col_id=params.col_id,
                prompt=params.prompt,
                work_dir=str(tmp),
                col_name=params.col_name,
                title=params.title,
            )
            agent = KiroCliAgent()
            with patch("src.adapters.kiro_cli_agent.log") as mock_log, \
                 patch.object(agent, "_run", return_value="ok"), \
                 patch.object(agent, "_append_log"), \
                 patch.object(agent, "_create_log", return_value=Path(tmp) / "log.md"):
                mock_log.info.side_effect = fake_log_info
                agent.execute(p)

        return captured

    def test_model_nao_aparece_em_nenhuma_linha_de_log_inicial(self):
        """model não deve aparecer no log inicial do terminal (linha de início)."""
        params = _make_params(
            title="Tarefa",
            col_name="Etapa",
            model="claude-sonnet-4.6",
        )
        msgs = self._capture_all_log_info_calls(params)
        # A primeira mensagem (início da execução) não deve ter model=
        inicio = [m for m in msgs if "agent=" in m]
        assert inicio, "Deve existir ao menos uma linha de log com agent="
        assert "model=" not in inicio[0], \
            f"model= não deve aparecer na linha inicial: {inicio[0]}"

    def test_cwd_nao_aparece_na_linha_inicial(self):
        """cwd não deve aparecer no log inicial do terminal."""
        params = _make_params(
            title="Tarefa",
            col_name="Etapa",
        )
        msgs = self._capture_all_log_info_calls(params)
        inicio = [m for m in msgs if "agent=" in m]
        assert inicio
        assert "cwd=" not in inicio[0], \
            f"cwd= não deve aparecer na linha inicial: {inicio[0]}"

    def test_model_permanece_no_log_markdown(self):
        """model deve continuar sendo registrado no arquivo Markdown de execução."""
        from src.adapters.kiro_cli_agent import KiroCliAgent

        params = _make_params(
            title="Tarefa",
            col_name="Etapa",
            model="claude-sonnet-4.6",
        )
        agent = KiroCliAgent()
        content = agent._build_log(params)
        assert "claude-sonnet-4.6" in content, \
            "model deve permanecer no log Markdown (seção Parâmetros)"

    def test_work_dir_permanece_no_log_markdown(self):
        """work_dir deve continuar sendo registrado no arquivo Markdown de execução."""
        from src.adapters.kiro_cli_agent import KiroCliAgent

        params = _make_params(
            title="Tarefa",
            col_name="Etapa",
            work_dir="/home/user/repo/main",
        )
        agent = KiroCliAgent()
        content = agent._build_log(params)
        assert "/home/user/repo/main" in content, \
            "work_dir deve permanecer no log Markdown (seção Parâmetros)"


# ─────────────────────────────────────────────────────────────────────────────
# (e) call_agent popula col_name e title corretamente
# ─────────────────────────────────────────────────────────────────────────────

class TestCallAgentPopulaNovosCampos:
    """call_agent deve popular col_name e title em AgentParams."""

    def _run_call_agent(self, body_content: str, col_name: str) -> AgentParams:
        """
        Executa call_agent com uma task simulada e captura o AgentParams
        passado ao adapter.execute.
        """
        import src.__main__ as main_module
        from src.core.board import Board
        from src.adapters.github_board import GitHubBoardAdapter

        captured_params = []

        config = {
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
            "boards": {
                "platform": "github",
                "task": {
                    "flow": "feature",
                    "columns": {
                        "doing": {
                            "name": col_name,
                            "agent": "dev",
                            "gitevents": "no-branch",
                            "change": {"advance": "done"},
                        },
                    },
                },
            },
            "agents": {
                "kiro-cli": {
                    "dev": {
                        "name": "Sofia Carvalho - Engenheira de Software PL",
                        "model": "claude-sonnet-4.6",
                    },
                },
            },
        }

        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            body_path = tmp_path / "25-slug-body.md"
            body_path.write_text(body_content, encoding="utf-8")

            issue = {
                "id": "25",
                "column": "doing",
                "status": "ok",
                "labels": [],
                "body_path": str(body_path),
            }

            task = {
                "board_id": "task",
                "issue": issue,
                "column": config["boards"]["task"]["columns"]["doing"],
                "col_id": "doing",
                "board": config["boards"]["task"],
            }

            def fake_execute(params: AgentParams) -> None:
                captured_params.append(params)

            mock_adapter = MagicMock()
            mock_adapter.execute.side_effect = fake_execute

            with patch("src.__main__.KiroCliAgent", return_value=mock_adapter), \
                 patch("src.adapters.kiro_cli_agent.KiroCliAgent", return_value=mock_adapter), \
                 patch("src.core.agent_guard.AgentGuard.__enter__", return_value=MagicMock()), \
                 patch("src.core.agent_guard.AgentGuard.__exit__", return_value=False), \
                 patch("src.__main__.resolve_work_dir", return_value=tmp_path):
                main_module.call_agent(config, task)

        return captured_params[0] if captured_params else None

    def test_col_name_preenchido_com_nome_da_coluna(self):
        """AgentParams.col_name deve ser preenchido com task['column']['name']."""
        params = self._run_call_agent(
            body_content="# Título da issue\nConteúdo da issue.",
            col_name="Análise Técnica",
        )
        assert params is not None, "call_agent não chamou adapter.execute"
        assert params.col_name == "Análise Técnica", \
            f"col_name esperado 'Análise Técnica', obtido: '{params.col_name}'"

    def test_title_preenchido_com_primeira_linha_do_body(self):
        """AgentParams.title deve ser a primeira linha não-vazia do body (sem '# ')."""
        params = self._run_call_agent(
            body_content="# Log não descritivo\nDescricão da tarefa.",
            col_name="Análise Técnica",
        )
        assert params is not None, "call_agent não chamou adapter.execute"
        assert params.title == "Log não descritivo", \
            f"title esperado 'Log não descritivo', obtido: '{params.title}'"

    def test_title_sem_prefixo_markdown(self):
        """O título não deve conter o prefixo '# ' do markdown."""
        params = self._run_call_agent(
            body_content="# Minha tarefa importante\nDetalhes.",
            col_name="Desenvolvimento",
        )
        assert params is not None
        assert not params.title.startswith("#"), \
            f"Título não deve ter '# ': '{params.title}'"
        assert params.title == "Minha tarefa importante"

    def test_title_body_sem_prefixo_hash(self):
        """Body sem '# ' no título ainda extrai a primeira linha."""
        params = self._run_call_agent(
            body_content="Título sem hash\nConteúdo.",
            col_name="Etapa",
        )
        assert params is not None
        assert params.title == "Título sem hash"
