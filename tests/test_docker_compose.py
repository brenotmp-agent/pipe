"""Testes de validação estática do docker-compose.yml e arquivos relacionados.

Verificam se os artefatos de configuração Docker atendem os critérios de
aceitação da US-04 (#46) / contrato D-05:

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
COMPOSE_EPHEMERAL = REPO_ROOT / "compose.ephemeral.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
GITIGNORE = REPO_ROOT / ".gitignore"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def compose_text():
    assert COMPOSE_FILE.exists(), (
        "docker-compose.yml não encontrado na raiz do repositório. "
        "US-04 exige o arquivo com os três bind mounts de estado."
    )
    return COMPOSE_FILE.read_text(encoding="utf-8")


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


class TestBindMountsEstado:
    """AC-04: bind mounts para .pipe/, repo/ e logs/ — não named volumes (ADR-04)."""

    def test_bind_mount_pipe_state_presente(self, compose_text):
        """docker-compose.yml deve conter bind mount para /app/.pipe."""
        assert re.search(
            r"PIPE_STATE_DIR.*:/app/\.pipe",
            compose_text,
        ), (
            "Bind mount para /app/.pipe ausente. "
            "US-04 AC-04: ${PIPE_STATE_DIR:-./.pipe}:/app/.pipe obrigatório."
        )

    def test_bind_mount_pipe_repo_presente(self, compose_text):
        """docker-compose.yml deve conter bind mount para /app/repo."""
        assert re.search(
            r"PIPE_REPO_DIR.*:/app/repo",
            compose_text,
        ), (
            "Bind mount para /app/repo ausente. "
            "US-04 AC-04: ${PIPE_REPO_DIR:-./repo}:/app/repo obrigatório."
        )

    def test_bind_mount_pipe_logs_presente(self, compose_text):
        """docker-compose.yml deve conter bind mount para /app/logs."""
        assert re.search(
            r"PIPE_LOGS_DIR.*:/app/logs",
            compose_text,
        ), (
            "Bind mount para /app/logs ausente. "
            "US-04 AC-04: ${PIPE_LOGS_DIR:-./logs}:/app/logs obrigatório."
        )

    def test_named_volume_pipe_state_ausente(self, compose_text):
        """Named volume 'pipe_state' não deve existir (substituído por bind mount — ADR-04)."""
        assert "pipe_state:" not in compose_text, (
            "Named volume 'pipe_state' encontrado. "
            "ADR-04: usar bind mount ${PIPE_STATE_DIR:-./.pipe}:/app/.pipe."
        )

    def test_named_volume_pipe_repos_ausente(self, compose_text):
        """Named volume 'pipe_repos' não deve existir (substituído por bind mount — ADR-04)."""
        assert "pipe_repos:" not in compose_text, (
            "Named volume 'pipe_repos' encontrado. "
            "ADR-04: usar bind mount ${PIPE_REPO_DIR:-./repo}:/app/repo."
        )

    def test_named_volume_pipe_logs_ausente(self, compose_text):
        """Named volume 'pipe_logs' não deve existir (substituído por bind mount — ADR-04)."""
        assert "pipe_logs:" not in compose_text, (
            "Named volume 'pipe_logs' encontrado. "
            "ADR-04: usar bind mount ${PIPE_LOGS_DIR:-./logs}:/app/logs."
        )

    def test_secao_volumes_toplevel_sem_entradas_de_estado(self, compose_text):
        """Seção 'volumes:' top-level não deve ter entradas para pipe_state/pipe_repos/pipe_logs."""
        # Encontra seção volumes: top-level (nível 0, não indentada)
        top_level_volumes = re.findall(
            r"^volumes:\s*\n((?:  .*\n?)*)",
            compose_text,
            re.MULTILINE,
        )
        if top_level_volumes:
            bloco = top_level_volumes[-1]
            for nome in ("pipe_state", "pipe_repos", "pipe_logs"):
                assert nome not in bloco, (
                    f"Named volume '{nome}' encontrado na seção volumes: top-level. "
                    "ADR-04: remover entradas de named volumes de estado."
                )


# ---------------------------------------------------------------------------
# US-04 AC-03 — Defaults inline (funcionamento sem .env)
# ---------------------------------------------------------------------------


class TestDefaultsInline:
    """AC-03: defaults inline garantem funcionamento sem .env (H-2 — sem efêmero por engano)."""

    def test_pipe_state_default_inline(self, compose_text):
        """`${PIPE_STATE_DIR:-./.pipe}` garante default sem .env."""
        assert re.search(
            r"\$\{PIPE_STATE_DIR:-\./.pipe\}",
            compose_text,
        ), (
            "Default inline para PIPE_STATE_DIR ausente. "
            "US-04 AC-03: use ${PIPE_STATE_DIR:-./.pipe} para funcionar sem .env."
        )

    def test_pipe_repo_default_inline(self, compose_text):
        """`${PIPE_REPO_DIR:-./repo}` garante default sem .env."""
        assert re.search(
            r"\$\{PIPE_REPO_DIR:-\./repo\}",
            compose_text,
        ), (
            "Default inline para PIPE_REPO_DIR ausente. "
            "US-04 AC-03: use ${PIPE_REPO_DIR:-./repo} para funcionar sem .env."
        )

    def test_pipe_logs_default_inline(self, compose_text):
        """`${PIPE_LOGS_DIR:-./logs}` garante default sem .env."""
        assert re.search(
            r"\$\{PIPE_LOGS_DIR:-\./logs\}",
            compose_text,
        ), (
            "Default inline para PIPE_LOGS_DIR ausente. "
            "US-04 AC-03: use ${PIPE_LOGS_DIR:-./logs} para funcionar sem .env."
        )


# ---------------------------------------------------------------------------
# US-04 AC-06 — D-05: nunca montar /app inteiro
# ---------------------------------------------------------------------------


class TestNuncaMontarAppInteiro:
    """AC-06 / D-05: bind mounts de estado mapeiam subdiretórios, nunca /app inteiro."""

    def test_sem_bind_mount_app_inteiro(self, compose_text):
        """Nenhum volume deve apontar para /app como destino direto (D-05)."""
        # Padrões que indicariam montagem de /app inteiro: :/app ou :/app:
        matches = re.findall(r":\s*/app\s*(?::|$|\n)", compose_text, re.MULTILINE)
        # Remove linhas comentadas
        perigosas = [m for m in matches if not m.strip().startswith("#")]
        assert not perigosas, (
            "Volume montando /app inteiro detectado. "
            "D-05: montar /app sobrescreve o código da imagem. "
            "Use /app/.pipe, /app/repo ou /app/logs."
        )

    def test_volumes_estado_usam_subpaths(self, compose_text):
        """Os três bind mounts de estado mapeiam subdiretórios de /app."""
        for subpath in ("/app/.pipe", "/app/repo", "/app/logs"):
            assert subpath in compose_text, (
                f"Subpath de estado '{subpath}' não encontrado no compose. "
                f"D-05: bind mount deve apontar para '{subpath}', não para /app."
            )


# ---------------------------------------------------------------------------
# Volumes de configuração e credenciais — não devem ter sido removidos
# ---------------------------------------------------------------------------


class TestVolumesExistentesPreservados:
    """Os volumes de config/credenciais já existentes não devem ter sido removidos."""

    def test_pipe_yml_volume_presente(self, compose_text):
        """pipe.yml montado como volume read-only deve ser preservado (US-03)."""
        assert re.search(r"pipe\.yml.*:/app/pipe\.yml.*:ro", compose_text), (
            "Volume de pipe.yml ausente. "
            "Esta task acrescenta volumes de estado; os de config/credenciais devem ser mantidos."
        )

    def test_contexts_volume_presente(self, compose_text):
        """contexts/ montado como volume deve ser preservado (US-03)."""
        assert re.search(r"contexts.*:/app/contexts", compose_text), (
            "Volume de contexts/ ausente. "
            "Esta task acrescenta volumes de estado; os de config/credenciais devem ser mantidos."
        )

    def test_ssh_key_volume_presente(self, compose_text):
        """Chave SSH montada como volume read-only deve ser preservada (US-02)."""
        assert re.search(r"SSH_KEY_FILE.*:/root/\.ssh/id_ed25519.*:ro", compose_text), (
            "Volume da chave SSH ausente. "
            "Esta task acrescenta volumes de estado; os de credenciais devem ser mantidos."
        )

    def test_gh_config_volume_presente(self, compose_text):
        """Configuração do gh CLI montada como read-only deve ser preservada (US-02)."""
        assert re.search(r"GH_CONFIG_DIR.*:/root/\.config/gh.*:ro", compose_text), (
            "Volume de configuração do gh ausente. "
            "Esta task acrescenta volumes de estado; os de credenciais devem ser mantidos."
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
# Ordem dos volumes — estado antes de config/credenciais (preferência de leitura)
# ---------------------------------------------------------------------------


class TestOrdemVolumes:
    """Os volumes de estado (D-05) devem aparecer antes dos de config/credenciais no compose."""

    def test_bind_mounts_estado_antes_de_pipe_yml(self, compose_text):
        """Volumes de estado devem aparecer antes do volume de pipe.yml."""
        state_match = re.search(r"PIPE_STATE_DIR", compose_text)
        config_match = re.search(r"pipe\.yml.*:/app/pipe\.yml", compose_text)
        if state_match and config_match:
            assert state_match.start() < config_match.start(), (
                "Volumes de estado aparecem DEPOIS de pipe.yml. "
                "A issue especifica: volumes de estado ANTES dos de config/segredos."
            )

    def test_bind_mounts_estado_antes_de_contexts(self, compose_text):
        """Volumes de estado devem aparecer antes do volume de contexts/."""
        state_match = re.search(r"PIPE_STATE_DIR", compose_text)
        contexts_match = re.search(r"contexts.*:/app/contexts", compose_text)
        if state_match and contexts_match:
            assert state_match.start() < contexts_match.start(), (
                "Volumes de estado aparecem DEPOIS de contexts/. "
                "A issue especifica: volumes de estado ANTES dos de config/segredos."
            )

    def test_bind_mounts_estado_antes_de_ssh_key(self, compose_text):
        """Volumes de estado devem aparecer antes do volume da chave SSH."""
        state_match = re.search(r"PIPE_STATE_DIR", compose_text)
        ssh_match = re.search(r"SSH_KEY_FILE.*:/root/\.ssh/id_ed25519", compose_text)
        if state_match and ssh_match:
            assert state_match.start() < ssh_match.start(), (
                "Volumes de estado aparecem DEPOIS da chave SSH. "
                "A issue especifica: volumes de estado ANTES dos de config/segredos."
            )

    def test_bind_mounts_estado_antes_de_gh_config(self, compose_text):
        """Volumes de estado devem aparecer antes do volume do gh config."""
        state_match = re.search(r"PIPE_STATE_DIR", compose_text)
        gh_match = re.search(r"GH_CONFIG_DIR.*:/root/\.config/gh", compose_text)
        if state_match and gh_match:
            assert state_match.start() < gh_match.start(), (
                "Volumes de estado aparecem DEPOIS do gh config. "
                "A issue especifica: volumes de estado ANTES dos de config/segredos."
            )

    def test_tres_bind_mounts_de_estado_consecutivos(self, compose_text):
        """Os três bind mounts de estado devem aparecer próximos (bloco coeso de estado)."""
        pipe_match = re.search(r"PIPE_STATE_DIR", compose_text)
        repo_match = re.search(r"PIPE_REPO_DIR", compose_text)
        logs_match = re.search(r"PIPE_LOGS_DIR", compose_text)
        if pipe_match and repo_match and logs_match:
            positions = sorted([pipe_match.start(), repo_match.start(), logs_match.start()])
            # Os três devem estar dentro de 800 caracteres entre si (bloco coeso)
            assert positions[2] - positions[0] < 800, (
                "Os três bind mounts de estado (PIPE_STATE_DIR, PIPE_REPO_DIR, PIPE_LOGS_DIR) "
                "estão espalhados no compose. Devem estar num bloco coeso, "
                "separados dos volumes de config/credenciais."
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
    """Testes que requerem Docker Compose instalado.

    Validam os critérios de aceitação que só podem ser verificados em runtime.

    Para executar localmente:
        docker compose config          # deve validar sem erro com e sem .env
        pytest tests/test_docker_compose.py::TestDockerComposeIntegracao -v
    """

    def test_compose_config_valida_sem_env(self):
        """US-04 AC-03: 'docker compose config' deve validar sem erro mesmo sem .env."""
        import os

        env_sem_estado = {k: v for k, v in os.environ.items()
                         if k not in ("PIPE_STATE_DIR", "PIPE_REPO_DIR", "PIPE_LOGS_DIR")}
        result = subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "config"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env_sem_estado,
        )
        assert result.returncode == 0, (
            f"'docker compose config' falhou sem .env (exit {result.returncode}). "
            f"Stderr: {result.stderr}\n"
            "US-04 AC-03: defaults inline devem garantir funcionamento sem .env."
        )

    def test_compose_config_valida_com_env(self):
        """US-04 AC-03: 'docker compose config' deve validar sem erro com variáveis definidas."""
        import os

        env_com_estado = dict(os.environ, **{
            "PIPE_STATE_DIR": "/tmp/pipe_state_test",
            "PIPE_REPO_DIR": "/tmp/pipe_repo_test",
            "PIPE_LOGS_DIR": "/tmp/pipe_logs_test",
        })
        result = subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "config"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env_com_estado,
        )
        assert result.returncode == 0, (
            f"'docker compose config' falhou com variáveis definidas (exit {result.returncode}). "
            f"Stderr: {result.stderr}"
        )

    def test_compose_config_usa_defaults_inline(self):
        """Os defaults inline aparecem no output de 'docker compose config' quando sem .env."""
        import os

        env_sem_estado = {k: v for k, v in os.environ.items()
                         if k not in ("PIPE_STATE_DIR", "PIPE_REPO_DIR", "PIPE_LOGS_DIR")}
        result = subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "config"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env_sem_estado,
        )
        if result.returncode != 0:
            pytest.skip("docker compose config falhou — testar defaults não é possível.")

        output = result.stdout
        # Os defaults inline devem resultar em .pipe, ./repo, ./logs na config resolvida
        assert ".pipe" in output or "/app/.pipe" in output, (
            "Default ./.pipe não aparece no output de 'docker compose config'. "
            "Verifique o default inline: ${PIPE_STATE_DIR:-./.pipe}."
        )

    def test_ephemeral_compose_config_valida(self):
        """compose.ephemeral.yml deve ser aceito por 'docker compose config' como override."""
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
        """US-04 AC-01 (configuração): 'docker compose config' resolve variáveis de estado customizadas.

        Valida que ao definir PIPE_STATE_DIR, PIPE_REPO_DIR e PIPE_LOGS_DIR com
        caminhos customizados, o Compose aceita a configuração sem erros e expande
        corretamente as variáveis no config resolvido.

        Nota: este teste valida a configuração de bind mounts (pré-condição do AC-01),
        não o ciclo runtime de down/up com container em execução. A garantia de
        persistência real (AC-01 completo) requer build da imagem e é verificada
        manualmente conforme documentado em doc/stories/rodar-no-docker/arquitetura.md §8.
        """
        import os

        state_dir = tmp_path / "pipe_state"
        repo_dir = tmp_path / "pipe_repo"
        logs_dir = tmp_path / "pipe_logs"
        state_dir.mkdir()
        repo_dir.mkdir()
        logs_dir.mkdir()

        env_com_dirs = dict(os.environ, **{
            "PIPE_STATE_DIR": str(state_dir),
            "PIPE_REPO_DIR": str(repo_dir),
            "PIPE_LOGS_DIR": str(logs_dir),
            "GH_TOKEN": "ghp_placeholder_for_test",
            "SSH_KEY_FILE": str(Path.home() / ".ssh" / "id_ed25519"),
            "GH_CONFIG_DIR": str(Path.home() / ".config" / "gh"),
        })

        # Verifica que `docker compose config` resolve os paths corretamente
        # com as variáveis de estado apontando para os diretórios customizados
        result = subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "config"],
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
            "PIPE_STATE_DIR não está sendo expandido corretamente pelo Compose."
        )

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
