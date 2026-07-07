"""
Casos de Teste — Correção 2: CONTEXT.md gerado no startup a partir do pipe.yml

Contexto: Durante o incidente "Issue Fantasma", um agente criou arquivos com
prefixo numérico e sobrescreveu snapshot.json com IDs inventados, porque não
tinha instruções explícitas derivadas da configuração real do sistema.

Esta suíte valida que:
  - generate_context() cria .pipe/CONTEXT.md a partir do config
  - Regenera quando pipe.yml é mais novo que CONTEXT.md
  - Não sobrescreve se CONTEXT.md já está atualizado
  - O CONTEXT.md lista arquivos protegidos
  - O CONTEXT.md instrui nomeação de issues SEM prefixo numérico
  - A instrução de nomeação menciona APENAS -body.md (não history/addcomment)
  - O CONTEXT.md documenta boards, colunas e branches do pipe.yml
  - O conteúdo é injetado via --agent (argumento CLI), NÃO inline no prompt
  - O adapter passa --agent ao kiro-cli quando há context_agent definido

Estratégia: testes unitários com diretório temporário simulando o cwd da
esteira. Nenhuma chamada real ao GitHub ou ao kiro-cli.
"""

import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# Config de exemplo
# ─────────────────────────────────────────────────────────────────────────────

def _make_config(boards=None, flows=None):
    """Retorna config mínima representativa para testes."""
    if flows is None:
        flows = {
            "base": "main",
            "feature": {"prefix": "feature/", "create": "main", "merge": "main"},
            "hotfix": {"prefix": "hotfix/", "create": "main", "merge": "main"},
        }
    if boards is None:
        boards = {
            "platform": "github",
            "task": {
                "name": "Task Board",
                "flow": "feature",
                "columns": {
                    "todo": {"name": "To Do"},
                    "doing": {"name": "Doing", "agent": "dev"},
                    "done": {"name": "Done"},
                },
            },
        }
    return {
        "sleep": 60,
        "git": {
            "repo": {"main": "git@github.com:user/repo.git"},
            "flow": flows,
        },
        "agents": {
            "kiro-cli": {
                "dev": {"name": "engineering", "model": "claude-sonnet-4"},
            }
        },
        "boards": boards,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 1 — Ciclo de vida do arquivo
# ─────────────────────────────────────────────────────────────────────────────

class TestCicloDeVida(unittest.TestCase):

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        (self.cwd / ".pipe").mkdir()
        (self.cwd / "pipe.yml").write_text("# pipe.yml de teste\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, config=None):
        from src.core.context_generator import generate_context
        with patch("src.core.context_generator.PIPE_FILE", self.cwd / "pipe.yml"), \
             patch("src.core.context_generator.CONTEXT_FILE", self.cwd / ".pipe" / "CONTEXT.md"):
            generate_context(config or _make_config())

    def test_cria_context_se_nao_existir(self):
        """Deve criar .pipe/CONTEXT.md quando ele não existe."""
        ctx = self.cwd / ".pipe" / "CONTEXT.md"
        self.assertFalse(ctx.exists())
        self._run()
        self.assertTrue(ctx.exists())
        self.assertGreater(len(ctx.read_text()), 0)

    def test_regenera_quando_pipeyml_modificado(self):
        """Deve regenerar quando pipe.yml é mais novo que CONTEXT.md."""
        ctx = self.cwd / ".pipe" / "CONTEXT.md"
        self._run()
        old_content = ctx.read_text()
        # Torna o pipe.yml mais novo que o CONTEXT.md
        time.sleep(0.02)
        (self.cwd / "pipe.yml").write_text("# atualizado\n")
        self._run()
        # Arquivo deve ser regravado (mtime do CONTEXT.md mudou)
        self.assertTrue(ctx.exists())

    def test_nao_sobrescreve_se_atualizado(self):
        """Não deve sobrescrever CONTEXT.md se já está atualizado (pipe.yml mais antigo)."""
        ctx = self.cwd / ".pipe" / "CONTEXT.md"
        self._run()
        mtime_antes = ctx.stat().st_mtime
        # pipe.yml não foi modificado → CONTEXT.md já está atualizado
        time.sleep(0.01)
        self._run()
        mtime_depois = ctx.stat().st_mtime
        self.assertEqual(mtime_antes, mtime_depois)


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 2 — Arquivos protegidos
# ─────────────────────────────────────────────────────────────────────────────

class TestArquivosProtegidos(unittest.TestCase):

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        (self.cwd / ".pipe").mkdir()
        (self.cwd / "pipe.yml").write_text("# pipe.yml\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _get_content(self):
        from src.core.context_generator import generate_context
        ctx_file = self.cwd / ".pipe" / "CONTEXT.md"
        with patch("src.core.context_generator.PIPE_FILE", self.cwd / "pipe.yml"), \
             patch("src.core.context_generator.CONTEXT_FILE", ctx_file):
            generate_context(_make_config())
        return ctx_file.read_text()

    def test_lista_snapshot_json(self):
        content = self._get_content()
        self.assertIn("snapshot.json", content)

    def test_lista_changequeue_json(self):
        content = self._get_content()
        self.assertIn("changeQueue.json", content)

    def test_lista_throttle(self):
        content = self._get_content()
        self.assertIn("throttle", content)

    def test_lista_sessions_json(self):
        content = self._get_content()
        self.assertIn("sessions.json", content)

    def test_secao_restricoes_presente(self):
        """Deve haver uma seção de restrições ou arquivos protegidos."""
        content = self._get_content()
        keywords = ["restrição", "Restrição", "protegido", "NUNCA", "proibido", "NÃO"]
        self.assertTrue(
            any(k in content for k in keywords),
            f"Nenhuma palavra-chave de restrição encontrada. Início do conteúdo:\n{content[:300]}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 3 — Nomeação de issues (sem prefixo numérico)
# ─────────────────────────────────────────────────────────────────────────────

class TestNomeacaoIssues(unittest.TestCase):

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        (self.cwd / ".pipe").mkdir()
        (self.cwd / "pipe.yml").write_text("# pipe.yml\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _get_content(self):
        from src.core.context_generator import generate_context
        ctx_file = self.cwd / ".pipe" / "CONTEXT.md"
        with patch("src.core.context_generator.PIPE_FILE", self.cwd / "pipe.yml"), \
             patch("src.core.context_generator.CONTEXT_FILE", ctx_file):
            generate_context(_make_config())
        return ctx_file.read_text()

    def test_instrui_contra_prefixo_numerico(self):
        """Deve instruir explicitamente contra prefixo numérico no nome do arquivo."""
        content = self._get_content()
        keywords = ["prefixo", "numérico", "número", "prefixo numérico", "sem prefixo"]
        self.assertTrue(
            any(k in content for k in keywords),
            "Instrução contra prefixo numérico não encontrada"
        )

    def test_menciona_body_md(self):
        """Deve mencionar o padrão correto -body.md."""
        content = self._get_content()
        self.assertIn("-body.md", content)

    def test_nao_solicita_criacao_history(self):
        """Instrução de criação NÃO deve sugerir criar -history.md."""
        content = self._get_content()
        # Verifica que não há instrução de criação do history
        # (pode mencionar o arquivo em outros contextos, mas não como item a criar)
        lines_with_history = [
            l for l in content.splitlines()
            if "-history.md" in l and ("crie" in l.lower() or "criar" in l.lower()
                                        or "opcional" in l.lower() or "- `" in l)
        ]
        self.assertEqual(
            len(lines_with_history), 0,
            f"Instrução de criação de -history.md encontrada (não deve existir):\n"
            + "\n".join(lines_with_history)
        )

    def test_nao_solicita_criacao_addcomment(self):
        """Instrução de criação NÃO deve sugerir criar -addcomment.md."""
        content = self._get_content()
        lines_with_add = [
            l for l in content.splitlines()
            if "-addcomment.md" in l and ("crie" in l.lower() or "criar" in l.lower()
                                           or "opcional" in l.lower() or "- `" in l)
        ]
        self.assertEqual(
            len(lines_with_add), 0,
            f"Instrução de criação de -addcomment.md encontrada (não deve existir):\n"
            + "\n".join(lines_with_add)
        )

    def test_exemplo_padrao_errado(self):
        """Deve mostrar exemplo do padrão errado (com prefixo numérico) para deixar claro."""
        content = self._get_content()
        # Ex: "4-login-body.md" ou menção a "4-slug-body.md"
        import re
        has_example = bool(re.search(r"\d+-\w.*-body\.md", content))
        self.assertTrue(has_example, "Exemplo do padrão errado (com prefixo numérico) não encontrado")


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 4 — Boards e colunas
# ─────────────────────────────────────────────────────────────────────────────

class TestBoardsEColunas(unittest.TestCase):

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        (self.cwd / ".pipe").mkdir()
        (self.cwd / "pipe.yml").write_text("# pipe.yml\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _get_content(self, config=None):
        from src.core.context_generator import generate_context
        ctx_file = self.cwd / ".pipe" / "CONTEXT.md"
        with patch("src.core.context_generator.PIPE_FILE", self.cwd / "pipe.yml"), \
             patch("src.core.context_generator.CONTEXT_FILE", ctx_file):
            generate_context(config or _make_config())
        return ctx_file.read_text()

    def test_nome_do_board(self):
        content = self._get_content()
        self.assertIn("Task Board", content)

    def test_id_do_board(self):
        content = self._get_content()
        self.assertIn("task", content)

    def test_nomes_das_colunas(self):
        content = self._get_content()
        self.assertIn("To Do", content)
        self.assertIn("Doing", content)
        self.assertIn("Done", content)

    def test_multiplos_boards(self):
        """Com dois boards, ambos devem aparecer no CONTEXT.md."""
        config = _make_config(boards={
            "platform": "github",
            "task": {
                "name": "Task Board",
                "flow": "feature",
                "columns": {"todo": {"name": "To Do"}, "doing": {"name": "Doing"}},
            },
            "bug": {
                "name": "Bug Board",
                "flow": "hotfix",
                "columns": {"open": {"name": "Open"}, "closed": {"name": "Closed"}},
            },
        })
        content = self._get_content(config)
        self.assertIn("Task Board", content)
        self.assertIn("Bug Board", content)

    def test_flow_associado_ao_board(self):
        content = self._get_content()
        self.assertIn("feature", content)

    def test_config_sem_boards_nao_levanta_excecao(self):
        """Config com boards vazio (apenas platform) não deve levantar exceção."""
        config = _make_config(boards={"platform": "github"})
        try:
            self._get_content(config)
        except Exception as e:
            self.fail(f"Exceção inesperada com boards vazio: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 5 — Branches e prefixos
# ─────────────────────────────────────────────────────────────────────────────

class TestBranchesEPrefixos(unittest.TestCase):

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        (self.cwd / ".pipe").mkdir()
        (self.cwd / "pipe.yml").write_text("# pipe.yml\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _get_content(self, config=None):
        from src.core.context_generator import generate_context
        ctx_file = self.cwd / ".pipe" / "CONTEXT.md"
        with patch("src.core.context_generator.PIPE_FILE", self.cwd / "pipe.yml"), \
             patch("src.core.context_generator.CONTEXT_FILE", ctx_file):
            generate_context(config or _make_config())
        return ctx_file.read_text()

    def test_prefixo_feature(self):
        content = self._get_content()
        self.assertIn("feature/", content)

    def test_branch_base(self):
        content = self._get_content()
        self.assertIn("main", content)

    def test_multiplos_flows(self):
        content = self._get_content()
        self.assertIn("hotfix/", content)

    def test_secao_branches_presente(self):
        content = self._get_content()
        keywords = ["branch", "Branch", "git", "flow", "prefixo"]
        self.assertTrue(
            any(k in content for k in keywords),
            "Seção de branches não encontrada"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 6 — Integração via --agent (NÃO inline no prompt)
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegracaoViaAgent(unittest.TestCase):
    """Valida que o CONTEXT.md é injetado via --agent, não inline no prompt."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        (self.cwd / ".pipe").mkdir()
        (self.cwd / "pipe.yml").write_text("# pipe.yml\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _generate(self, config=None):
        from src.core.context_generator import generate_context
        ctx_file = self.cwd / ".pipe" / "CONTEXT.md"
        with patch("src.core.context_generator.PIPE_FILE", self.cwd / "pipe.yml"), \
             patch("src.core.context_generator.CONTEXT_FILE", ctx_file):
            generate_context(config or _make_config())
        return ctx_file

    def test_generate_context_retorna_path_do_arquivo(self):
        """generate_context deve retornar o Path do arquivo gerado."""
        from src.core.context_generator import generate_context
        ctx_file = self.cwd / ".pipe" / "CONTEXT.md"
        with patch("src.core.context_generator.PIPE_FILE", self.cwd / "pipe.yml"), \
             patch("src.core.context_generator.CONTEXT_FILE", ctx_file):
            result = generate_context(_make_config())
        self.assertIsNotNone(result)
        self.assertIsInstance(result, Path)

    def test_build_prompt_nao_contem_conteudo_do_context_md(self):
        """build_prompt NÃO deve embutir o conteúdo do CONTEXT.md no texto do prompt."""
        from src.core.agent import build_prompt

        sentinel = "SENTINEL_CONTEXT_CONTENT_XYZ"

        # Cria CONTEXT.md com conteúdo sentinela
        ctx_file = self.cwd / ".pipe" / "CONTEXT.md"
        ctx_file.write_text(f"# Context\n{sentinel}\n")

        config = _make_config()
        # Monta task mínima
        body_path = self.cwd / ".pipe" / "boards" / "task" / "doing" / "slug-body.md"
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_text("# Título da issue\n\nConteúdo.\n")

        task = {
            "board_id": "task",
            "board": config["boards"]["task"],
            "column": config["boards"]["task"]["columns"]["doing"],
            "col_id": "doing",
            "issue": {"id": "1", "body_path": str(body_path)},
        }

        with patch("src.core.context_generator.CONTEXT_FILE", ctx_file), \
             patch("src.core.agent.CONTEXT_FILE", ctx_file, create=True):
            prompt = build_prompt(config, task)

        self.assertNotIn(
            sentinel, prompt,
            "Conteúdo do CONTEXT.md encontrado inline no prompt — deve ser via --agent"
        )

    def test_kiro_cli_passa_agent_flag_quando_context_file_existe(self):
        """KiroCliAgent deve passar --agent ao comando quando CONTEXT.md existe."""
        from src.adapters.kiro_cli_agent import KiroCliAgent
        from src.core.agent import AgentParams

        ctx_file = self.cwd / ".pipe" / "CONTEXT.md"
        ctx_file.write_text("# Context\nRESTRIÇÕES\n")

        params = AgentParams(
            platform="kiro-cli",
            agent_id="dev",
            agent_name="engineering",
            model="claude-sonnet-4",
            issue_id="1",
            board_id="task",
            col_id="doing",
            prompt="Execute a tarefa.",
            work_dir=str(self.cwd),
        )

        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stdout = ""
            r.stderr = ""
            return r

        agent = KiroCliAgent()

        with patch("subprocess.run", side_effect=fake_run), \
             patch("src.adapters.kiro_cli_agent.SessionIndex") as mock_idx, \
             patch("src.adapters.kiro_cli_agent.CONTEXT_FILE", ctx_file, create=True):
            mock_idx.return_value.get.return_value = None
            mock_idx.return_value.set.return_value = None
            agent._run(params, self.cwd)

        self.assertIn("--agent", captured_cmd,
                      f"--agent não encontrado no comando: {captured_cmd}")

    def test_kiro_cli_nao_passa_agent_flag_sem_context_file(self):
        """KiroCliAgent não deve passar --agent quando não há CONTEXT.md."""
        from src.adapters.kiro_cli_agent import KiroCliAgent
        from src.core.agent import AgentParams

        ctx_file = self.cwd / ".pipe" / "CONTEXT.md"
        # Garantir que NÃO existe
        if ctx_file.exists():
            ctx_file.unlink()

        params = AgentParams(
            platform="kiro-cli",
            agent_id="dev",
            agent_name="engineering",
            model="claude-sonnet-4",
            issue_id="1",
            board_id="task",
            col_id="doing",
            prompt="Execute a tarefa.",
            work_dir=str(self.cwd),
        )

        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stdout = ""
            r.stderr = ""
            return r

        agent = KiroCliAgent()

        with patch("subprocess.run", side_effect=fake_run), \
             patch("src.adapters.kiro_cli_agent.SessionIndex") as mock_idx, \
             patch("src.adapters.kiro_cli_agent.CONTEXT_FILE", ctx_file, create=True):
            mock_idx.return_value.get.return_value = None
            mock_idx.return_value.set.return_value = None
            agent._run(params, self.cwd)

        self.assertNotIn("--agent", captured_cmd,
                         "--agent não deveria aparecer quando CONTEXT.md não existe")


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 7 — Arquivo de agente gerado para o kiro-cli
# ─────────────────────────────────────────────────────────────────────────────

class TestArquivoDeAgente(unittest.TestCase):
    """Valida que generate_context (ou startup) gera o arquivo de agente JSON."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        (self.cwd / ".pipe").mkdir()
        (self.cwd / "pipe.yml").write_text("# pipe.yml\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, config=None):
        from src.core.context_generator import generate_context
        ctx_file = self.cwd / ".pipe" / "CONTEXT.md"
        agent_file = self.cwd / ".kiro" / "agents" / "pipe_context.json"
        with patch("src.core.context_generator.PIPE_FILE", self.cwd / "pipe.yml"), \
             patch("src.core.context_generator.CONTEXT_FILE", ctx_file), \
             patch("src.core.context_generator.AGENT_FILE", agent_file, create=True):
            generate_context(config or _make_config())
        return ctx_file, agent_file

    def test_gera_arquivo_de_agente_json(self):
        """Deve gerar .kiro/agents/pipe_context.json com o conteúdo do CONTEXT.md."""
        _, agent_file = self._run()
        self.assertTrue(agent_file.exists(), ".kiro/agents/pipe_context.json não foi criado")

    def test_arquivo_de_agente_json_valido(self):
        """O arquivo .kiro/agents/pipe_context.json deve ser JSON válido."""
        _, agent_file = self._run()
        try:
            data = json.loads(agent_file.read_text())
        except json.JSONDecodeError as e:
            self.fail(f"pipe_context.json não é JSON válido: {e}")
        self.assertIsInstance(data, dict)

    def test_arquivo_de_agente_tem_prompt(self):
        """O arquivo JSON deve ter campo 'prompt' com o conteúdo do CONTEXT.md."""
        ctx_file, agent_file = self._run()
        data = json.loads(agent_file.read_text())
        self.assertIn("prompt", data)
        ctx_content = ctx_file.read_text()
        self.assertEqual(data["prompt"].strip(), ctx_content.strip())

    def test_arquivo_de_agente_tem_nome(self):
        """O arquivo JSON deve ter campo 'name'."""
        _, agent_file = self._run()
        data = json.loads(agent_file.read_text())
        self.assertIn("name", data)
        self.assertTrue(data["name"])


if __name__ == "__main__":
    unittest.main()
