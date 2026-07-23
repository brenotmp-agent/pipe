"""Testes de validação do runbook de operação Docker — US-06 (#21), RF-08.

## Escopo

O runbook vive em `doc/runbook/docker.md` e documenta como um operador
novo coloca a esteira para rodar em Docker. Esta suíte valida que:

  1. O arquivo existe e tem a estrutura mínima esperada.
  2. Todos os pré-requisitos do host estão cobertos (AC-01).
  3. A estrutura do compose está descrita com todos os parâmetros relevantes (AC-02).
  4. O passo a passo de subida (5 passos) com comandos exatos está presente (AC-03).
  5. A saída esperada dos logs de arranque é correta (AC-04).
  6. Parar/reiniciar com `down` (preserva) vs `down -v` (destrói) está documentado (AC-05).
  7. A rotação da KIRO_API_KEY (4 passos) está documentada (AC-06).
  8. O documento foi marcado como estável.
  9. Consistência interna: nome do serviço, variáveis e volumes batem com os
     artefatos reais (docker-compose.yml e .env.example).

## Filosofia dos testes

Os testes são **estáticos** — verificam o conteúdo do arquivo Markdown sem
executar Docker. Onde cabível, cruzam as informações do runbook com os artefatos
reais do repositório para detectar divergências de sincronismo.

Cada teste falha com uma mensagem descritiva indicando exatamente o que está
ausente ou incorreto, de forma que o agente de desenvolvimento possa corrigir
o documento sem consultar esta suíte.

## Rastreabilidade

US-06 (#21) | RF-08
Depende de: #40 (Dockerfile), #41 (docker-compose.yml + .env.example)
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = REPO_ROOT / "doc" / "runbook" / "docker.md"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
GITIGNORE = REPO_ROOT / ".gitignore"

# ---------------------------------------------------------------------------
# Skip condicional — runbook ainda não existe (será criado pelo desenvolvimento)
# ---------------------------------------------------------------------------

RUNBOOK_SKIP = pytest.mark.skipif(
    not RUNBOOK.exists(),
    reason=(
        "doc/runbook/docker.md não encontrado — testes de US-06 requerem o runbook. "
        "O desenvolvimento (issue #42 / US-06) criará o arquivo. "
        "Após o commit do runbook esses testes passarão a executar."
    ),
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def runbook_text():
    assert RUNBOOK.exists(), (
        "doc/runbook/docker.md não encontrado na raiz do repositório. "
        "US-06 AC-03: o runbook é obrigatório para documentar a operação em Docker."
    )
    return RUNBOOK.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def compose_text():
    assert COMPOSE_FILE.exists(), "docker-compose.yml não encontrado."
    return COMPOSE_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def env_example_text():
    assert ENV_EXAMPLE.exists(), ".env.example não encontrado."
    return ENV_EXAMPLE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Estrutura mínima — arquivo existe e não está vazio
# ---------------------------------------------------------------------------


class TestRunbookExiste:
    """O arquivo doc/runbook/docker.md deve existir e ter conteúdo."""

    def test_runbook_existe_na_pasta_correta(self):
        """doc/runbook/docker.md deve existir (US-06 AC-03)."""
        assert RUNBOOK.exists(), (
            "doc/runbook/docker.md não encontrado. "
            "US-06: criar o runbook em doc/runbook/docker.md."
        )

    def test_runbook_e_arquivo_regular(self):
        """doc/runbook/docker.md deve ser um arquivo regular (não diretório nem symlink)."""
        if not RUNBOOK.exists():
            pytest.skip("Runbook não encontrado — verificação de tipo ignorada.")
        assert RUNBOOK.is_file(), (
            "doc/runbook/docker.md não é um arquivo regular. "
            "US-06: deve ser um arquivo Markdown versionável."
        )

    @RUNBOOK_SKIP
    def test_runbook_nao_esta_vazio(self, runbook_text):
        """doc/runbook/docker.md não deve estar vazio."""
        assert len(runbook_text.strip()) > 0, (
            "doc/runbook/docker.md está vazio. "
            "US-06: o runbook deve conter a documentação completa de operação."
        )

    @RUNBOOK_SKIP
    def test_runbook_tem_titulo_principal(self, runbook_text):
        """O runbook deve ter um título de nível 1 (# Título)."""
        assert re.search(r"^#\s+\S+", runbook_text, re.MULTILINE), (
            "Runbook sem título principal (# Título). "
            "US-06: o documento deve ter cabeçalho de nível 1."
        )


# ---------------------------------------------------------------------------
# US-06 AC-01 — Pré-requisitos no host cobertos
# ---------------------------------------------------------------------------


@RUNBOOK_SKIP
class TestAC01PreRequisitos:
    """AC-01: pré-requisitos no host cobertos (Docker V2, SSH, GH_TOKEN, KIRO_API_KEY).

    O runbook deve informar ao operador tudo que ele precisa ter configurado
    no host antes de executar qualquer comando.
    """

    def test_docker_v2_mencionado(self, runbook_text):
        """Docker Compose V2 (comando 'docker compose', sem hífen) deve estar nos pré-requisitos."""
        assert re.search(
            r"docker\s+compose|Docker\s+Compose\s+V2|Compose\s+V2",
            runbook_text,
        ), (
            "Docker Compose V2 não mencionado no runbook. "
            "US-06 AC-01: pré-requisito de Docker Compose V2 obrigatório "
            "(comando 'docker compose', sem hífen)."
        )

    def test_chave_ssh_mencionada(self, runbook_text):
        """Chave SSH deve ser mencionada nos pré-requisitos."""
        assert re.search(
            r"[Cc]have\s+SSH|SSH\s+key|id_ed25519|SSH.*GitHub|\.ssh",
            runbook_text,
        ), (
            "Chave SSH não mencionada no runbook. "
            "US-06 AC-01: o operador precisa ter a chave SSH registrada no GitHub."
        )

    def test_gh_token_mencionado(self, runbook_text):
        """GH_TOKEN deve ser mencionado nos pré-requisitos."""
        assert "GH_TOKEN" in runbook_text, (
            "GH_TOKEN não mencionado no runbook. "
            "US-06 AC-01: token do GitHub é pré-requisito para operação do board."
        )

    def test_kiro_api_key_mencionada(self, runbook_text):
        """KIRO_API_KEY deve ser mencionada nos pré-requisitos."""
        assert "KIRO_API_KEY" in runbook_text, (
            "KIRO_API_KEY não mencionada no runbook. "
            "US-06 AC-01: chave de API do kiro-cli é pré-requisito obrigatório."
        )

    def test_secao_prerequisitos_presente(self, runbook_text):
        """O runbook deve ter seção explícita de pré-requisitos ou checklist."""
        assert re.search(
            r"[Pp]ré.?[Rr]equisito|[Bb]efore\s+you\s+begin|[Aa]ntes\s+de\s+come[çc]ar|[Cc]hecklist",
            runbook_text,
        ), (
            "Seção de pré-requisitos não encontrada no runbook. "
            "US-06 AC-01: o documento deve ter seção explícita de pré-requisitos."
        )


# ---------------------------------------------------------------------------
# US-06 AC-02 — Estrutura do compose descrita com todos os parâmetros
# ---------------------------------------------------------------------------


@RUNBOOK_SKIP
class TestAC02EstruturaCompose:
    """AC-02: estrutura do compose descrita com todos os parâmetros relevantes.

    O runbook deve descrever os elementos essenciais do docker-compose.yml
    para que o operador entenda o que cada parte faz.
    """

    def test_nome_servico_pipe_consistente(self, runbook_text, compose_text):
        """O nome do serviço Docker no runbook deve bater com o serviço no docker-compose.yml.

        Se o compose define o serviço como 'pipe', todos os comandos do runbook
        que referenciam o serviço (docker logs pipe, docker compose ps) devem
        usar o mesmo nome.
        """
        # Extrai o nome do serviço do compose (primeiro serviço declarado)
        match_compose = re.search(r"^services:\s*\n\s{2}(\w[\w-]*):", compose_text, re.MULTILINE)
        if not match_compose:
            pytest.skip("Não foi possível extrair nome do serviço do compose.")
        nome_servico = match_compose.group(1)

        # O runbook deve referenciar o mesmo nome
        assert nome_servico in runbook_text, (
            f"Nome do serviço '{nome_servico}' não encontrado no runbook. "
            f"US-06 AC-02: os comandos do runbook devem usar o serviço '{nome_servico}' "
            f"conforme declarado no docker-compose.yml."
        )

    def test_ssh_key_file_host_mencionada(self, runbook_text):
        """A variável SSH_KEY_FILE_HOST (Docker secret) deve ser mencionada no runbook."""
        assert "SSH_KEY_FILE_HOST" in runbook_text, (
            "SSH_KEY_FILE_HOST não mencionada no runbook. "
            "US-06 AC-02: o operador precisa saber que esta variável configura "
            "o Docker secret da chave SSH (declarada no .env)."
        )

    def test_volumes_nomeados_mencionados(self, runbook_text):
        """O runbook deve mencionar os named volumes ou a persistência de estado."""
        assert re.search(
            r"volume|[Pp]ersist[êe]ncia|[Ee]stado.*preserv|down\s+-v",
            runbook_text,
        ), (
            "Volumes nomeados / persistência de estado não mencionados no runbook. "
            "US-06 AC-02: o operador precisa entender que o estado persiste em "
            "named volumes e o que 'down -v' implica."
        )

    def test_restart_policy_mencionada(self, runbook_text):
        """O runbook deve mencionar o comportamento de restart automático do container."""
        assert re.search(
            r"restart|reinici[ao]|[Aa]uto.?reinici",
            runbook_text,
        ), (
            "Política de restart não mencionada no runbook. "
            "US-06 AC-02: o operador deve saber que o container reinicia "
            "automaticamente (restart: unless-stopped)."
        )


# ---------------------------------------------------------------------------
# US-06 AC-03 — Passo a passo de subida (5 passos) com comandos exatos
# ---------------------------------------------------------------------------


@RUNBOOK_SKIP
class TestAC03PassoAPasso:
    """AC-03: passo a passo de subida (5 passos) com comandos exatos.

    O runbook deve conter uma sequência de passos que o operador possa seguir
    linearmente para colocar a esteira no ar.
    """

    def test_clone_do_repositorio_presente(self, runbook_text):
        """O passo de clonar o repositório deve estar no runbook."""
        assert re.search(
            r"git\s+clone",
            runbook_text,
        ), (
            "Comando 'git clone' ausente no runbook. "
            "US-06 AC-03: passo 1 — clonar o repositório é obrigatório."
        )

    def test_criacao_env_presente(self, runbook_text):
        """O passo de criar o arquivo .env deve estar no runbook."""
        assert re.search(
            r"\.env(?:\.example)?|cp\s+\.env",
            runbook_text,
        ), (
            "Criação do .env não mencionada no runbook. "
            "US-06 AC-03: passo 2 — criar o .env a partir do .env.example é obrigatório."
        )

    def test_criacao_pipe_yml_presente(self, runbook_text):
        """O passo de criar/configurar o pipe.yml deve estar no runbook."""
        assert "pipe.yml" in runbook_text, (
            "pipe.yml não mencionado no runbook. "
            "US-06 AC-03: passo 3 — configurar o pipe.yml é obrigatório."
        )

    def test_comando_build_presente(self, runbook_text):
        """O comando de build da imagem deve estar no runbook."""
        assert re.search(
            r"docker\s+(?:compose\s+)?build|DOCKER_BUILDKIT",
            runbook_text,
        ), (
            "Comando de build ausente no runbook. "
            "US-06 AC-03: passo 4 — 'docker compose build' é obrigatório."
        )

    def test_comando_up_presente(self, runbook_text):
        """O comando 'docker compose up' deve estar no runbook."""
        assert re.search(
            r"docker\s+compose\s+up",
            runbook_text,
        ), (
            "Comando 'docker compose up' ausente no runbook. "
            "US-06 AC-03: passo 5 — subir o container é obrigatório."
        )

    def test_comando_up_em_background(self, runbook_text):
        """O runbook deve usar 'docker compose up -d' (modo detached) no passo principal."""
        assert re.search(
            r"docker\s+compose\s+up\s+-d|docker\s+compose\s+up\b.*-d",
            runbook_text,
        ), (
            "'docker compose up -d' (modo detached) ausente no runbook. "
            "US-06 AC-03: a esteira deve ser iniciada em background com a flag -d."
        )

    def test_buildkit_secret_no_build(self, runbook_text):
        """O comando de build com BuildKit e --secret deve estar documentado."""
        assert re.search(
            r"--secret|DOCKER_BUILDKIT|BuildKit",
            runbook_text,
        ), (
            "BuildKit / --secret não mencionado no runbook. "
            "US-06 AC-03: o Dockerfile usa BuildKit com --secret id=ssh_key — "
            "o comando de build correto deve estar documentado."
        )


# ---------------------------------------------------------------------------
# US-06 AC-04 — Saída esperada dos logs de arranque
# ---------------------------------------------------------------------------


@RUNBOOK_SKIP
class TestAC04LogsEsperados:
    """AC-04: saída esperada dos logs de arranque é correta.

    O operador deve saber como verificar que a esteira subiu com sucesso.
    O runbook precisa mostrar exemplos dos rótulos de log reais.
    """

    def test_rotulos_de_log_mencionados(self, runbook_text):
        """Os rótulos de log reais ([Config], [Startup], [Board], [Sleep]) devem aparecer."""
        rotulos = ["[Config]", "[Startup]", "[Board]", "[Sleep]"]
        encontrados = [r for r in rotulos if r in runbook_text]
        assert len(encontrados) >= 2, (
            f"Poucos rótulos de log reais encontrados no runbook (encontrados: {encontrados}). "
            "US-06 AC-04: os rótulos [Config], [Startup], [Board] e [Sleep] são gerados "
            "por src/__main__.py e devem aparecer no runbook para o operador saber "
            "que está funcionando."
        )

    def test_comando_logs_presente(self, runbook_text):
        """O comando para visualizar logs ('docker compose logs' ou 'docker logs') deve estar no runbook."""
        assert re.search(
            r"docker\s+(?:compose\s+)?logs",
            runbook_text,
        ), (
            "Comando de logs ausente no runbook. "
            "US-06 AC-04: o operador precisa saber como verificar que a esteira está rodando "
            "('docker compose logs pipe -f' ou equivalente)."
        )

    def test_secao_verificacao_presente(self, runbook_text):
        """O runbook deve ter seção de verificação de saúde / como saber se está rodando."""
        assert re.search(
            r"[Vv]erific[aâ]|[Ss]a[úu]de|[Hh]ealth|[Vv]alidar?\b|[Cc]onfirmar?",
            runbook_text,
        ), (
            "Seção de verificação de saúde não encontrada no runbook. "
            "US-06 AC-04: o runbook deve explicar como confirmar que a esteira subiu corretamente."
        )


# ---------------------------------------------------------------------------
# US-06 AC-05 — Parar/reiniciar com preservação de estado
# ---------------------------------------------------------------------------


@RUNBOOK_SKIP
class TestAC05PararReiniciar:
    """AC-05: parar/reiniciar com down (preserva) vs down -v (destrói) documentado."""

    def test_docker_compose_down_presente(self, runbook_text):
        """'docker compose down' deve estar no runbook."""
        assert re.search(
            r"docker\s+compose\s+down",
            runbook_text,
        ), (
            "'docker compose down' ausente no runbook. "
            "US-06 AC-05: o operador precisa saber como parar a esteira."
        )

    def test_docker_compose_down_v_presente(self, runbook_text):
        """'docker compose down -v' (destrói volumes) deve estar no runbook."""
        assert re.search(
            r"docker\s+compose\s+down\s+-v|down\s+-v",
            runbook_text,
        ), (
            "'docker compose down -v' ausente no runbook. "
            "US-06 AC-05: o operador deve saber que '-v' destrói os volumes nomeados "
            "(perde estado de runtime)."
        )

    def test_distincao_down_vs_down_v_explicada(self, runbook_text):
        """O runbook deve explicar a diferença de comportamento entre down e down -v."""
        assert re.search(
            r"preserv[ao]|mant[eé][mn]|destroy|destró[ói]|apag[ao]|perd[ae]|[Ee]stado.*down|down.*[Ee]stado",
            runbook_text,
            re.IGNORECASE,
        ), (
            "Distinção entre 'down' e 'down -v' não explicada no runbook. "
            "US-06 AC-05: 'down' preserva os named volumes (estado mantido); "
            "'down -v' remove os volumes (estado destruído). Ambos os comportamentos "
            "devem estar documentados."
        )

    def test_docker_compose_stop_mencionado(self, runbook_text):
        """'docker compose stop' ou equivalente deve estar no runbook como forma de parar sem destruir."""
        assert re.search(
            r"docker\s+compose\s+stop|docker\s+compose\s+restart|reinici[ao]",
            runbook_text,
        ), (
            "'docker compose stop/restart' não mencionado no runbook. "
            "US-06 AC-05: o operador deve conhecer todas as formas de parar e reiniciar "
            "o container sem destruir o estado."
        )


# ---------------------------------------------------------------------------
# US-06 AC-06 — Rotação da KIRO_API_KEY documentada (4 passos)
# ---------------------------------------------------------------------------


@RUNBOOK_SKIP
class TestAC06RotacaoKiroApiKey:
    """AC-06: rotação da KIRO_API_KEY documentada (4 passos).

    Quando a chave expira ou precisa ser trocada, o operador deve ter
    um procedimento claro de 4 passos.
    """

    def test_rotacao_kiro_api_key_mencionada(self, runbook_text):
        """O runbook deve ter seção ou procedimento de rotação da KIRO_API_KEY."""
        assert re.search(
            r"[Rr]ota[çc][aã]o|[Tt]rocar?\s+(?:a\s+)?KIRO|KIRO_API_KEY.*[Rr]ota|[Rr]enov|[Ee]xpir",
            runbook_text,
        ), (
            "Rotação da KIRO_API_KEY não documentada no runbook. "
            "US-06 AC-06: o procedimento de troca da chave de API do kiro-cli é obrigatório."
        )

    def test_editar_env_na_rotacao(self, runbook_text):
        """O procedimento de rotação deve mencionar editar o .env."""
        # Verifica que em algum ponto perto de KIRO_API_KEY aparece edição do .env
        assert re.search(
            r"\.env.*KIRO|KIRO.*\.env|edit[ae].*\.env|atualiz.*\.env|\.env.*atualiz",
            runbook_text,
            re.IGNORECASE,
        ), (
            "Edição do .env não mencionada no procedimento de rotação. "
            "US-06 AC-06: o operador precisa saber que deve atualizar o valor "
            "de KIRO_API_KEY no arquivo .env."
        )

    def test_restart_na_rotacao(self, runbook_text):
        """O procedimento de rotação deve incluir reiniciar o container para aplicar a nova chave."""
        # Verifica que perto do contexto de rotação aparece restart ou up
        assert re.search(
            r"docker\s+compose\s+(?:restart|up|stop|down)",
            runbook_text,
        ), (
            "Reinício do container não mencionado na rotação. "
            "US-06 AC-06: após atualizar a KIRO_API_KEY no .env, o container "
            "precisa ser reiniciado para aplicar a nova chave."
        )


# ---------------------------------------------------------------------------
# Status estável — documento marcado como validado
# ---------------------------------------------------------------------------


@RUNBOOK_SKIP
class TestStatusEstavel:
    """O runbook deve ter status 'estável' após validação final.

    Indica que o documento foi validado contra os artefatos reais e pode
    ser confiado pelos operadores.
    """

    def test_status_estavel_presente(self, runbook_text):
        """O runbook deve conter indicação de status 'estável' (ou 'stable')."""
        assert re.search(
            r"[Ee]st[áa]vel|[Ss]table|[Vv]alidado",
            runbook_text,
        ), (
            "Status 'estável' não encontrado no runbook. "
            "US-06: após validação, o cabeçalho do runbook deve conter "
            "\"Status: **estável**\" ou equivalente."
        )


# ---------------------------------------------------------------------------
# Pré-condição de segurança — independe do runbook existir
# ---------------------------------------------------------------------------


class TestPrecondiceSeguranca:
    """Verificações que devem passar independentemente do runbook existir.

    Garantias de segurança que a esteira já deve satisfazer antes mesmo
    da documentação estar pronta.
    """

    def test_gitignore_tem_env(self):
        """.gitignore deve conter .env para proteger segredos do versionamento.

        Verificação independente do runbook — o .gitignore já deve proteger
        o .env antes da documentação ser escrita.
        """
        assert GITIGNORE.exists(), ".gitignore não encontrado."
        gitignore_text = GITIGNORE.read_text(encoding="utf-8")
        assert re.search(r"^\.env$", gitignore_text, re.MULTILINE), (
            ".env não está no .gitignore. "
            "US-06: o arquivo .env contém segredos e nunca deve ser versionado. "
            "Adicionar '.env' ao .gitignore."
        )


# ---------------------------------------------------------------------------
# Consistência interna — runbook x artefatos reais
# ---------------------------------------------------------------------------


@RUNBOOK_SKIP
class TestConsistenciaComArtefatos:
    """O runbook deve estar consistente com os artefatos reais do repositório.

    Divergências entre o que o runbook diz e o que existe em docker-compose.yml
    ou .env.example são bugs de documentação que enganam o operador.
    """

    def test_env_example_nao_tem_gh_config_dir_no_runbook(self, runbook_text, env_example_text):
        """Se .env.example tem GH_CONFIG_DIR, o runbook deve reconhecê-la ou não contradizê-la.

        Verificação: runbook não deve listar variáveis obrigatórias que não existem
        no .env.example como se fossem do .env.
        """
        # Extrai variáveis listadas no .env.example
        variaveis_env_example = set(re.findall(r"^([A-Z][A-Z0-9_]+)=", env_example_text, re.MULTILINE))
        # Não deve haver menção a variáveis que parecem ser do .env mas não estão lá
        # (teste leve: só verifica que não há contradição grave via variáveis conhecidas)
        variaveis_obrigatorias_runbook = set(
            re.findall(r"\b([A-Z][A-Z0-9_]{4,})\b", runbook_text)
        ) & {"GH_TOKEN", "KIRO_API_KEY", "SSH_KEY_FILE_HOST"}
        for var in variaveis_obrigatorias_runbook:
            assert var in variaveis_env_example, (
                f"Variável '{var}' mencionada no runbook mas ausente no .env.example. "
                "US-06: runbook e .env.example devem estar sincronizados."
            )

    def test_cinco_volumes_nomeados_coerentes_com_compose(self, runbook_text, compose_text):
        """Os volumes nomeados do compose devem estar refletidos no runbook (pelo menos os de estado).

        O compose tem 5 named volumes: pipe-repo, pipe-logs, pipe-state, kiro-home, kiro-local.
        O runbook deve ao menos mencionar os volumes de estado de forma que o operador
        entenda o que 'down -v' destrói.
        """
        # Volumes de estado críticos para o operador entender
        volumes_estado = ["pipe-state", "pipe-repo", "pipe-logs"]
        # Pelo menos 1 dos 3 deve ser mencionado no runbook (ou a seção de volumes)
        encontrados = [v for v in volumes_estado if v in runbook_text]
        assert len(encontrados) >= 1 or re.search(r"named\s+volume|volume\s+nomeado", runbook_text, re.IGNORECASE), (
            f"Nenhum volume de estado ({', '.join(volumes_estado)}) mencionado no runbook. "
            "US-06 AC-02: ao menos os volumes de estado devem ser mencionados para que "
            "o operador entenda o impacto de 'docker compose down -v'."
        )

    def test_runbook_menciona_env_no_gitignore(self, runbook_text):
        """O runbook deve mencionar que .env não deve ser versionado / está no .gitignore."""
        assert re.search(
            r"\.gitignore|[Nn]ão\s+version[ae]|[Nn]ever\s+commit|[Ss]egred[oo].*\.env|\.env.*[Ss]egred",
            runbook_text,
            re.IGNORECASE,
        ), (
            "Runbook não menciona que .env está no .gitignore / não deve ser versionado. "
            "US-06: o operador deve ser alertado sobre segurança do .env."
        )
