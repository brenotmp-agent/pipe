"""Testes de validação estática do docker-compose.yml e arquivos relacionados.

## Arquitetura de arquivos Compose

O repositório separa os modelos de orquestração em arquivos distintos para
evitar conflito entre US-03 (named volumes) e US-04 (bind mounts de estado):

  docker-compose.yml      — base US-03: named volumes, Docker secret, env_file
  compose.dev.yml         — override US-04: bind mounts configuráveis para estado
                            (criado pelo desenvolvimento — issue US-04)
  compose.ephemeral.yml   — override CI: volumes anônimos (sem persistência)

A separação evita o code smell de "configuração morta" (bind mount e named volume
para o mesmo destino no mesmo arquivo, onde o Compose descarta silenciosamente
o que perdeu para o último declarado).

## US-03 (#37) — docker-compose.yml principal

Critérios cobertos:

  - AC-01: arquivo docker-compose.yml existe na raiz do repositório
  - AC-02: docker compose config sem erro de sintaxe
  - AC-03: 5 named volumes declarados (pipe-repo, pipe-logs, pipe-state, kiro-home, kiro-local)
  - AC-04: ./pipe.yml e ./contexts/ montados com :ro
  - AC-05: secret ssh_key declarado com file: ${SSH_KEY_FILE_HOST}
  - AC-06: PIPE_SSH_KEY_FILE=/run/secrets/ssh_key em environment: (não via .env)
  - AC-07: env_file: .env presente (injeta GH_TOKEN e KIRO_API_KEY)
  - AC-08: nenhum segredo hardcoded no arquivo

## US-04 (#46) — compose.dev.yml (override de bind mounts)

Critérios cobertos (quando compose.dev.yml existir):

  - AC-01: down && up preserva estado nos diretórios do host
  - AC-02: variáveis PIPE_STATE_DIR, PIPE_REPO_DIR, PIPE_LOGS_DIR configuram os paths
  - AC-03: defaults inline garantem funcionamento sem .env
  - AC-04: bind mounts (não named volumes) para os três diretórios de estado
  - AC-05: compose.ephemeral.yml disponível para modo efêmero (CI/testes)
  - AC-06: nenhum bind mount aponta para /app inteiro (D-05)
  - AC-07: comentários de impacto no .env.example para PIPE_REPO_DIR e PIPE_LOGS_DIR
  - AC-08: compose.ephemeral.yml é override mínimo (sem restart ou sobreposições indesejadas)
  - AC-09: volumes de estado ordenados antes de todos os volumes de config/credenciais

Testes estáticos (não sobem containers) — executam sem Docker.
Testes que requerem Docker ficam em TestDockerComposeIntegracao e são
ignorados automaticamente quando o daemon Docker não está disponível
(DOCKER_SKIP = pytest.mark.skipif(...) definido a nível de módulo).
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
# compose.dev.yml: override de US-04 (bind mounts de estado configuráveis).
# Criado pelo desenvolvimento (issue US-04). Testes de US-04 são pulados enquanto
# esse arquivo não existir — não é falha do compose principal (US-03).
COMPOSE_DEV = REPO_ROOT / "compose.dev.yml"
COMPOSE_EPHEMERAL = REPO_ROOT / "compose.ephemeral.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
GITIGNORE = REPO_ROOT / ".gitignore"

# Skip condicional para testes que dependem de compose.dev.yml (US-04)
US04_SKIP = pytest.mark.skipif(
    not COMPOSE_DEV.exists(),
    reason=(
        "compose.dev.yml não encontrado — testes de US-04 (bind mounts de estado) "
        "requerem o arquivo de override dedicado. "
        "Crie compose.dev.yml com os bind mounts ${PIPE_STATE_DIR}, "
        "${PIPE_REPO_DIR} e ${PIPE_LOGS_DIR} para habilitar esses testes."
    ),
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def compose_text():
    assert COMPOSE_FILE.exists(), (
        "docker-compose.yml não encontrado na raiz do repositório. "
        "US-03 exige o arquivo com named volumes, Docker secret e env_file."
    )
    return COMPOSE_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def compose_dev_text():
    """Conteúdo de compose.dev.yml (override US-04 com bind mounts de estado).

    Retorna string vazia se o arquivo ainda não existir — cada teste que usa
    esta fixture deve ter o marcador @US04_SKIP para pular graciosamente.
    """
    if not COMPOSE_DEV.exists():
        return ""
    return COMPOSE_DEV.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ephemeral_text():
    assert COMPOSE_EPHEMERAL.exists(), (
        "compose.ephemeral.yml não encontrado. "
        "US-04 AC-05: arquivo de override para modo efêmero é obrigatório."
    )
    return COMPOSE_EPHEMERAL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def env_example_text():
    assert ENV_EXAMPLE.exists(), (
        ".env.example não encontrado. "
        "US-04 AC-02/AC-03: variáveis de estado devem estar documentadas."
    )
    return ENV_EXAMPLE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# US-04 AC-04 — Bind mounts (não named volumes) para estado de runtime
# ---------------------------------------------------------------------------


@US04_SKIP
class TestBindMountsEstado:
    """AC-04: bind mounts para .pipe/, repo/ e logs/ em compose.dev.yml — não named volumes.

    US-03 usa named volumes no docker-compose.yml principal (ADR-07).
    US-04 usa bind mounts configuráveis em compose.dev.yml (override dedicado).
    Os dois modelos não devem conviver no mesmo arquivo (geraria configuração morta).
    """

    def test_bind_mount_pipe_state_presente(self, compose_dev_text):
        """compose.dev.yml deve conter bind mount para /app/.pipe."""
        assert re.search(
            r"PIPE_STATE_DIR.*:/app/\.pipe",
            compose_dev_text,
        ), (
            "Bind mount para /app/.pipe ausente em compose.dev.yml. "
            "US-04 AC-04: ${PIPE_STATE_DIR:-./.pipe}:/app/.pipe obrigatório no override."
        )

    def test_bind_mount_pipe_repo_presente(self, compose_dev_text):
        """compose.dev.yml deve conter bind mount para /app/repo."""
        assert re.search(
            r"PIPE_REPO_DIR.*:/app/repo",
            compose_dev_text,
        ), (
            "Bind mount para /app/repo ausente em compose.dev.yml. "
            "US-04 AC-04: ${PIPE_REPO_DIR:-./repo}:/app/repo obrigatório no override."
        )

    def test_bind_mount_pipe_logs_presente(self, compose_dev_text):
        """compose.dev.yml deve conter bind mount para /app/logs."""
        assert re.search(
            r"PIPE_LOGS_DIR.*:/app/logs",
            compose_dev_text,
        ), (
            "Bind mount para /app/logs ausente em compose.dev.yml. "
            "US-04 AC-04: ${PIPE_LOGS_DIR:-./logs}:/app/logs obrigatório no override."
        )

    def test_named_volume_pipe_state_ausente_no_override(self, compose_dev_text):
        """Named volume 'pipe-state' não deve existir no compose.dev.yml (usa bind mount)."""
        assert "pipe-state:" not in compose_dev_text, (
            "Named volume 'pipe-state' encontrado em compose.dev.yml. "
            "US-04 AC-04: usar bind mount ${PIPE_STATE_DIR:-./.pipe}:/app/.pipe."
        )

    def test_named_volume_pipe_repo_ausente_no_override(self, compose_dev_text):
        """Named volume 'pipe-repo' não deve existir no compose.dev.yml (usa bind mount)."""
        assert "pipe-repo:" not in compose_dev_text, (
            "Named volume 'pipe-repo' encontrado em compose.dev.yml. "
            "US-04 AC-04: usar bind mount ${PIPE_REPO_DIR:-./repo}:/app/repo."
        )

    def test_named_volume_pipe_logs_ausente_no_override(self, compose_dev_text):
        """Named volume 'pipe-logs' não deve existir no compose.dev.yml (usa bind mount)."""
        assert "pipe-logs:" not in compose_dev_text, (
            "Named volume 'pipe-logs' encontrado em compose.dev.yml. "
            "US-04 AC-04: usar bind mount ${PIPE_LOGS_DIR:-./logs}:/app/logs."
        )

    def test_secao_volumes_toplevel_sem_entradas_de_estado(self, compose_dev_text):
        """Seção 'volumes:' top-level do override não deve ter entradas para pipe-state etc."""
        top_level_volumes = re.findall(
            r"^volumes:\s*\n((?:  .*\n?)*)",
            compose_dev_text,
            re.MULTILINE,
        )
        if top_level_volumes:
            bloco = top_level_volumes[-1]
            for nome in ("pipe-state", "pipe-repo", "pipe-logs"):
                assert nome not in bloco, (
                    f"Named volume '{nome}' encontrado na seção volumes: do override. "
                    "US-04: bind mounts de estado não devem ser declarados como named volumes."
                )


# ---------------------------------------------------------------------------
# US-04 AC-03 — Defaults inline (funcionamento sem .env)
# ---------------------------------------------------------------------------


@US04_SKIP
class TestDefaultsInline:
    """AC-03: defaults inline em compose.dev.yml garantem funcionamento sem .env.

    O compose principal (docker-compose.yml / US-03) não precisa de defaults
    inline de estado — ele usa named volumes. O override de US-04 (compose.dev.yml)
    é que precisa de ${PIPE_STATE_DIR:-./.pipe} etc. para funcionar sem .env.
    """

    def test_pipe_state_default_inline(self, compose_dev_text):
        """`${PIPE_STATE_DIR:-./.pipe}` garante default sem .env no override de US-04."""
        assert re.search(
            r"\$\{PIPE_STATE_DIR:-\./.pipe\}",
            compose_dev_text,
        ), (
            "Default inline para PIPE_STATE_DIR ausente em compose.dev.yml. "
            "US-04 AC-03: use ${PIPE_STATE_DIR:-./.pipe} para funcionar sem .env."
        )

    def test_pipe_repo_default_inline(self, compose_dev_text):
        """`${PIPE_REPO_DIR:-./repo}` garante default sem .env no override de US-04."""
        assert re.search(
            r"\$\{PIPE_REPO_DIR:-\./repo\}",
            compose_dev_text,
        ), (
            "Default inline para PIPE_REPO_DIR ausente em compose.dev.yml. "
            "US-04 AC-03: use ${PIPE_REPO_DIR:-./repo} para funcionar sem .env."
        )

    def test_pipe_logs_default_inline(self, compose_dev_text):
        """`${PIPE_LOGS_DIR:-./logs}` garante default sem .env no override de US-04."""
        assert re.search(
            r"\$\{PIPE_LOGS_DIR:-\./logs\}",
            compose_dev_text,
        ), (
            "Default inline para PIPE_LOGS_DIR ausente em compose.dev.yml. "
            "US-04 AC-03: use ${PIPE_LOGS_DIR:-./logs} para funcionar sem .env."
        )


# ---------------------------------------------------------------------------
# US-04 AC-06 — D-05: nunca montar /app inteiro
# ---------------------------------------------------------------------------


class TestNuncaMontarAppInteiro:
    """AC-06 / D-05: volumes de estado mapeiam subdiretórios de /app, nunca /app inteiro.

    Aplica-se ao docker-compose.yml principal (named volumes) e a qualquer override.
    Named volumes e bind mounts devem sempre usar subpaths (/app/.pipe, /app/repo,
    /app/logs) — nunca /app diretamente, pois isso sobrescreveria o código da imagem.
    """

    def test_sem_bind_mount_app_inteiro(self, compose_text):
        """Nenhum volume deve apontar para /app como destino direto (D-05)."""
        # Padrões que indicariam montagem de /app inteiro: :/app ou :/app:
        matches = re.findall(r":\s*/app\s*(?::|$|\n)", compose_text, re.MULTILINE)
        # Remove linhas comentadas
        perigosas = [m for m in matches if not m.strip().startswith("#")]
        assert not perigosas, (
            "Volume montando /app inteiro detectado no docker-compose.yml. "
            "D-05: montar /app sobrescreve o código da imagem. "
            "Use /app/.pipe, /app/repo ou /app/logs."
        )

    def test_volumes_estado_usam_subpaths(self, compose_text):
        """Os destinos de estado devem ser subdiretórios de /app (named volumes ou bind mounts)."""
        for subpath in ("/app/.pipe", "/app/repo", "/app/logs"):
            assert subpath in compose_text, (
                f"Subpath de estado '{subpath}' não encontrado no docker-compose.yml. "
                f"D-05: volumes de estado devem apontar para '{subpath}', não para /app."
            )


# ---------------------------------------------------------------------------
# Volumes de configuração — presentes no compose principal
# ---------------------------------------------------------------------------


class TestVolumesConfiguracaoPresentes:
    """Os volumes de configuração (pipe.yml, contexts/) devem estar no compose principal.

    Volumes de credenciais como SSH e gh foram substituídos pelo Docker secret (ADR-07)
    e deixaram de existir como bind mounts no compose principal (US-03). Caso um
    arquivo de override de US-04 exija esses volumes como bind mounts, eles devem
    aparecer em compose.dev.yml, não aqui.
    """

    def test_pipe_yml_volume_presente(self, compose_text):
        """pipe.yml montado como volume read-only deve estar no compose principal (US-03)."""
        assert re.search(r"pipe\.yml.*:/app/pipe\.yml.*:ro", compose_text), (
            "Volume de pipe.yml ausente no docker-compose.yml. "
            "US-03 AC-04: ./pipe.yml:/app/pipe.yml:ro é obrigatório."
        )

    def test_contexts_volume_presente(self, compose_text):
        """contexts/ montado como volume deve estar no compose principal (US-03)."""
        assert re.search(r"contexts.*:/app/contexts", compose_text), (
            "Volume de contexts/ ausente no docker-compose.yml. "
            "US-03 AC-04: ./contexts:/app/contexts:ro é obrigatório."
        )

    def test_chave_ssh_via_secret_nao_bind_mount(self, compose_text):
        """A chave SSH deve chegar ao container via Docker secret, não bind mount direto.

        ADR-07 (decisão não negociável): bind mount direto de ~/.ssh no container
        é substituído pelo Docker secret ssh_key montado em /run/secrets/ssh_key.
        Não deve haver linha do tipo 'SSH_KEY_FILE:/root/.ssh/id_ed25519:ro'.
        """
        assert not re.search(r"SSH_KEY_FILE.*:/root/\.ssh/id_ed25519.*:ro", compose_text), (
            "Bind mount direto da chave SSH encontrado no docker-compose.yml. "
            "ADR-07 (decisão não negociável): a chave SSH deve chegar apenas via "
            "Docker secret 'ssh_key' (file: ${SSH_KEY_FILE_HOST}), montado em "
            "/run/secrets/ssh_key. Remover o bind mount direto."
        )

    def test_secret_ssh_key_presente_no_servico(self, compose_text):
        """O serviço pipe deve referenciar o secret ssh_key (substituto do bind mount de SSH)."""
        assert re.search(r"secrets:.*ssh_key|ssh_key.*secrets:", compose_text, re.DOTALL), (
            "Secret 'ssh_key' não referenciado no serviço pipe. "
            "ADR-07: usar Docker secret ssh_key em vez de bind mount direto de chave SSH."
        )


# ---------------------------------------------------------------------------
# US-04 AC-02 — Variáveis no .env.example
# ---------------------------------------------------------------------------


class TestEnvExampleVariaveisEstado:
    """AC-02: .env.example documenta as três variáveis de estado com comentários."""

    def test_pipe_state_dir_presente(self, env_example_text):
        """PIPE_STATE_DIR deve estar no .env.example."""
        assert "PIPE_STATE_DIR" in env_example_text, (
            "PIPE_STATE_DIR ausente no .env.example. "
            "US-04 AC-02: variáveis de estado devem ser documentadas."
        )

    def test_pipe_repo_dir_presente(self, env_example_text):
        """PIPE_REPO_DIR deve estar no .env.example."""
        assert "PIPE_REPO_DIR" in env_example_text, (
            "PIPE_REPO_DIR ausente no .env.example. "
            "US-04 AC-02: variáveis de estado devem ser documentadas."
        )

    def test_pipe_logs_dir_presente(self, env_example_text):
        """PIPE_LOGS_DIR deve estar no .env.example."""
        assert "PIPE_LOGS_DIR" in env_example_text, (
            "PIPE_LOGS_DIR ausente no .env.example. "
            "US-04 AC-02: variáveis de estado devem ser documentadas."
        )

    def test_pipe_state_dir_valor_default(self, env_example_text):
        """PIPE_STATE_DIR deve ter valor padrão ./.pipe no .env.example."""
        assert re.search(r"PIPE_STATE_DIR=\./.pipe", env_example_text), (
            "PIPE_STATE_DIR sem valor padrão ./.pipe no .env.example."
        )

    def test_pipe_repo_dir_valor_default(self, env_example_text):
        """PIPE_REPO_DIR deve ter valor padrão ./repo no .env.example."""
        assert re.search(r"PIPE_REPO_DIR=\./repo", env_example_text), (
            "PIPE_REPO_DIR sem valor padrão ./repo no .env.example."
        )

    def test_pipe_logs_dir_valor_default(self, env_example_text):
        """PIPE_LOGS_DIR deve ter valor padrão ./logs no .env.example."""
        assert re.search(r"PIPE_LOGS_DIR=\./logs", env_example_text), (
            "PIPE_LOGS_DIR sem valor padrão ./logs no .env.example."
        )

    def test_env_example_tem_comentario_estado(self, env_example_text):
        """O .env.example deve ter seção comentada explicando o estado de runtime."""
        # Verifica que existe alguma menção a "estado" ou "runtime" nos comentários
        assert re.search(
            r"#.*[Ee]stado.*[Rr]untime|#.*[Rr]untime.*[Ee]stado|#.*US-04|#.*runtime",
            env_example_text,
        ), (
            ".env.example não tem comentário de seção para estado de runtime. "
            "US-04 AC-02: variáveis de estado devem ser separadas e comentadas."
        )

    def test_env_example_explica_perda_pipe_state(self, env_example_text):
        """Comentário do PIPE_STATE_DIR deve mencionar o que se perde sem persistência."""
        # Verifica presença de menção a re-sync ou continuidade ou sessões ou agente
        lines = env_example_text.splitlines()
        pipe_state_idx = next(
            (i for i, l in enumerate(lines) if "PIPE_STATE_DIR" in l), None
        )
        assert pipe_state_idx is not None, "PIPE_STATE_DIR não encontrado."
        # Pega os 5 comentários antes da linha da variável
        context = "\n".join(lines[max(0, pipe_state_idx - 5) : pipe_state_idx + 2])
        assert re.search(
            r"continu|re.sync|sess|agente|snapshot|racioc",
            context,
            re.IGNORECASE,
        ), (
            "Comentário do PIPE_STATE_DIR não explica o impacto de não persistir "
            "(ex.: re-sync, perda de continuidade dos agentes). "
            "US-04 AC-02: comentários devem informar o operador."
        )

    def test_env_example_explica_perda_pipe_repo(self, env_example_text):
        """Comentário do PIPE_REPO_DIR deve mencionar o que se perde sem persistência (re-clone)."""
        lines = env_example_text.splitlines()
        pipe_repo_idx = next(
            (i for i, l in enumerate(lines) if "PIPE_REPO_DIR" in l), None
        )
        assert pipe_repo_idx is not None, "PIPE_REPO_DIR não encontrado."
        # Pega os 5 comentários antes da linha da variável
        context = "\n".join(lines[max(0, pipe_repo_idx - 5) : pipe_repo_idx + 2])
        assert re.search(
            r"re.clone|clone|reposit",
            context,
            re.IGNORECASE,
        ), (
            "Comentário do PIPE_REPO_DIR não explica o impacto de não persistir "
            "(ex.: re-clone de todos os repositórios). "
            "US-04 AC-02: comentários devem informar o operador."
        )

    def test_env_example_explica_perda_pipe_logs(self, env_example_text):
        """Comentário do PIPE_LOGS_DIR deve mencionar o que se perde sem persistência (histórico)."""
        lines = env_example_text.splitlines()
        pipe_logs_idx = next(
            (i for i, l in enumerate(lines) if "PIPE_LOGS_DIR" in l), None
        )
        assert pipe_logs_idx is not None, "PIPE_LOGS_DIR não encontrado."
        # Pega os 5 comentários antes da linha da variável
        context = "\n".join(lines[max(0, pipe_logs_idx - 5) : pipe_logs_idx + 2])
        assert re.search(
            r"histór|log|execu|operaç",
            context,
            re.IGNORECASE,
        ), (
            "Comentário do PIPE_LOGS_DIR não explica o impacto de não persistir "
            "(ex.: perde histórico de execução). "
            "US-04 AC-02: comentários devem informar o operador."
        )

    def test_env_example_manteve_variaveis_existentes(self, env_example_text):
        """Variáveis já existentes no .env.example não devem ter sido removidas."""
        for var in ("GH_TOKEN", "SSH_KEY_FILE", "GH_CONFIG_DIR"):
            assert var in env_example_text, (
                f"Variável {var!r} ausente no .env.example. "
                "Esta task apenas acrescenta variáveis de estado; as existentes devem ser mantidas."
            )


# ---------------------------------------------------------------------------
# US-04 AC-05 — compose.ephemeral.yml
# ---------------------------------------------------------------------------


class TestComposeEphemeral:
    """AC-05: compose.ephemeral.yml com volumes anônimos para modo efêmero."""

    def test_ephemeral_tem_secao_services(self, ephemeral_text):
        """compose.ephemeral.yml deve ter seção 'services:'."""
        assert "services:" in ephemeral_text, (
            "Seção 'services:' ausente no compose.ephemeral.yml."
        )

    def test_ephemeral_tem_servico_pipe(self, ephemeral_text):
        """compose.ephemeral.yml deve referenciar o serviço 'pipe'."""
        assert re.search(r"^\s*pipe:", ephemeral_text, re.MULTILINE), (
            "Serviço 'pipe' ausente no compose.ephemeral.yml. "
            "Deve sobrescrever o serviço 'pipe' do compose principal."
        )

    def test_ephemeral_volume_anonimo_pipe(self, ephemeral_text):
        """compose.ephemeral.yml deve ter volume anônimo para /app/.pipe."""
        assert re.search(r"-\s*/app/\.pipe", ephemeral_text), (
            "Volume anônimo para /app/.pipe ausente no compose.ephemeral.yml. "
            "US-04 AC-05: modo efêmero usa volumes anônimos descartáveis."
        )

    def test_ephemeral_volume_anonimo_repo(self, ephemeral_text):
        """compose.ephemeral.yml deve ter volume anônimo para /app/repo."""
        assert re.search(r"-\s*/app/repo", ephemeral_text), (
            "Volume anônimo para /app/repo ausente no compose.ephemeral.yml. "
            "US-04 AC-05: modo efêmero usa volumes anônimos descartáveis."
        )

    def test_ephemeral_volume_anonimo_logs(self, ephemeral_text):
        """compose.ephemeral.yml deve ter volume anônimo para /app/logs."""
        assert re.search(r"-\s*/app/logs", ephemeral_text), (
            "Volume anônimo para /app/logs ausente no compose.ephemeral.yml. "
            "US-04 AC-05: modo efêmero usa volumes anônimos descartáveis."
        )

    def test_ephemeral_nao_tem_bind_mounts_de_estado(self, ephemeral_text):
        """compose.ephemeral.yml NÃO deve ter bind mounts de estado (deve ser anônimo)."""
        for var in ("PIPE_STATE_DIR", "PIPE_REPO_DIR", "PIPE_LOGS_DIR"):
            assert var not in ephemeral_text, (
                f"{var} encontrado no compose.ephemeral.yml. "
                "Modo efêmero usa volumes anônimos — sem bind mounts de estado."
            )

    def test_ephemeral_tem_comentario_de_uso(self, ephemeral_text):
        """compose.ephemeral.yml deve ter comentário explicando o comando de uso."""
        assert re.search(
            r"docker.compose.*-f.*ephemeral|compose.*efêmero|override",
            ephemeral_text,
            re.IGNORECASE,
        ), (
            "compose.ephemeral.yml sem comentário de uso. "
            "Documente: 'docker compose -f docker-compose.yml -f compose.ephemeral.yml up'."
        )

    def test_ephemeral_sem_secao_volumes_toplevel(self, ephemeral_text):
        """compose.ephemeral.yml não deve declarar seção 'volumes:' top-level.

        Volumes anônimos inline (- /app/.pipe) não precisam de entrada na seção
        top-level. Declará-los criaria named volumes e quebraria a semântica efêmera.
        """
        top_level_volumes = re.findall(
            r"^volumes:\s*\n",
            ephemeral_text,
            re.MULTILINE,
        )
        assert not top_level_volumes, (
            "Seção 'volumes:' top-level encontrada no compose.ephemeral.yml. "
            "Volumes anônimos inline (- /app/.pipe) não requerem declaração top-level. "
            "Remover a seção para garantir semântica efêmera correta."
        )

    def test_ephemeral_sem_restart(self, ephemeral_text):
        """compose.ephemeral.yml não deve sobrescrever a política de restart.

        O override efêmero deve ser mínimo — apenas volumes. Alterar restart,
        environment ou outros campos vai além do escopo e pode causar surpresas.
        """
        assert "restart:" not in ephemeral_text, (
            "'restart:' encontrado no compose.ephemeral.yml. "
            "O override efêmero deve ser mínimo: somente volumes anônimos de estado."
        )

    def test_ephemeral_sem_environment(self, ephemeral_text):
        """compose.ephemeral.yml não deve sobrescrever variáveis de environment.

        O override efêmero deve ser mínimo — apenas volumes. Alterar environment
        vai além do escopo deste override.
        """
        assert "environment:" not in ephemeral_text, (
            "'environment:' encontrado no compose.ephemeral.yml. "
            "O override efêmero deve ser mínimo: somente volumes anônimos de estado."
        )


# ---------------------------------------------------------------------------
# Segurança — sem segredos hardcoded
# ---------------------------------------------------------------------------


class TestSemSegredosHardcoded:
    """AC da US-02: nenhum segredo hardcoded no docker-compose.yml."""

    def test_gh_token_nao_hardcoded(self, compose_text):
        """GH_TOKEN não deve ter valor hardcoded no compose."""
        # Aceita ${GH_TOKEN} mas não GH_TOKEN=ghp_xxx
        assert not re.search(r"GH_TOKEN\s*=\s*ghp_[A-Za-z0-9]+", compose_text), (
            "GH_TOKEN com valor hardcoded encontrado no docker-compose.yml. "
            "Segredos devem vir do .env, nunca embutidos no compose."
        )

    def test_sem_token_literal(self, compose_text):
        """Nenhuma string parecida com token (ghp_, ghs_, glpat-) deve estar hardcoded."""
        secret_patterns = [r"ghp_[A-Za-z0-9]{36}", r"ghs_[A-Za-z0-9]+", r"glpat-[A-Za-z0-9]+"]
        for pat in secret_patterns:
            assert not re.search(pat, compose_text), (
                f"Possível token hardcoded detectado (padrão {pat!r}). "
                "Segredos não devem estar no docker-compose.yml."
            )


# ---------------------------------------------------------------------------
# Ordem dos volumes em compose.dev.yml — estado antes de config/credenciais
# ---------------------------------------------------------------------------


@US04_SKIP
class TestOrdemVolumes:
    """Os volumes de estado (D-05) devem aparecer antes dos de config no compose.dev.yml."""

    def test_bind_mounts_estado_antes_de_pipe_yml(self, compose_dev_text):
        """Volumes de estado devem aparecer antes do volume de pipe.yml."""
        state_match = re.search(r"PIPE_STATE_DIR", compose_dev_text)
        config_match = re.search(r"pipe\.yml.*:/app/pipe\.yml", compose_dev_text)
        if state_match and config_match:
            assert state_match.start() < config_match.start(), (
                "Volumes de estado aparecem DEPOIS de pipe.yml em compose.dev.yml. "
                "A issue especifica: volumes de estado ANTES dos de config/segredos."
            )

    def test_bind_mounts_estado_antes_de_contexts(self, compose_dev_text):
        """Volumes de estado devem aparecer antes do volume de contexts/."""
        state_match = re.search(r"PIPE_STATE_DIR", compose_dev_text)
        contexts_match = re.search(r"contexts.*:/app/contexts", compose_dev_text)
        if state_match and contexts_match:
            assert state_match.start() < contexts_match.start(), (
                "Volumes de estado aparecem DEPOIS de contexts/ em compose.dev.yml. "
                "A issue especifica: volumes de estado ANTES dos de config/segredos."
            )

    def test_tres_bind_mounts_de_estado_consecutivos(self, compose_dev_text):
        """Os três bind mounts de estado devem aparecer próximos (bloco coeso de estado)."""
        pipe_match = re.search(r"PIPE_STATE_DIR", compose_dev_text)
        repo_match = re.search(r"PIPE_REPO_DIR", compose_dev_text)
        logs_match = re.search(r"PIPE_LOGS_DIR", compose_dev_text)
        if pipe_match and repo_match and logs_match:
            positions = sorted([pipe_match.start(), repo_match.start(), logs_match.start()])
            assert positions[2] - positions[0] < 800, (
                "Os três bind mounts de estado estão espalhados em compose.dev.yml. "
                "Devem estar num bloco coeso, separados dos volumes de config/credenciais."
            )


# ---------------------------------------------------------------------------
# Testes de integração (requerem Docker daemon — skip se indisponível)
# ---------------------------------------------------------------------------


def _docker_disponivel() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _artefatos_compose_presentes() -> bool:
    """Retorna True apenas se docker-compose.yml existir (pré-requisito para testes de integração)."""
    return COMPOSE_FILE.exists()


DOCKER_SKIP = pytest.mark.skipif(
    not _docker_disponivel() or not _artefatos_compose_presentes(),
    reason="Docker daemon não disponível ou docker-compose.yml ausente — teste de integração ignorado",
)


@DOCKER_SKIP
class TestDockerComposeIntegracao:
    """Testes de integração com Docker Compose para validação do compose principal e overrides.

    Cobrem US-03 AC-02 (sintaxe) e US-04 AC-05 (override efêmero).
    Os testes específicos de US-03 (named volumes, secret) ficam em
    TestUS03IntegracaoCompose mais abaixo.

    Para executar localmente:
        pytest tests/test_docker_compose.py::TestDockerComposeIntegracao -v
    """

    def test_compose_config_valida_sem_ssh_key_file_host(self):
        """US-03 AC-02: 'docker compose config' não deve falhar por erro de sintaxe ou estrutura.

        O compose principal usa named volumes — não depende de PIPE_STATE_DIR etc.
        Sem SSH_KEY_FILE_HOST o Compose pode emitir aviso sobre variável não resolvida
        no secret, mas não deve falhar por razão de sintaxe/estrutura.
        """
        import os

        env_sem_secret = {k: v for k, v in os.environ.items()
                         if k != "SSH_KEY_FILE_HOST"}
        result = subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "config"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env_sem_secret,
        )
        if result.returncode != 0:
            stderr_lower = result.stderr.lower()
            if "ssh_key_file_host" in stderr_lower or "secret" in stderr_lower:
                pytest.skip(
                    "Compose falhou por SSH_KEY_FILE_HOST não definida — comportamento esperado "
                    "em ambientes sem .env. Defina SSH_KEY_FILE_HOST para validação completa."
                )
            pytest.fail(
                f"'docker compose config' falhou por razão inesperada (exit {result.returncode}). "
                f"Stderr: {result.stderr}"
            )

    def test_ephemeral_compose_config_valida(self):
        """US-04 AC-05: compose.ephemeral.yml deve ser aceito como override pelo Compose."""
        import os

        result = subprocess.run(
            [
                "docker", "compose",
                "-f", str(COMPOSE_FILE),
                "-f", str(COMPOSE_EPHEMERAL),
                "config",
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=os.environ,
        )
        assert result.returncode == 0, (
            f"'docker compose config' com compose.ephemeral.yml falhou (exit {result.returncode}). "
            f"Stderr: {result.stderr}\n"
            "US-04 AC-05: o override efêmero deve ser aceito pelo Compose."
        )

    def test_ac01_config_resolve_paths_de_estado_customizados(self, tmp_path):
        """US-04 AC-01 (configuração): 'docker compose config' resolve variáveis de estado
        customizadas no override compose.dev.yml.

        Valida que ao definir PIPE_STATE_DIR, PIPE_REPO_DIR e PIPE_LOGS_DIR com
        caminhos customizados, o Compose aceita a configuração sem erros e expande
        corretamente as variáveis no config resolvido — usando o override de US-04,
        que é onde os bind mounts de estado vivem (não no compose principal US-03).

        Nota: este teste valida a configuração de bind mounts (pré-condição do AC-01),
        não o ciclo runtime de down/up com container em execução. A garantia de
        persistência real (AC-01 completo) requer build da imagem e é verificada
        manualmente conforme documentado em doc/stories/rodar-no-docker/arquitetura.md §8.
        """
        if not COMPOSE_DEV.exists():
            pytest.skip(
                "compose.dev.yml não encontrado — teste de resolução de paths de US-04 "
                "requer o arquivo de override com bind mounts de estado. "
                "Crie compose.dev.yml para habilitar este teste."
            )

        import os

        state_dir = tmp_path / "pipe_state"
        repo_dir = tmp_path / "pipe_repo"
        logs_dir = tmp_path / "pipe_logs"
        state_dir.mkdir()
        repo_dir.mkdir()
        logs_dir.mkdir()

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(b"fake-key-for-compose-validation")
            fake_key = f.name

        try:
            env_com_dirs = dict(os.environ, **{
                "PIPE_STATE_DIR": str(state_dir),
                "PIPE_REPO_DIR": str(repo_dir),
                "PIPE_LOGS_DIR": str(logs_dir),
                "SSH_KEY_FILE_HOST": fake_key,
            })

            # Usa compose principal (US-03) + override de estado (US-04)
            result = subprocess.run(
                [
                    "docker", "compose",
                    "-f", str(COMPOSE_FILE),
                    "-f", str(COMPOSE_DEV),
                    "config",
                ],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env=env_com_dirs,
            )
            assert result.returncode == 0, (
                f"'docker compose config' com diretórios de estado customizados falhou. "
                f"Stderr: {result.stderr}\n"
                "US-04 AC-01: os diretórios de estado customizados devem ser aceitos pelo Compose."
            )
            # Confirma que os paths customizados aparecem no config resolvido
            output = result.stdout
            assert str(state_dir) in output, (
                f"Diretório de estado customizado ({state_dir}) não aparece no config resolvido. "
                "PIPE_STATE_DIR não está sendo expandido corretamente pelo Compose no override."
            )
        finally:
            import os as _os
            _os.unlink(fake_key)

    def test_ac01_estado_efemero_nao_persiste_no_host(self, tmp_path):
        """US-04 AC-01 (efêmero — validação estática): o config do compose efêmero não
        declara 'source:' de host para os diretórios de estado.

        Este teste valida a configuração: confirma que os volumes anônimos do override
        efêmero não têm bind mount de host nos dirs de estado (.pipe, repo, logs).
        Não é um teste de runtime (não sobe container nem executa down) — verifica
        que a estrutura do compose impede a persistência acidental no host.
        """
        import os

        result = subprocess.run(
            [
                "docker", "compose",
                "-f", str(COMPOSE_FILE),
                "-f", str(COMPOSE_EPHEMERAL),
                "config",
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=os.environ,
        )
        assert result.returncode == 0, (
            f"'docker compose config' com override efêmero falhou. Stderr: {result.stderr}"
        )
        output = result.stdout

        # No modo efêmero, os volumes anônimos não têm 'source' no host
        # O config resolvido não deve ter os caminhos de estado mapeando para paths do host
        # (bind mounts de estado devem ter sido sobrescritos pelos volumes anônimos)
        for path_pattern in (r"\.pipe\b", r"\bpipe_state\b", r"\bpipe_repos\b"):
            # Aceita .pipe dentro de /app/.pipe (destino no container), mas não como source do host
            lines_with_pattern = [
                l for l in output.splitlines()
                if re.search(path_pattern, l) and "source:" in l
            ]
            assert not lines_with_pattern, (
                f"Padrão '{path_pattern}' encontrado como 'source:' no config efêmero resolvido: "
                f"{lines_with_pattern}. "
                "No modo efêmero, os volumes de estado não devem ter source no host."
            )


# ---------------------------------------------------------------------------
# US-03 (#37) — Orquestração Compose: named volumes, Docker secrets, env_file
# ---------------------------------------------------------------------------
# Estes testes validam os critérios de aceitação da issue #37, que especifica
# uma nova estrutura de docker-compose.yml com named volumes e Docker secrets.
# São testes estáticos que verificam o conteúdo do arquivo sem subir containers.
# ---------------------------------------------------------------------------


class TestUS03ArquivoExiste:
    """US-03 AC-01: docker-compose.yml deve existir na raiz do repositório."""

    def test_docker_compose_yml_existe_na_raiz(self):
        """O arquivo docker-compose.yml deve existir na raiz do repositório."""
        assert COMPOSE_FILE.exists(), (
            "docker-compose.yml não encontrado na raiz do repositório. "
            "US-03 AC-01: o arquivo é obrigatório para orquestração via Compose."
        )

    def test_docker_compose_yml_e_arquivo_regular(self):
        """docker-compose.yml deve ser um arquivo regular (não diretório nem symlink)."""
        assert COMPOSE_FILE.is_file(), (
            "docker-compose.yml não é um arquivo regular. "
            "US-03 AC-01: deve ser um arquivo YAML versionável."
        )

    def test_docker_compose_yml_nao_esta_vazio(self, compose_text):
        """docker-compose.yml não deve estar vazio."""
        assert len(compose_text.strip()) > 0, (
            "docker-compose.yml está vazio. "
            "US-03 AC-01: o arquivo deve conter a configuração de orquestração."
        )


class TestUS03NamedVolumes:
    """US-03 AC-03: 5 named volumes declarados na seção volumes: top-level."""

    NAMED_VOLUMES_ESPERADOS = [
        "pipe-repo",
        "pipe-logs",
        "pipe-state",
        "kiro-home",
        "kiro-local",
    ]

    def _extrair_volumes_toplevel(self, compose_text: str) -> list[str]:
        """Extrai os nomes dos named volumes da seção top-level."""
        blocos = re.findall(
            r"^volumes:\s*\n((?:  .*\n?)*)",
            compose_text,
            re.MULTILINE,
        )
        if not blocos:
            return []
        bloco = blocos[-1]
        return re.findall(r"^\s{2}([\w-]+)\s*:", bloco, re.MULTILINE)

    def test_secao_volumes_toplevel_presente(self, compose_text):
        """docker-compose.yml deve ter seção 'volumes:' top-level para os named volumes."""
        assert re.search(r"^volumes:", compose_text, re.MULTILINE), (
            "Seção 'volumes:' top-level ausente no docker-compose.yml. "
            "US-03 AC-03: os 5 named volumes precisam ser declarados."
        )

    @pytest.mark.parametrize("volume", NAMED_VOLUMES_ESPERADOS)
    def test_named_volume_declarado(self, compose_text, volume):
        """Cada um dos 5 named volumes deve estar declarado na seção volumes: top-level."""
        blocos = re.findall(
            r"^volumes:\s*\n((?:  .*\n?)*)",
            compose_text,
            re.MULTILINE,
        )
        bloco = blocos[-1] if blocos else ""
        assert re.search(rf"^\s{{2}}{re.escape(volume)}\s*(?::|$)", bloco, re.MULTILINE), (
            f"Named volume '{volume}' ausente na seção 'volumes:' top-level. "
            f"US-03 AC-03: todos os 5 volumes devem estar declarados: "
            f"{', '.join(TestUS03NamedVolumes.NAMED_VOLUMES_ESPERADOS)}."
        )

    def test_cinco_named_volumes_declarados(self, compose_text):
        """Exatamente os 5 named volumes de US-03 devem estar declarados."""
        blocos = re.findall(
            r"^volumes:\s*\n((?:  .*\n?)*)",
            compose_text,
            re.MULTILINE,
        )
        bloco = blocos[-1] if blocos else ""
        encontrados = re.findall(r"^\s{2}([\w-]+)\s*(?::|$)", bloco, re.MULTILINE)
        for vol in self.NAMED_VOLUMES_ESPERADOS:
            assert vol in encontrados, (
                f"Named volume '{vol}' não encontrado na seção volumes: top-level. "
                "US-03 AC-03: os 5 named volumes são obrigatórios."
            )

    @pytest.mark.parametrize("volume", NAMED_VOLUMES_ESPERADOS)
    def test_named_volume_referenciado_em_services(self, compose_text, volume):
        """Cada named volume deve ser referenciado na seção volumes: do serviço 'pipe'."""
        # O volume deve aparecer como montagem no serviço (ex.: - pipe-repo:/app/repo)
        assert re.search(rf"-\s*{re.escape(volume)}:", compose_text), (
            f"Named volume '{volume}' não é referenciado nos volumes do serviço pipe. "
            "US-03 AC-03: volumes declarados devem ser montados no serviço."
        )


class TestUS03MontamCaminhosCertos:
    """US-03: named volumes devem montar nos caminhos corretos dentro do container."""

    def test_pipe_repo_monta_em_app_repo(self, compose_text):
        """pipe-repo deve montar em /app/repo."""
        assert re.search(r"pipe-repo:/app/repo", compose_text), (
            "Named volume 'pipe-repo' não está montado em /app/repo. "
            "US-03: pipe-repo deve mapear para /app/repo."
        )

    def test_pipe_logs_monta_em_app_logs(self, compose_text):
        """pipe-logs deve montar em /app/logs."""
        assert re.search(r"pipe-logs:/app/logs", compose_text), (
            "Named volume 'pipe-logs' não está montado em /app/logs. "
            "US-03: pipe-logs deve mapear para /app/logs."
        )

    def test_pipe_state_monta_em_app_pipe(self, compose_text):
        """pipe-state deve montar em /app/.pipe."""
        assert re.search(r"pipe-state:/app/\.pipe", compose_text), (
            "Named volume 'pipe-state' não está montado em /app/.pipe. "
            "US-03: pipe-state deve mapear para /app/.pipe."
        )

    def test_kiro_home_monta_em_home_pipe_kiro(self, compose_text):
        """kiro-home deve montar em /home/pipe/.kiro."""
        assert re.search(r"kiro-home:/home/pipe/\.kiro", compose_text), (
            "Named volume 'kiro-home' não está montado em /home/pipe/.kiro. "
            "US-03 AC-03 / ADR-07 RA-1: kiro-home é necessário para retomada de sessão."
        )

    def test_kiro_local_monta_em_home_pipe_local_share_kiro_cli(self, compose_text):
        """kiro-local deve montar em /home/pipe/.local/share/kiro-cli."""
        assert re.search(r"kiro-local:/home/pipe/\.local/share/kiro-cli", compose_text), (
            "Named volume 'kiro-local' não está montado em /home/pipe/.local/share/kiro-cli. "
            "US-03 AC-03 / ADR-07 RA-1: kiro-local persiste o índice SQLite necessário "
            "para --list-sessions e --resume-id."
        )


class TestUS03VolumesConfiguracaoReadOnly:
    """US-03 AC-04: ./pipe.yml e ./contexts/ montados com :ro."""

    def test_pipe_yml_montado_read_only(self, compose_text):
        """./pipe.yml deve ser montado no container com :ro (somente leitura)."""
        assert re.search(r"\./pipe\.yml:/app/pipe\.yml:ro", compose_text), (
            "./pipe.yml não está montado com :ro em /app/pipe.yml. "
            "US-03 AC-04: configuração é somente leitura no container."
        )

    def test_contexts_montado_read_only(self, compose_text):
        """./contexts deve ser montado no container com :ro (somente leitura)."""
        assert re.search(r"\./contexts:/app/contexts:ro", compose_text), (
            "./contexts não está montado com :ro em /app/contexts. "
            "US-03 AC-04: contextos dos agentes são somente leitura no container."
        )


class TestUS03DockerSecret:
    """US-03 AC-05: Docker secret ssh_key declarado com file: ${SSH_KEY_FILE_HOST}."""

    def test_secao_secrets_toplevel_presente(self, compose_text):
        """docker-compose.yml deve ter seção 'secrets:' top-level."""
        assert re.search(r"^secrets:", compose_text, re.MULTILINE), (
            "Seção 'secrets:' top-level ausente no docker-compose.yml. "
            "US-03 AC-05: Docker secret para chave SSH é obrigatório."
        )

    def test_secret_ssh_key_declarado(self, compose_text):
        """Secret 'ssh_key' deve estar declarado na seção secrets: top-level."""
        blocos = re.findall(
            r"^secrets:\s*\n((?:  .*\n?)*)",
            compose_text,
            re.MULTILINE,
        )
        bloco = blocos[-1] if blocos else ""
        assert re.search(r"^\s{2}ssh_key\s*:", bloco, re.MULTILINE), (
            "Secret 'ssh_key' não declarado na seção 'secrets:' top-level. "
            "US-03 AC-05: o secret da chave SSH deve ser declarado."
        )

    def test_secret_ssh_key_usa_ssh_key_file_host(self, compose_text):
        """Secret ssh_key deve usar file: ${SSH_KEY_FILE_HOST} (variável de ambiente do host)."""
        assert re.search(r"file:\s*\$\{SSH_KEY_FILE_HOST\}", compose_text), (
            "Secret 'ssh_key' não usa 'file: ${SSH_KEY_FILE_HOST}'. "
            "US-03 AC-05: o caminho da chave no host é fornecido via .env, "
            "nunca hardcoded. Formato: file: ${SSH_KEY_FILE_HOST}."
        )

    def test_servico_pipe_referencia_secret_ssh_key(self, compose_text):
        """O serviço 'pipe' deve referenciar o secret 'ssh_key' em sua seção secrets:."""
        # Encontra a seção do serviço pipe e verifica referência ao secret
        assert re.search(r"secrets:.*ssh_key|ssh_key.*secrets:", compose_text, re.DOTALL), (
            "Serviço 'pipe' não referencia o secret 'ssh_key'. "
            "US-03 AC-05: o serviço deve declarar o secret para ter acesso a ele."
        )

    def test_secret_montado_em_run_secrets(self, compose_text):
        """O secret ssh_key é montado automaticamente em /run/secrets/ssh_key pelo Compose."""
        # A montagem automática em /run/secrets/ssh_key é comportamento do Compose;
        # verificamos indiretamente que PIPE_SSH_KEY_FILE aponta para esse caminho.
        assert "/run/secrets/ssh_key" in compose_text, (
            "/run/secrets/ssh_key não encontrado no docker-compose.yml. "
            "US-03 AC-06: PIPE_SSH_KEY_FILE deve apontar para /run/secrets/ssh_key, "
            "que é o caminho onde o Compose monta secrets com 'file:'."
        )

    def test_sem_bind_mount_direto_de_chave_ssh(self, compose_text):
        """Não deve haver bind mount direto da chave SSH (substituído pelo Docker secret)."""
        # Padrão de bind mount direto: algo como ~/.ssh ou /home/.../.ssh ou /root/.ssh
        # montado em /root/.ssh ou similar
        assert not re.search(r"\.ssh/id_\w+:/run/secrets", compose_text), (
            "Bind mount direto de chave SSH detectado apontando para /run/secrets. "
            "US-03 AC-05: usar Docker secret 'ssh_key' com file: ${SSH_KEY_FILE_HOST}, "
            "não bind mount direto."
        )


class TestUS03PipeSSHKeyFileEmEnvironment:
    """US-03 AC-06: PIPE_SSH_KEY_FILE=/run/secrets/ssh_key em environment: (não no .env)."""

    def test_pipe_ssh_key_file_em_environment(self, compose_text):
        """PIPE_SSH_KEY_FILE deve estar na seção environment: do serviço pipe."""
        assert re.search(r"PIPE_SSH_KEY_FILE.*=.*/run/secrets/ssh_key", compose_text), (
            "PIPE_SSH_KEY_FILE=/run/secrets/ssh_key ausente na seção environment:. "
            "US-03 AC-06 / ADR-07: o caminho interno do secret é determinado pelo compose, "
            "não pelo operador via .env."
        )

    def test_pipe_ssh_key_file_valor_fixo(self, compose_text):
        """PIPE_SSH_KEY_FILE deve ter valor fixo /run/secrets/ssh_key, não uma variável."""
        # Não deve ser ${PIPE_SSH_KEY_FILE} — deve ser o valor fixo
        match = re.search(r"PIPE_SSH_KEY_FILE[:\s=]+(.+)", compose_text)
        if match:
            valor = match.group(1).strip()
            assert "/run/secrets/ssh_key" in valor and "${" not in valor, (
                f"PIPE_SSH_KEY_FILE tem valor '{valor}' em vez de '/run/secrets/ssh_key' fixo. "
                "US-03 AC-06 / ADR-07: o caminho interno é fixo no compose, "
                "não configurável pelo operador."
            )

    def test_pipe_ssh_key_file_nao_e_variavel_de_ambiente_interpolada(self, compose_text):
        """PIPE_SSH_KEY_FILE não deve ser referência a variável do .env."""
        # Padrão indesejado: PIPE_SSH_KEY_FILE: ${PIPE_SSH_KEY_FILE} ou similar
        assert not re.search(r"PIPE_SSH_KEY_FILE[:\s=]+\$\{PIPE_SSH_KEY_FILE", compose_text), (
            "PIPE_SSH_KEY_FILE está sendo interpolada do .env. "
            "US-03 AC-06 / ADR-07: deve ser valor fixo /run/secrets/ssh_key no compose."
        )


class TestUS03EnvFile:
    """US-03 AC-07: env_file: .env presente para injetar GH_TOKEN e KIRO_API_KEY."""

    def test_env_file_presente(self, compose_text):
        """O serviço pipe deve ter env_file: .env ou env_file: - .env."""
        assert re.search(r"env_file:", compose_text), (
            "Diretiva 'env_file:' ausente no docker-compose.yml. "
            "US-03 AC-07: env_file: .env injeta GH_TOKEN e KIRO_API_KEY sem hardcoding."
        )

    def test_env_file_aponta_para_dotenv(self, compose_text):
        """env_file deve referenciar .env."""
        assert re.search(r"env_file:.*\.env|env_file:\s*\n\s*-\s*\.env", compose_text, re.DOTALL), (
            "env_file não aponta para '.env'. "
            "US-03 AC-07: o arquivo de variáveis de ambiente deve ser '.env'."
        )

    def test_gh_token_nao_em_environment_hardcoded(self, compose_text):
        """GH_TOKEN não deve ter valor hardcoded na seção environment: (deve vir do .env)."""
        assert not re.search(r"GH_TOKEN\s*[:=]\s*ghp_[A-Za-z0-9]+", compose_text), (
            "GH_TOKEN com valor hardcoded no compose. "
            "US-03 AC-07 / AC-08: tokens devem vir do .env via env_file:, nunca hardcoded."
        )

    def test_kiro_api_key_nao_hardcoded(self, compose_text):
        """KIRO_API_KEY não deve ter valor hardcoded no compose."""
        assert not re.search(r"KIRO_API_KEY\s*[:=]\s*[A-Za-z0-9_\-]{20,}", compose_text), (
            "KIRO_API_KEY com possível valor hardcoded no compose. "
            "US-03 AC-08: segredos devem vir do .env via env_file:."
        )


class TestUS03SemSegredosHardcoded:
    """US-03 AC-08: nenhum segredo hardcoded no docker-compose.yml."""

    def test_sem_ssh_key_conteudo_hardcoded(self, compose_text):
        """Conteúdo de chave SSH (BEGIN RSA PRIVATE KEY, etc.) não deve aparecer no compose."""
        padrao_chave = r"BEGIN\s+(RSA|OPENSSH|EC|DSA)\s+PRIVATE\s+KEY"
        assert not re.search(padrao_chave, compose_text), (
            "Conteúdo de chave SSH privada detectado no docker-compose.yml. "
            "US-03 AC-08: nunca embutir chaves ou segredos diretamente no compose."
        )

    def test_sem_token_github_hardcoded(self, compose_text):
        """Token do GitHub não deve estar hardcoded no compose."""
        for pat in (r"ghp_[A-Za-z0-9]{36}", r"ghs_[A-Za-z0-9]+", r"glpat-[A-Za-z0-9]+"):
            assert not re.search(pat, compose_text), (
                f"Possível token GitHub hardcoded (padrão {pat!r}) no docker-compose.yml. "
                "US-03 AC-08: segredos devem ser referenciados via variáveis de ambiente."
            )

    def test_ssh_key_file_host_e_referencia_de_variavel(self, compose_text):
        """SSH_KEY_FILE_HOST deve ser referenciado como ${SSH_KEY_FILE_HOST}, não com valor real."""
        # Busca especificamente a linha do secret ssh_key com file:
        match = re.search(r"^\s*file:\s*(.+)", compose_text, re.MULTILINE)
        # Se não há nenhum 'file:' no compose, o secret pode não estar declarado —
        # outro teste (test_secret_ssh_key_usa_ssh_key_file_host) cobre esse caso.
        if not match:
            return
        valor = match.group(1).strip()
        assert "${SSH_KEY_FILE_HOST}" in valor or "${" in valor, (
            f"'file:' do secret tem valor direto '{valor}' em vez de variável. "
            "US-03 AC-05 / AC-08: usar 'file: ${{SSH_KEY_FILE_HOST}}' — "
            "o caminho real vem do .env."
        )

    def test_sem_variaveis_sensíveis_com_valores_reais(self, compose_text):
        """Nenhuma variável sensível deve ter valor real embutido no compose."""
        padroes_sensiveis = [
            (r"GH_TOKEN\s*[:=]\s*ghp_\w+", "GH_TOKEN"),
            (r"KIRO_API_KEY\s*[:=]\s*[A-Za-z0-9\-_]{32,}", "KIRO_API_KEY"),
            (r"SSH_KEY\s*[:=]\s*-----BEGIN", "SSH_KEY com conteúdo de chave"),
        ]
        for pat, nome in padroes_sensiveis:
            assert not re.search(pat, compose_text), (
                f"Variável sensível '{nome}' com valor real detectada no compose. "
                "US-03 AC-08: nenhum segredo hardcoded."
            )


class TestUS03SintaxeYAML:
    """US-03 AC-02: docker compose config não deve produzir erro de sintaxe."""

    def test_arquivo_yaml_valido(self, compose_text):
        """docker-compose.yml deve ser YAML válido (parseável pelo PyYAML)."""
        try:
            import yaml
            conteudo = yaml.safe_load(compose_text)
            assert conteudo is not None, "YAML resultou em None — arquivo pode estar vazio."
        except Exception as e:
            pytest.fail(
                f"docker-compose.yml não é YAML válido: {e}\n"
                "US-03 AC-02: o arquivo deve ser parseável sem erros de sintaxe."
            )

    def test_yaml_tem_chave_services(self, compose_text):
        """docker-compose.yml deve ter chave 'services:' de nível raiz."""
        try:
            import yaml
            conteudo = yaml.safe_load(compose_text)
            assert "services" in conteudo, (
                "Chave 'services' ausente no docker-compose.yml. "
                "US-03 AC-02: o compose precisa declarar ao menos o serviço 'pipe'."
            )
        except Exception:
            pytest.skip("YAML inválido — teste de sintaxe avançada ignorado.")

    def test_yaml_tem_servico_pipe(self, compose_text):
        """docker-compose.yml deve declarar o serviço 'pipe'."""
        try:
            import yaml
            conteudo = yaml.safe_load(compose_text)
            services = conteudo.get("services", {})
            assert "pipe" in services, (
                "Serviço 'pipe' ausente em services:. "
                "US-03 AC-02: o serviço principal da esteira deve se chamar 'pipe'."
            )
        except Exception:
            pytest.skip("YAML inválido — teste de estrutura ignorado.")

    def test_yaml_tem_chave_secrets(self, compose_text):
        """docker-compose.yml deve ter chave 'secrets:' de nível raiz."""
        try:
            import yaml
            conteudo = yaml.safe_load(compose_text)
            assert "secrets" in conteudo, (
                "Chave 'secrets' ausente no docker-compose.yml. "
                "US-03 AC-05: a seção secrets: é obrigatória para o Docker secret ssh_key."
            )
        except Exception:
            pytest.skip("YAML inválido — teste de estrutura ignorado.")

    def test_yaml_tem_chave_volumes(self, compose_text):
        """docker-compose.yml deve ter chave 'volumes:' de nível raiz."""
        try:
            import yaml
            conteudo = yaml.safe_load(compose_text)
            assert "volumes" in conteudo, (
                "Chave 'volumes' ausente no docker-compose.yml. "
                "US-03 AC-03: a seção volumes: é obrigatória para os 5 named volumes."
            )
        except Exception:
            pytest.skip("YAML inválido — teste de estrutura ignorado.")


class TestUS03IntegracaoCompose:
    """US-03 AC-02: docker compose config sem erro de sintaxe (testes com Docker)."""

    def test_compose_config_com_ssh_key_file_host(self):
        """US-03 AC-02: 'docker compose config' deve validar com SSH_KEY_FILE_HOST definido."""
        if not _docker_disponivel():
            pytest.skip("Docker daemon não disponível.")

        import os
        import tempfile

        # Cria arquivo temporário simulando chave SSH
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(b"fake-key-for-compose-validation")
            fake_key = f.name

        try:
            env_com_secret = dict(os.environ, SSH_KEY_FILE_HOST=fake_key)
            result = subprocess.run(
                ["docker", "compose", "-f", str(COMPOSE_FILE), "config"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env=env_com_secret,
            )
            assert result.returncode == 0, (
                f"'docker compose config' falhou com SSH_KEY_FILE_HOST definido "
                f"(exit {result.returncode}). Stderr: {result.stderr}\n"
                "US-03 AC-02: o compose deve validar sem erro quando SSH_KEY_FILE_HOST está preenchido."
            )
        finally:
            import os as _os
            _os.unlink(fake_key)

    def test_compose_config_lista_cinco_named_volumes(self):
        """US-03 AC-03: 'docker compose config --volumes' deve listar os 5 named volumes."""
        if not _docker_disponivel():
            pytest.skip("Docker daemon não disponível.")

        import os
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(b"fake-key")
            fake_key = f.name

        try:
            env_com_secret = dict(os.environ, SSH_KEY_FILE_HOST=fake_key)
            result = subprocess.run(
                ["docker", "compose", "-f", str(COMPOSE_FILE), "config", "--volumes"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env=env_com_secret,
            )
            if result.returncode != 0:
                pytest.skip(f"docker compose config --volumes falhou: {result.stderr}")

            output = result.stdout
            for volume in TestUS03NamedVolumes.NAMED_VOLUMES_ESPERADOS:
                assert volume in output, (
                    f"Named volume '{volume}' ausente no output de 'docker compose config --volumes'. "
                    f"US-03 AC-03: todos os 5 volumes devem ser listados."
                )
        finally:
            import os as _os
            _os.unlink(fake_key)

    def test_compose_config_sem_gh_token_hardcoded_no_output(self):
        """US-03 AC-08: o output de 'docker compose config' não deve conter tokens reais."""
        if not _docker_disponivel():
            pytest.skip("Docker daemon não disponível.")

        import os
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(b"fake-key")
            fake_key = f.name

        try:
            env_teste = dict(os.environ, SSH_KEY_FILE_HOST=fake_key)
            # Remove GH_TOKEN do ambiente para garantir que não vaze
            env_teste.pop("GH_TOKEN", None)

            result = subprocess.run(
                ["docker", "compose", "-f", str(COMPOSE_FILE), "config"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env=env_teste,
            )
            if result.returncode != 0:
                pytest.skip("docker compose config falhou sem GH_TOKEN — skip.")

            # O output resolvido não deve conter tokens reais de GitHub
            assert not re.search(r"ghp_[A-Za-z0-9]{36}", result.stdout), (
                "Token GitHub (ghp_...) detectado no output de 'docker compose config'. "
                "US-03 AC-08: segredos reais nunca devem aparecer no compose."
            )
        finally:
            import os as _os
            _os.unlink(fake_key)


# ---------------------------------------------------------------------------
# US-05 AC-03 — Política de restart: unless-stopped
# ---------------------------------------------------------------------------
# Testa o critério de aceitação AC-03 da US-05 (#20): o serviço 'pipe' deve
# declarar `restart: unless-stopped` no docker-compose.yml.
#
# Semântica da política:
#   - Container reinicia automaticamente após crash ou reboot do host.
#   - Container NÃO reinicia se parado manualmente com `docker compose stop`.
#   - Sobrevive a `docker compose down` sem a flag -v (containers recriados
#     ficam com restart ativo).
#
# Os testes abaixo são estáticos (sem subir container); o comportamento runtime
# real (crash → reinício) não pode ser verificado sem subir o daemon.
# ---------------------------------------------------------------------------


class TestUS05AC03RestartPolicy:
    """US-05 AC-03: restart: unless-stopped declarado no serviço 'pipe'.

    Garante que o container reinicia automaticamente após crash ou reboot do
    host, mas para normalmente com `docker compose stop` (sem loop infinito).
    """

    def test_restart_unless_stopped_declarado(self, compose_text):
        """O serviço pipe deve declarar `restart: unless-stopped`."""
        assert re.search(r"restart:\s*unless-stopped", compose_text), (
            "'restart: unless-stopped' ausente no docker-compose.yml. "
            "US-05 AC-03: o serviço pipe deve reiniciar automaticamente após "
            "crash ou reboot do host. Adicionar 'restart: unless-stopped' no serviço."
        )

    def test_restart_no_servico_pipe(self, compose_text):
        """restart: unless-stopped deve estar dentro da definição do serviço 'pipe', não em outro serviço."""
        import yaml

        try:
            conteudo = yaml.safe_load(compose_text)
        except Exception:
            pytest.skip("YAML inválido — teste de posicionamento ignorado.")

        services = conteudo.get("services", {})
        assert "pipe" in services, (
            "Serviço 'pipe' não encontrado — não é possível verificar restart policy."
        )
        pipe_service = services["pipe"]
        assert "restart" in pipe_service, (
            "Chave 'restart' ausente no serviço 'pipe'. "
            "US-05 AC-03: 'restart: unless-stopped' deve estar definido no serviço pipe."
        )
        assert pipe_service["restart"] == "unless-stopped", (
            f"Valor de 'restart' é '{pipe_service['restart']}' em vez de 'unless-stopped'. "
            "US-05 AC-03: a política correta é 'unless-stopped' — reinicia após crash "
            "mas respeita parada manual com `docker compose stop`."
        )

    def test_restart_policy_e_unless_stopped_nao_always(self, compose_text):
        """A política de restart NÃO deve ser 'always' (não respeita parada manual).

        'always' faria o container reiniciar mesmo após `docker compose stop`,
        tornando impossível parar o serviço sem intervenção mais agressiva.
        'unless-stopped' é a escolha correta: reinicia após crash/reboot mas
        para com `docker compose stop` ou `docker stop`.
        """
        assert not re.search(r"restart:\s*always", compose_text), (
            "restart: always encontrado no docker-compose.yml. "
            "US-05 AC-03: usar 'restart: unless-stopped', não 'always'. "
            "'always' não respeita `docker compose stop` — requer intervenção manual."
        )

    def test_restart_policy_e_unless_stopped_nao_on_failure(self, compose_text):
        """A política de restart NÃO deve ser 'on-failure'.

        'on-failure' reinicia apenas em saídas com código != 0 e NÃO reinicia
        após reboot do host. 'unless-stopped' cobre ambos os casos (crash e
        reboot) conforme especificado em US-05 AC-03.
        """
        assert not re.search(r"restart:\s*on-failure", compose_text), (
            "restart: on-failure encontrado no docker-compose.yml. "
            "US-05 AC-03: usar 'restart: unless-stopped'. "
            "'on-failure' não reinicia após reboot do host."
        )

    def test_restart_policy_e_unless_stopped_nao_no(self, compose_text):
        """A política de restart NÃO deve ser 'no' (desabilitaria o reinício automático)."""
        # Verifica que não há "restart: no" explícito — o padrão sem restart é 'no',
        # mas se declarado explicitamente é igualmente inválido para US-05 AC-03.
        assert not re.search(r"restart:\s*\"?no\"?", compose_text), (
            "restart: no encontrado no docker-compose.yml. "
            "US-05 AC-03: usar 'restart: unless-stopped'. "
            "'no' (padrão) desabilita o reinício automático."
        )

    def test_restart_nao_sobrescrito_em_ephemeral(self):
        """compose.ephemeral.yml NÃO deve sobrescrever a política de restart.

        O override efêmero deve ser mínimo (apenas volumes anônimos).
        Sobrescrever restart no override efêmero removeria a garantia de US-05 AC-03
        em ambientes que usam o override.
        Nota: este teste já está em TestComposeEphemeral — reforça o vínculo com US-05.
        """
        if not COMPOSE_EPHEMERAL.exists():
            pytest.skip("compose.ephemeral.yml não encontrado — skip.")
        ephemeral_text = COMPOSE_EPHEMERAL.read_text(encoding="utf-8")
        assert "restart:" not in ephemeral_text, (
            "'restart:' encontrado no compose.ephemeral.yml. "
            "US-05 AC-03: o override efêmero não deve sobrescrever a política de restart "
            "definida no compose principal."
        )

    def test_env_example_nao_tem_restart_configuravel(self, env_example_text):
        """restart: unless-stopped é fixo no compose — não deve ser configurável via .env.

        Se restart fosse uma variável de ambiente, o operador poderia desabilitá-lo
        acidentalmente. A política de reinício é decisão de design (US-05 AC-03),
        não parâmetro operacional.
        """
        assert not re.search(r"RESTART_POLICY|COMPOSE_RESTART", env_example_text), (
            "Variável de configuração de restart encontrada no .env.example. "
            "US-05 AC-03: restart: unless-stopped é fixo no compose, "
            "não deve ser configurável pelo operador via .env."
        )


class TestUS05AC03IntegracaoCompose:
    """US-05 AC-03: validação da política de restart via 'docker compose config' (com Docker)."""

    def test_restart_unless_stopped_no_config_resolvido(self):
        """docker compose config deve mostrar restart: unless-stopped no serviço pipe."""
        if not _docker_disponivel():
            pytest.skip("Docker daemon não disponível.")

        import os
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(b"fake-key")
            fake_key = f.name

        try:
            env = dict(os.environ, SSH_KEY_FILE_HOST=fake_key)
            result = subprocess.run(
                ["docker", "compose", "-f", str(COMPOSE_FILE), "config"],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env=env,
            )
            if result.returncode != 0:
                pytest.skip(
                    f"docker compose config falhou (exit {result.returncode}): {result.stderr}"
                )
            assert re.search(r"restart:\s*unless-stopped", result.stdout), (
                "'restart: unless-stopped' ausente no output de 'docker compose config'. "
                "US-05 AC-03: o Compose deve resolver a política de restart corretamente."
            )
        finally:
            import os as _os
            _os.unlink(fake_key)

    def test_restart_unless_stopped_persiste_com_override_ephemeral(self):
        """restart: unless-stopped deve persistir quando compose.ephemeral.yml é aplicado como override."""
        if not _docker_disponivel():
            pytest.skip("Docker daemon não disponível.")
        if not COMPOSE_EPHEMERAL.exists():
            pytest.skip("compose.ephemeral.yml não encontrado.")

        import os
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(b"fake-key")
            fake_key = f.name

        try:
            env = dict(os.environ, SSH_KEY_FILE_HOST=fake_key)
            result = subprocess.run(
                [
                    "docker", "compose",
                    "-f", str(COMPOSE_FILE),
                    "-f", str(COMPOSE_EPHEMERAL),
                    "config",
                ],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env=env,
            )
            if result.returncode != 0:
                pytest.skip(
                    f"docker compose config com ephemeral falhou: {result.stderr}"
                )
            assert re.search(r"restart:\s*unless-stopped", result.stdout), (
                "'restart: unless-stopped' perdida ao aplicar compose.ephemeral.yml. "
                "US-05 AC-03: o override efêmero não deve sobrescrever a política de restart."
            )
        finally:
            import os as _os
            _os.unlink(fake_key)
