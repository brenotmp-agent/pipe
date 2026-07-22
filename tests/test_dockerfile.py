"""Testes de validação estática do Dockerfile.

Verificam se o Dockerfile atende os critérios de aceitação das issues:
  - AC-04 da US-05 (#20): PYTHONUNBUFFERED=1 definido
  - AC-05 de US-01 (#16): usuário não-root (pipe, uid 1000)
  - Requisitos de pinagem de versões (pyyaml==6.0.2, gh versão declarada)
  - Entrypoint correto e ausência de segredos no COPY

Estes testes são estáticos (não constroem a imagem) e podem ser executados
sem Docker instalado. Testes que requerem Docker ficam marcados com
@pytest.mark.docker e são ignorados por padrão no CI sem daemon.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"


# ---------------------------------------------------------------------------
# Fixture: conteúdo do Dockerfile
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dockerfile_text():
    assert DOCKERFILE.exists(), "Dockerfile não encontrado na raiz do repositório"
    return DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dockerfile_lines(dockerfile_text):
    return dockerfile_text.splitlines()


# ---------------------------------------------------------------------------
# AC-04 de US-05 — PYTHONUNBUFFERED=1
# ---------------------------------------------------------------------------

class TestPythonUnbuffered:
    """AC-04 da US-05: variável PYTHONUNBUFFERED=1 deve estar definida na imagem."""

    def test_env_pythonunbuffered_declarado(self, dockerfile_text):
        """ENV PYTHONUNBUFFERED=1 deve aparecer explicitamente no Dockerfile."""
        assert "PYTHONUNBUFFERED=1" in dockerfile_text, (
            "AC-04 violado: ENV PYTHONUNBUFFERED=1 ausente no Dockerfile. "
            "Logs em tempo real via 'docker logs' não funcionarão."
        )

    def test_env_pythonunbuffered_usa_instrucao_env(self, dockerfile_lines):
        """A variável deve ser definida via instrução ENV, não via ARG ou RUN export."""
        env_lines = [
            l.strip() for l in dockerfile_lines
            if re.match(r"^ENV\b", l.strip())
        ]
        combined = " ".join(env_lines)
        assert "PYTHONUNBUFFERED=1" in combined, (
            "PYTHONUNBUFFERED=1 não está definido por instrução ENV "
            "(pode estar em ARG ou comentário, o que não persiste na imagem)."
        )

    def test_pythonunbuffered_nao_e_zero(self, dockerfile_text):
        """PYTHONUNBUFFERED não deve ser definido com valor 0 (desabilitaria o buffer)."""
        assert "PYTHONUNBUFFERED=0" not in dockerfile_text, (
            "PYTHONUNBUFFERED=0 desabilita o modo sem buffer — contradiz AC-04."
        )


# ---------------------------------------------------------------------------
# AC-05 de US-01 — usuário não-root (pipe, uid 1000)
# ---------------------------------------------------------------------------

class TestNonRootUser:
    """AC-05 de US-01: container deve rodar como usuário não-root 'pipe' (uid 1000)."""

    def test_useradd_cria_usuario_pipe(self, dockerfile_text):
        """useradd deve criar o usuário 'pipe'."""
        assert re.search(r"useradd\b.*\bpipe\b", dockerfile_text), (
            "AC-05 violado: instrução 'useradd ... pipe' não encontrada. "
            "Container rodará como root."
        )

    def test_uid_1000_declarado(self, dockerfile_text):
        """Usuário pipe deve ser criado com uid 1000 (convencional para não-root)."""
        assert re.search(r"useradd\b.*--uid\s+1000", dockerfile_text), (
            "uid 1000 não declarado no useradd. ADR-05 exige uid determinístico "
            "para compatibilidade com volumes em docker-compose."
        )

    def test_create_home_presente(self, dockerfile_text):
        """--create-home necessário para _setup_ssh escrever ~/.ssh e kiro-cli gravar sessão."""
        assert re.search(r"useradd\b.*--create-home", dockerfile_text), (
            "--create-home ausente: _setup_ssh falha ao tentar escrever em ~/.ssh."
        )

    def test_instrucao_user_pipe(self, dockerfile_lines):
        """Instrução USER pipe deve aparecer para mudar o contexto de execução."""
        user_lines = [
            l.strip() for l in dockerfile_lines
            if re.match(r"^USER\b", l.strip())
        ]
        assert any("pipe" in l for l in user_lines), (
            "AC-05 violado: instrução 'USER pipe' ausente. "
            "Imagem executará como root mesmo que o usuário tenha sido criado."
        )

    def test_instrucao_user_pipe_antes_do_entrypoint(self, dockerfile_lines):
        """USER pipe deve aparecer antes do ENTRYPOINT."""
        user_idx = None
        entry_idx = None
        for i, line in enumerate(dockerfile_lines):
            stripped = line.strip()
            if re.match(r"^USER\s+pipe\b", stripped) and user_idx is None:
                user_idx = i
            if re.match(r"^ENTRYPOINT\b", stripped) and entry_idx is None:
                entry_idx = i
        assert user_idx is not None, "Instrução 'USER pipe' não encontrada."
        assert entry_idx is not None, "Instrução ENTRYPOINT não encontrada."
        assert user_idx < entry_idx, (
            f"USER pipe (linha {user_idx+1}) aparece após ENTRYPOINT (linha {entry_idx+1}). "
            "O container rodará como root."
        )

    def test_nenhum_user_root_apos_user_pipe(self, dockerfile_lines):
        """Não deve haver 'USER root' após 'USER pipe' (reescalonamento indevido)."""
        pipe_seen = False
        for line in dockerfile_lines:
            stripped = line.strip()
            if re.match(r"^USER\s+pipe\b", stripped):
                pipe_seen = True
            if pipe_seen and re.match(r"^USER\s+(root|0)\b", stripped):
                pytest.fail(
                    "USER root encontrado após USER pipe: "
                    "imagem voltará a rodar como root."
                )


# ---------------------------------------------------------------------------
# Pinagem de versões
# ---------------------------------------------------------------------------

class TestVersoesPinadas:
    """Dependências críticas devem ter versões explicitamente pinadas."""

    def test_pyyaml_versao_pinada(self, dockerfile_text):
        """pyyaml deve ser instalado com versão exata (pyyaml==6.0.2)."""
        assert re.search(r"pyyaml==\d+\.\d+", dockerfile_text, re.IGNORECASE), (
            "pyyaml instalado sem versão pinada. "
            "Builds futuros podem quebrar com versão incompatível."
        )

    def test_pyyaml_versao_especifica_6_0_2(self, dockerfile_text):
        """Versão de pyyaml deve ser 6.0.2 conforme especificado na issue."""
        assert "pyyaml==6.0.2" in dockerfile_text.lower(), (
            "Versão de pyyaml diferente de 6.0.2. "
            "Issue especifica esta versão como baseline verificado."
        )

    def test_gh_cli_versao_declarada(self, dockerfile_text):
        """GitHub CLI deve ter versão declarada (via ARG GH_VERSION ou apt install gh=X.Y.Z)."""
        versao_apt = re.search(r"gh=\d+\.\d+\.\d+", dockerfile_text)
        versao_arg = re.search(r"GH_VERSION=\d+\.\d+\.\d+", dockerfile_text)
        assert versao_apt or versao_arg, (
            "Versão do GitHub CLI não encontrada. "
            "Declare gh=X.Y.Z no apt install ou ARG GH_VERSION=X.Y.Z."
        )

    def test_gh_cli_nao_usa_latest(self, dockerfile_text):
        """GitHub CLI não deve ser instalado sem versão ('gh' solto ou 'latest')."""
        # Detecta padrão de apt sem versão: gh\n ou gh \\ ou gh && — sem = seguido de dígito
        # Somente dentro de apt-get install (contexto relevante)
        apts = re.findall(
            r"apt-get install[^\n]+(?:\\\n[^\n]+)*",
            dockerfile_text,
        )
        for bloco in apts:
            # Se 'gh' aparece no bloco mas sem '=<versão>' imediato
            if re.search(r"\bgh\b(?!=\d)", bloco):
                pytest.fail(
                    "GitHub CLI instalado via apt sem versão pinada. "
                    "Use 'gh=X.Y.Z' para garantir reproducibilidade."
                )


# ---------------------------------------------------------------------------
# Imagem base e entrypoint
# ---------------------------------------------------------------------------

class TestEstruturaDockerfile:
    """Estrutura geral: imagem base, entrypoint e ausência de segredos."""

    def test_base_python_3_12(self, dockerfile_text):
        """Imagem base deve ser python:3.12-slim."""
        assert re.search(r"FROM\s+python:3\.12", dockerfile_text), (
            "Imagem base não é python:3.12. "
            "Requisito de US-01: Python 3.12+."
        )

    def test_entrypoint_python_m_src(self, dockerfile_text):
        """ENTRYPOINT deve executar 'python -m src'."""
        assert re.search(
            r'ENTRYPOINT\s+\["python",\s*"-m",\s*"src"\]',
            dockerfile_text,
        ), (
            "ENTRYPOINT não é [\"python\", \"-m\", \"src\"]. "
            "O container não iniciará a esteira corretamente."
        )

    def test_nao_copia_pipe_yml(self, dockerfile_text):
        """pipe.yml NÃO deve ser copiado para a imagem (entra por volume em runtime)."""
        # COPY que mencione pipe.yml (exclui comentários)
        linhas_copy = [
            l for l in dockerfile_text.splitlines()
            if re.match(r"^\s*COPY\b", l) and "pipe.yml" in l
        ]
        assert not linhas_copy, (
            "pipe.yml está sendo copiado para a imagem. "
            "RF-05: deve entrar por volume em runtime para evitar segredos embarcados."
        )

    def test_nao_copia_contexts(self, dockerfile_text):
        """contexts/ NÃO deve ser copiado para a imagem."""
        linhas_copy = [
            l for l in dockerfile_text.splitlines()
            if re.match(r"^\s*COPY\b", l) and "contexts" in l
        ]
        assert not linhas_copy, (
            "contexts/ está sendo copiado para a imagem. "
            "Contextos contêm configuração de agentes e devem entrar por volume."
        )

    def test_nao_copia_readme_ou_context_md(self, dockerfile_text):
        """README.md e CONTEXT.md NÃO devem ser copiados (fora de escopo)."""
        for artefato in ("README.md", "CONTEXT.md"):
            linhas_copy = [
                l for l in dockerfile_text.splitlines()
                if re.match(r"^\s*COPY\b", l) and artefato in l
            ]
            assert not linhas_copy, (
                f"{artefato} está sendo copiado para a imagem. "
                "Apenas src/ deve ser copiado (RF-01)."
            )

    def test_copia_src_com_chown_pipe(self, dockerfile_text):
        """src/ deve ser copiado com --chown=pipe:pipe."""
        assert re.search(
            r"COPY\s+--chown=pipe:pipe\s+src/",
            dockerfile_text,
        ), (
            "src/ não está sendo copiado com --chown=pipe:pipe. "
            "Usuário pipe não terá permissão de leitura dos próprios arquivos."
        )

    def test_openssh_client_correto(self, dockerfile_text):
        """Pacote de SSH deve ser 'openssh-client', não 'ssh'."""
        # Verifica que openssh-client está presente
        assert "openssh-client" in dockerfile_text, (
            "'openssh-client' ausente. Operações SSH falharão."
        )
        # Verifica que não há instalação do pacote errado 'ssh' solto
        # (aceita 'openssh-client' mas rejeita ' ssh ' ou '\tssh\t' como pacote isolado)
        linhas_apt = [
            l for l in dockerfile_text.splitlines()
            if "apt-get install" in l or (
                l.strip().startswith("ssh") and not "openssh" in l
            )
        ]
        for linha in linhas_apt:
            if re.search(r"\bssh\b(?!-)", linha) and "openssh" not in linha:
                pytest.fail(
                    f"Pacote 'ssh' (nome incorreto) encontrado: {linha.strip()!r}. "
                    "O nome correto é 'openssh-client'."
                )

    def test_workdir_app(self, dockerfile_text):
        """/app deve ser o WORKDIR de execução."""
        assert re.search(r"^WORKDIR\s+/app", dockerfile_text, re.MULTILINE), (
            "WORKDIR /app não encontrado. "
            "Caminho de trabalho do container não está configurado."
        )


# ---------------------------------------------------------------------------
# Testes de integração Docker (requerem daemon — skippados se indisponível)
# ---------------------------------------------------------------------------

def _docker_disponivel():
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


DOCKER_SKIP = pytest.mark.skipif(
    not _docker_disponivel(),
    reason="Docker daemon não disponível — teste de integração ignorado",
)


@DOCKER_SKIP
class TestDockerIntegracao:
    """Testes que requerem Docker daemon e a imagem construída.

    Para executar localmente:
        docker build -t pipe-esteira-test .
        pytest tests/test_dockerfile.py -k docker -v

    Esses testes são marcados com @pytest.mark.docker e podem ser
    executados em CI com:
        pytest tests/test_dockerfile.py -m docker
    """

    IMAGE = "pipe-esteira-test"

    @pytest.fixture(scope="class", autouse=True)
    def build_image(self):
        """Constrói a imagem antes dos testes de integração."""
        result = subprocess.run(
            ["docker", "build", "-t", self.IMAGE, str(REPO_ROOT)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.skip(f"Build falhou — integrações ignoradas:\n{result.stderr}")

    def _run(self, cmd, image=None):
        full_cmd = ["docker", "run", "--rm", image or self.IMAGE] + cmd
        return subprocess.run(full_cmd, capture_output=True, text=True)

    def test_python_version_312(self):
        """python --version deve reportar 3.12.x."""
        r = self._run(["python", "--version"])
        assert r.returncode == 0
        assert "3.12" in r.stdout + r.stderr

    def test_git_disponivel(self):
        """git deve estar no PATH."""
        r = self._run(["git", "--version"])
        assert r.returncode == 0

    def test_gh_disponivel(self):
        """gh deve estar no PATH."""
        r = self._run(["gh", "--version"])
        assert r.returncode == 0

    def test_usuario_nao_root(self):
        """Container deve executar como uid 1000 (pipe), não root."""
        r = self._run(["id"])
        assert r.returncode == 0
        assert "uid=1000" in r.stdout, (
            f"Container rodando como usuário inesperado: {r.stdout.strip()}"
        )
        assert "pipe" in r.stdout

    def test_pythonunbuffered_no_env(self):
        """PYTHONUNBUFFERED=1 deve estar no ambiente do container."""
        r = self._run(["env"])
        assert r.returncode == 0
        assert "PYTHONUNBUFFERED=1" in r.stdout, (
            "AC-04 violado: PYTHONUNBUFFERED=1 não está no ambiente do container."
        )

    def test_pipe_yml_ausente_na_imagem(self):
        """pipe.yml não deve existir dentro da imagem."""
        r = self._run(["test", "-f", "/app/pipe.yml"])
        assert r.returncode != 0, (
            "pipe.yml encontrado em /app — segredos embutidos na imagem (viola RF-05)."
        )

    def test_contexts_ausente_na_imagem(self):
        """contexts/ não deve existir dentro da imagem."""
        r = self._run(["test", "-d", "/app/contexts"])
        assert r.returncode != 0, (
            "contexts/ encontrado em /app — configuração de agentes não deve ser embarcada."
        )

    def test_sem_variaveis_exit_code_nao_zero(self):
        """Container sem variáveis de ambiente deve falhar (check_config) com exit-code != 0."""
        r = self._run([])
        assert r.returncode != 0, (
            "AC-07: container sem variáveis de ambiente retornou exit-code 0. "
            "check_config deve falhar antecipadamente."
        )

    def test_src_presente_na_imagem(self):
        """src/ deve existir em /app/src dentro da imagem."""
        r = self._run(["test", "-d", "/app/src"])
        assert r.returncode == 0, "/app/src ausente na imagem."
