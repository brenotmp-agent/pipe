"""Testes de regressão para a detecção de rate limit do GitHubBoardAdapter.

Contexto do bug (falso-positivo):
    _handle_rate_limit escaneava f"{output} {error}" — onde `output` é o CORPO
    da resposta HTTP. A issue #3 ("Análise de custo de requisição GitHub") tem
    no body a expressão "Rate Limit" + um log colado. Assim, TODA listagem de
    issues devolvia um corpo contendo "rate limit" num HTTP 200 bem-sucedido, o
    que era classificado como *secondary* (remaining ~5000 > 0), dobrava o
    throttle e ativava penalty por horas — mesmo sem nenhum limite real.

Estes testes garantem que a detecção use SOMENTE sinais de transporte:
    - status HTTP 403/429,
    - stderr do gh,
    - seção estruturada `errors` do GraphQL.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.github_board import GitHubBoardAdapter


@pytest.fixture
def adapter(monkeypatch):
    a = GitHubBoardAdapter()
    # Neutraliza qualquer espera real para os testes rodarem instantaneamente.
    monkeypatch.setattr("src.adapters.github_board.time.sleep", lambda *_: None)
    # Evita fallback que chamaria a rede (/rate_limit).
    monkeypatch.setattr(a, "_get_rate_limit_info", lambda: {})
    return a


# Corpo de resposta 200 que CONTÉM "rate limit" no conteúdo da issue.
BODY_WITH_RATE_LIMIT_TEXT = (
    '{"data":{"node":{"items":{"pageInfo":{"hasNextPage":false},'
    '"nodes":[{"id":"I_1","content":{"number":3,'
    '"title":"Análise de custo de requisição GitHub",'
    '"body":"Precisamos evitar tomar um Rate Limit. [GitHub] Secondary rate limit ...",'
    '"labels":{"nodes":[]}}}]}}}}'
)


def test_body_com_texto_rate_limit_nao_dispara(adapter):
    """HTTP 200 cujo BODY contém 'rate limit' NÃO deve ser tratado como limite."""
    headers = {"__status__": 200, "x-ratelimit-remaining": "4994",
               "x-ratelimit-limit": "5000"}
    before = adapter._throttle_value
    assert adapter._handle_rate_limit(BODY_WITH_RATE_LIMIT_TEXT, "", headers) is False
    # E não pode ter mexido no throttle.
    assert adapter._throttle_value == before


def test_status_403_dispara_secondary(adapter):
    """HTTP 403 com quota restante => secondary rate limit (throttle sobe)."""
    headers = {"__status__": 403, "x-ratelimit-remaining": "4999"}
    before = adapter._throttle_value
    assert adapter._handle_rate_limit("", "", headers) is True
    assert adapter._throttle_value > before  # _throttle_hit dobrou


def test_status_429_dispara(adapter):
    headers = {"__status__": 429, "retry-after": "30"}
    assert adapter._handle_rate_limit("", "", headers) is True


def test_stderr_rate_limit_dispara(adapter):
    """Mensagem de rate limit no stderr do gh dispara mesmo sem status."""
    err = "gh: API rate limit exceeded for user"
    assert adapter._handle_rate_limit("", err, {"__status__": 200}) is True


def test_graphql_errors_rate_limited_dispara(adapter):
    """Resposta GraphQL 200 com errors[].type=RATE_LIMITED dispara."""
    output = ('{"errors":[{"type":"RATE_LIMITED",'
              '"message":"API rate limit exceeded"}]}')
    headers = {"__status__": 200, "x-ratelimit-remaining": "0"}
    assert adapter._handle_rate_limit(output, "", headers) is True


def test_primary_rate_limit_remaining_zero(adapter):
    """Status 403 + remaining 0 + reset => primary (não mexe no throttle)."""
    import time as _t
    headers = {
        "__status__": 403,
        "x-ratelimit-remaining": "0",
        "x-ratelimit-limit": "5000",
        "x-ratelimit-used": "5000",
        "x-ratelimit-reset": str(int(_t.time()) + 60),
        "x-ratelimit-resource": "graphql",
    }
    before = adapter._throttle_value
    assert adapter._handle_rate_limit("", "", headers) is True
    # Primary não deve escalar o throttle/penalty.
    assert adapter._throttle_value == before


def test_resposta_normal_sem_sinais_nao_dispara(adapter):
    """HTTP 200 comum, sem sinais, não dispara."""
    headers = {"__status__": 200, "x-ratelimit-remaining": "4990"}
    assert adapter._handle_rate_limit('{"data":{}}', "", headers) is False


# ── _graphql_rate_limited: precisão ───────────────────────────────────────────

def test_graphql_rate_limited_ignora_conteudo_de_issue():
    a = GitHubBoardAdapter()
    assert a._graphql_rate_limited(BODY_WITH_RATE_LIMIT_TEXT) is False


def test_graphql_rate_limited_detecta_errors():
    a = GitHubBoardAdapter()
    out = '{"errors":[{"type":"RATE_LIMITED","message":"exceeded"}]}'
    assert a._graphql_rate_limited(out) is True


def test_graphql_rate_limited_body_invalido():
    a = GitHubBoardAdapter()
    assert a._graphql_rate_limited("not json") is False
    assert a._graphql_rate_limited("") is False


# ── _parse_headers: captura de status ─────────────────────────────────────────

def test_parse_headers_captura_status():
    a = GitHubBoardAdapter()
    block = "HTTP/2 403 Forbidden\r\nx-ratelimit-remaining: 4999\r\nRetry-After: 60"
    headers = a._parse_headers(block)
    assert headers["__status__"] == 403
    assert headers["x-ratelimit-remaining"] == "4999"
    assert headers["retry-after"] == "60"


def test_parse_headers_status_200():
    a = GitHubBoardAdapter()
    headers = a._parse_headers("HTTP/1.1 200 OK\nContent-Type: application/json")
    assert headers["__status__"] == 200
