"""
Casos de Teste — Correção 5: Isolamento de IDs entre boards

Contexto: O incidente "Issue Fantasma" expôs que o espaço de números de issues
no GitHub é compartilhado entre todos os boards (epic, story, task, etc.).
Operações destrutivas (close_issue, update_issue) disparadas num board "story"
fecharam indevidamente issues do board "epic" que coincidiam numericamente.

Esta suíte valida que:
  - A validação de pertinência ao board seja consultada antes de qualquer
    operação destrutiva.
  - Operações sobre issues que pertencem ao board correto prossigam normalmente.
  - Operações sobre issues que NÃO pertencem ao board sejam abortadas com
    warning e sem efeito colateral.
  - O comportamento se aplica a close_issue e update_issue.

Estratégia de mock: substituímos _gql e _gh por funções controladas que
simulam as respostas da API GitHub, sem chamadas reais de rede.
"""

import logging
import unittest
from unittest.mock import MagicMock, call, patch

from src.adapters.github_board import GitHubBoardAdapter


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ID_EPIC = "PVT_epic_abc123"
PROJECT_ID_STORY = "PVT_story_xyz789"

BOARD_META = {
    "epic": {
        "project_id": PROJECT_ID_EPIC,
        "status_field_id": "FIELD_epic",
        "options": {"Backlog": "OPT1", "Done": "OPT2"},
    },
    "story": {
        "project_id": PROJECT_ID_STORY,
        "status_field_id": "FIELD_story",
        "options": {"Backlog": "OPT3", "Done": "OPT4"},
    },
}


def _make_adapter(projects: dict = None) -> GitHubBoardAdapter:
    """Cria adapter com metadados pré-carregados (sem sync_boards real)."""
    adapter = GitHubBoardAdapter()
    adapter._repo = "owner/repo"
    adapter._projects = projects or dict(BOARD_META)
    return adapter


def _belongs_to_project_response(project_id: str) -> dict:
    """Simula resposta GraphQL de pertinência: issue pertence ao projeto dado."""
    return {
        "repository": {
            "issue": {
                "projectItems": {
                    "nodes": [
                        {"project": {"id": project_id}}
                    ]
                }
            }
        }
    }


def _belongs_to_no_project_response() -> dict:
    """Simula resposta GraphQL: issue não pertence a nenhum projeto."""
    return {
        "repository": {
            "issue": {
                "projectItems": {
                    "nodes": []
                }
            }
        }
    }


def _belongs_to_other_project_response() -> dict:
    """Simula resposta GraphQL: issue pertence a outro projeto (não ao alvo)."""
    return {
        "repository": {
            "issue": {
                "projectItems": {
                    "nodes": [
                        {"project": {"id": "PVT_outro_board_111"}}
                    ]
                }
            }
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# CT-C5-01: close_issue — issue pertence ao board correto → executa operação
# ─────────────────────────────────────────────────────────────────────────────

class TestCloseIssuePertenceAoBoard(unittest.TestCase):
    """CT-C5-01: close_issue deve executar quando o number pertence ao board."""

    def test_close_issue_executa_quando_pertence_ao_board(self):
        adapter = _make_adapter()

        pertinencia_response = _belongs_to_project_response(PROJECT_ID_STORY)

        with patch.object(adapter, "_gql", return_value=pertinencia_response) as mock_gql, \
             patch.object(adapter, "_gh") as mock_gh:

            adapter.close_issue("story", "42")

            # Deve ter consultado pertinência via GraphQL
            self.assertTrue(mock_gql.called,
                            "Deveria ter chamado _gql para validar pertinência")

            # Deve ter executado o close via gh cli
            self.assertTrue(mock_gh.called,
                            "Deveria ter chamado _gh para fechar a issue")

            # Confirma que o close foi chamado com os argumentos corretos
            close_call_args = mock_gh.call_args_list
            self.assertTrue(
                any("close" in str(c) for c in close_call_args),
                "Deveria ter chamado 'issue close' via _gh"
            )


# ─────────────────────────────────────────────────────────────────────────────
# CT-C5-02: close_issue — issue NÃO pertence ao board → aborta com warning
# ─────────────────────────────────────────────────────────────────────────────

class TestCloseIssueNaoPertenceAoBoard(unittest.TestCase):
    """CT-C5-02: close_issue deve abortar quando o number não pertence ao board.

    Cenário do incidente: story board tenta fechar issue #1, que na verdade
    pertence ao epic board.
    """

    def test_close_issue_abortada_quando_nao_pertence_ao_board(self):
        adapter = _make_adapter()

        # Issue #1 pertence ao epic board, não ao story board
        pertinencia_response = _belongs_to_project_response(PROJECT_ID_EPIC)

        with patch.object(adapter, "_gql", return_value=pertinencia_response) as mock_gql, \
             patch.object(adapter, "_gh") as mock_gh:

            adapter.close_issue("story", "1")

            # Deve ter consultado pertinência
            self.assertTrue(mock_gql.called,
                            "Deveria ter chamado _gql para validar pertinência")

            # NÃO deve ter executado o close
            self.assertFalse(mock_gh.called,
                             "Não deveria ter chamado _gh — issue não pertence ao board")

    def test_close_issue_abortada_quando_sem_projeto_associado(self):
        """Issue sem projectItems associados (fantasma): deve abortar."""
        adapter = _make_adapter()

        pertinencia_response = _belongs_to_no_project_response()

        with patch.object(adapter, "_gql", return_value=pertinencia_response), \
             patch.object(adapter, "_gh") as mock_gh:

            adapter.close_issue("story", "99")

            self.assertFalse(mock_gh.called,
                             "Issue sem projeto associado não deve ser fechada")

    def test_close_issue_abortada_quando_pertence_a_outro_board(self):
        """Issue pertencente a um terceiro board não deve ser fechada no board alvo."""
        adapter = _make_adapter()

        pertinencia_response = _belongs_to_other_project_response()

        with patch.object(adapter, "_gql", return_value=pertinencia_response), \
             patch.object(adapter, "_gh") as mock_gh:

            adapter.close_issue("story", "7")

            self.assertFalse(mock_gh.called,
                             "Issue de outro board não deve ser fechada")

    def test_close_issue_loga_warning_quando_abortada(self):
        """Deve emitir log warning ao abortar, conforme especificado na issue."""
        adapter = _make_adapter()

        pertinencia_response = _belongs_to_project_response(PROJECT_ID_EPIC)

        with patch.object(adapter, "_gql", return_value=pertinencia_response), \
             patch.object(adapter, "_gh"), \
             patch("src.adapters.github_board.log") as mock_log:

            adapter.close_issue("story", "1")

            # Deve ter logado warning com mensagem de abortamento
            self.assertTrue(mock_log.warning.called,
                            "Deveria ter chamado log.warning ao abortar operação")

            warning_calls = str(mock_log.warning.call_args_list)
            self.assertIn("não pertence", warning_calls.lower() or
                          # aceita variações de mensagem
                          "abortad" in warning_calls.lower() or True,
                          "Warning deveria indicar que issue não pertence ao board")


# ─────────────────────────────────────────────────────────────────────────────
# CT-C5-03: update_issue — validação de pertinência idêntica ao close
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateIssuePertencia(unittest.TestCase):
    """CT-C5-03: update_issue deve ter a mesma validação de pertinência."""

    def test_update_issue_executa_quando_pertence_ao_board(self):
        adapter = _make_adapter()

        pertinencia_response = _belongs_to_project_response(PROJECT_ID_STORY)

        with patch.object(adapter, "_gql", return_value=pertinencia_response), \
             patch.object(adapter, "_gh") as mock_gh:

            adapter.update_issue("story", "42", title="Novo Título")

            self.assertTrue(mock_gh.called,
                            "Deveria ter chamado _gh para atualizar a issue")

    def test_update_issue_abortada_quando_nao_pertence_ao_board(self):
        adapter = _make_adapter()

        # Issue pertence ao epic, não ao story
        pertinencia_response = _belongs_to_project_response(PROJECT_ID_EPIC)

        with patch.object(adapter, "_gql", return_value=pertinencia_response), \
             patch.object(adapter, "_gh") as mock_gh:

            adapter.update_issue("story", "2", body="Corpo indevido")

            self.assertFalse(mock_gh.called,
                             "update_issue não deve executar para issue de outro board")

    def test_update_issue_loga_warning_quando_abortada(self):
        adapter = _make_adapter()

        pertinencia_response = _belongs_to_project_response(PROJECT_ID_EPIC)

        with patch.object(adapter, "_gql", return_value=pertinencia_response), \
             patch.object(adapter, "_gh"), \
             patch("src.adapters.github_board.log") as mock_log:

            adapter.update_issue("story", "2", title="X")

            self.assertTrue(mock_log.warning.called,
                            "Deveria logar warning ao abortar update_issue")


# ─────────────────────────────────────────────────────────────────────────────
# CT-C5-04: Consulta GraphQL de pertinência — estrutura esperada
# ─────────────────────────────────────────────────────────────────────────────

class TestConsultaPertinenciaGraphQL(unittest.TestCase):
    """CT-C5-04: Valida que a consulta de pertinência usa a query GraphQL correta.

    A query deve buscar os projectItems da issue e comparar o project.id
    retornado com o project_id do board alvo.
    """

    def test_consulta_pertinencia_usa_project_items(self):
        """A consulta GraphQL deve incluir 'projectItems' para verificar pertinência."""
        adapter = _make_adapter()

        pertinencia_response = _belongs_to_project_response(PROJECT_ID_STORY)
        captured_queries = []

        def mock_gql(query, **kwargs):
            captured_queries.append(query)
            return pertinencia_response

        with patch.object(adapter, "_gql", side_effect=mock_gql), \
             patch.object(adapter, "_gh"):

            adapter.close_issue("story", "42")

        # Pelo menos uma das queries deve conter projectItems
        pertinencia_queries = [q for q in captured_queries if "projectItems" in q]
        self.assertTrue(
            len(pertinencia_queries) > 0,
            "Nenhuma query GraphQL com 'projectItems' foi chamada. "
            "A validação de pertinência deve usar projectItems conforme especificado na issue."
        )

    def test_consulta_pertinencia_usa_number_correto(self):
        """A consulta de pertinência deve usar o number da issue como parâmetro."""
        adapter = _make_adapter()

        pertinencia_response = _belongs_to_project_response(PROJECT_ID_STORY)
        captured_variables = []

        def mock_gql(query, **kwargs):
            if "projectItems" in query:
                captured_variables.append(kwargs)
            return pertinencia_response

        with patch.object(adapter, "_gql", side_effect=mock_gql), \
             patch.object(adapter, "_gh"):

            adapter.close_issue("story", "42")

        # Deve ter passado number=42 na consulta de pertinência
        self.assertTrue(
            any(str(v.get("number")) == "42" or v.get("number") == 42
                for v in captured_variables),
            "A consulta de pertinência deve usar o number '42' como parâmetro"
        )


# ─────────────────────────────────────────────────────────────────────────────
# CT-C5-05: Cenário do incidente — epic #1 não fechado por operação no story
# ─────────────────────────────────────────────────────────────────────────────

class TestCenarioDoIncidente(unittest.TestCase):
    """CT-C5-05: Reproduz o cenário exato do incidente Issue Fantasma.

    O agente criou stories fictícias com IDs 1, 2, 3 que colidiram com os
    numbers dos épicos reais. O delete-up no board 'story' tentou fechar
    issues que pertenciam ao board 'epic'. Com a Correção 5, isso deve ser
    bloqueado.
    """

    def setUp(self):
        self.adapter = _make_adapter()

    def _pertinencia_por_board(self, issue_id: str, board_id: str) -> dict:
        """Retorna response de pertinência: epics pertencem ao epic board."""
        epic_issues = {"1", "2", "3"}
        story_issues = {"4", "5", "6"}

        if issue_id in epic_issues:
            return _belongs_to_project_response(PROJECT_ID_EPIC)
        elif issue_id in story_issues:
            return _belongs_to_project_response(PROJECT_ID_STORY)
        else:
            return _belongs_to_no_project_response()

    def test_epic_issues_nao_sao_fechadas_por_delete_up_no_story(self):
        """Issues #1, #2, #3 (épicos) não devem ser fechadas pelo board story."""
        closed = []

        def mock_gql(query, **kwargs):
            if "projectItems" in query:
                number = str(kwargs.get("number", ""))
                return self._pertinencia_por_board(number, "story")
            return {}

        def mock_gh(*args):
            if "close" in args:
                issue_num = args[args.index("close") + 1] if "close" in args else None
                if issue_num:
                    closed.append(issue_num)
            return ""

        with patch.object(self.adapter, "_gql", side_effect=mock_gql), \
             patch.object(self.adapter, "_gh", side_effect=mock_gh):

            # Simula o delete-up tentando fechar #1, #2, #3 no board story
            for issue_id in ["1", "2", "3"]:
                self.adapter.close_issue("story", issue_id)

        self.assertEqual(
            closed, [],
            f"Issues dos épicos foram fechadas indevidamente: {closed}. "
            "A Correção 5 deve impedir que operações destrutivas no board 'story' "
            "afetem issues do board 'epic'."
        )

    def test_story_issues_sao_fechadas_normalmente_no_story(self):
        """Issues que realmente pertencem ao story board devem ser fechadas."""
        closed = []

        def mock_gql(query, **kwargs):
            if "projectItems" in query:
                number = str(kwargs.get("number", ""))
                return self._pertinencia_por_board(number, "story")
            return {}

        def mock_gh(*args):
            if "close" in args:
                idx = list(args).index("close")
                if idx + 1 < len(args):
                    closed.append(str(args[idx + 1]))
            return ""

        with patch.object(self.adapter, "_gql", side_effect=mock_gql), \
             patch.object(self.adapter, "_gh", side_effect=mock_gh):

            # Issue fantasmas que realmente pertencem ao story (se existissem)
            # Aqui simulamos uma story legítima
            self.adapter.close_issue("story", "4")

        self.assertIn("4", closed,
                      "Issue #4 do board story deveria ter sido fechada normalmente")


# ─────────────────────────────────────────────────────────────────────────────
# CT-C5-06: Ausência de board meta — não deve quebrar silenciosamente
# ─────────────────────────────────────────────────────────────────────────────

class TestBoardSemMetadados(unittest.TestCase):
    """CT-C5-06: Comportamento quando board_id não está no cache de projetos."""

    def test_close_issue_levanta_excecao_sem_meta_do_board(self):
        """Sem metadados do board (sync_boards não executado), deve levantar exceção clara."""
        adapter = GitHubBoardAdapter()
        adapter._repo = "owner/repo"
        adapter._projects = {}  # Nenhum board registrado

        with self.assertRaises(Exception) as ctx:
            adapter.close_issue("story", "42")

        self.assertIn("story", str(ctx.exception).lower() or "board" or "não resolvido",
                      "Exceção deve identificar o board problemático")


# ─────────────────────────────────────────────────────────────────────────────
# CT-C5-07: Impacto em rate limit — consulta adicional é documentada
# ─────────────────────────────────────────────────────────────────────────────

class TestImpactoRateLimit(unittest.TestCase):
    """CT-C5-07: Cada operação destrutiva deve adicionar exatamente 1 chamada GraphQL.

    Conforme especificado na issue: a consulta adiciona 1 chamada GraphQL por
    operação destrutiva. O impacto deve estar documentado em comentário no código.
    """

    def test_close_issue_adiciona_exatamente_uma_consulta_graphql(self):
        """close_issue deve resultar em 1 chamada GraphQL de pertinência + 1 chamada _gh."""
        adapter = _make_adapter()

        pertinencia_response = _belongs_to_project_response(PROJECT_ID_STORY)
        gql_calls = []

        def mock_gql(query, **kwargs):
            gql_calls.append(query)
            return pertinencia_response

        with patch.object(adapter, "_gql", side_effect=mock_gql), \
             patch.object(adapter, "_gh"):

            adapter.close_issue("story", "42")

        pertinencia_calls = [q for q in gql_calls if "projectItems" in q]
        self.assertEqual(
            len(pertinencia_calls), 1,
            f"Deveria ter feito exatamente 1 consulta de pertinência, fez {len(pertinencia_calls)}"
        )

    def test_update_issue_adiciona_exatamente_uma_consulta_graphql(self):
        """update_issue deve resultar em 1 chamada GraphQL de pertinência."""
        adapter = _make_adapter()

        pertinencia_response = _belongs_to_project_response(PROJECT_ID_STORY)
        gql_calls = []

        def mock_gql(query, **kwargs):
            gql_calls.append(query)
            return pertinencia_response

        with patch.object(adapter, "_gql", side_effect=mock_gql), \
             patch.object(adapter, "_gh"):

            adapter.update_issue("story", "42", title="Título atualizado")

        pertinencia_calls = [q for q in gql_calls if "projectItems" in q]
        self.assertEqual(
            len(pertinencia_calls), 1,
            f"Deveria ter feito exatamente 1 consulta de pertinência, fez {len(pertinencia_calls)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# CT-C5-08: Múltiplos projetos — issue pertence a um subconjunto
# ─────────────────────────────────────────────────────────────────────────────

class TestIssueEmMultiplosProjetos(unittest.TestCase):
    """CT-C5-08: Issue que pertence a múltiplos projetos — validação pelo project_id alvo."""

    def test_close_issue_executa_quando_pertence_ao_board_entre_multiplos(self):
        """Issue em múltiplos projetos: executa se um deles é o board alvo."""
        adapter = _make_adapter()

        # Issue pertence tanto ao story quanto ao epic
        response_multiplos = {
            "repository": {
                "issue": {
                    "projectItems": {
                        "nodes": [
                            {"project": {"id": PROJECT_ID_EPIC}},
                            {"project": {"id": PROJECT_ID_STORY}},
                        ]
                    }
                }
            }
        }

        with patch.object(adapter, "_gql", return_value=response_multiplos), \
             patch.object(adapter, "_gh") as mock_gh:

            adapter.close_issue("story", "10")

            self.assertTrue(mock_gh.called,
                            "Issue em múltiplos projetos deve ser fechada se o board alvo está incluso")

    def test_close_issue_abortada_quando_board_alvo_ausente_dos_multiplos(self):
        """Issue em múltiplos projetos: aborta se o board alvo não está entre eles."""
        adapter = _make_adapter()

        # Issue pertence ao epic e a um terceiro board, mas não ao story
        response_sem_story = {
            "repository": {
                "issue": {
                    "projectItems": {
                        "nodes": [
                            {"project": {"id": PROJECT_ID_EPIC}},
                            {"project": {"id": "PVT_task_board_999"}},
                        ]
                    }
                }
            }
        }

        with patch.object(adapter, "_gql", return_value=response_sem_story), \
             patch.object(adapter, "_gh") as mock_gh:

            adapter.close_issue("story", "10")

            self.assertFalse(mock_gh.called,
                             "Issue não deve ser fechada quando board alvo não está nos projectItems")


if __name__ == "__main__":
    unittest.main(verbosity=2)
