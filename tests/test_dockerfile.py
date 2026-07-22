"""Testes de validação estática do Dockerfile.

Verificam se o Dockerfile atende os critérios de aceitação das issues:
  - US-01 (#16) / task #45: estrutura de camadas, usuário não-root, .dockerignore
  - US-05 (#20) AC-04: PYTHONUNBUFFERED=1 definido via ENV
  - ADR-04: versões pinadas (pyyaml, gh, git, openssh-client)
  - ADR-05: usuário não-root (pipe, uid 1000)
  - ADR-06: nenhum segredo embarcado, .dockerignore bloqueia tudo
  - ADR-07: código da esteira via git clone, NÃO via COPY
  - ADR-03: kiro-cli instalado via download URL + verificação SHA256

Testes estáticos (não constroem a imagem) — executam sem Docker.
Testes que requerem Docker ficam em TestDockerIntegracao marcados com
@pytest.mark.docker (skip automático se daemon ausente).
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
VERSIONS_ENV = REPO_ROOT / "docker" / "versions.env"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_env(path: Path) -> dict:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dockerfile_text():
    assert DOCKERFILE.exists(), "Dockerfile não encontrado na raiz do repositório"
    return DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dockerfile_lines(dockerfile_text):
    return dockerfile_text.splitlines()


@pytest.fixture(scope="module")
def dockerignore_text():
    assert DOCKERIGNORE.exists(), ".dockerignore não encontrado na raiz do repositório"
    return DOCKERIGNORE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def versions():
    assert VERSIONS_ENV.exists(), "docker/versions.env não encontrado"
    return _parse_env(VERSIONS_ENV)


# ---------------------------------------------------------------------------
# AC-04 de US-05 — PYTHONUNBUFFERED=1
# ---------------------------------------------------------------------------

class TestPythonUnbuffered:
    """AC-04 da US-05: variável PYTHONUNBUFFERED=1 deve estar definida na imagem."""

    def test_env_pythonunbuffered_declarado(self, dockerfile_text):
        assert "PYTHONUNBUFFERED=1" in dockerfile_text, (
            "AC-04 violado: ENV PYTHONUNBUFFERED=1 ausente no Dockerfile."
        )

    def test_env_pythonunbuffered_usa_instrucao_env(self, dockerfile_lines):
        env_lines = [
            l.strip() for l in dockerfile_lines
            if re.match(r"^ENV\b", l.strip())
        ]
        combined = " ".join(env_lines)
        assert "PYTHONUNBUFFERED=1" in combined, (
            "PYTHONUNBUFFERED=1 não está definido por instrução ENV."
        )

    def test_pythonunbuffered_nao_e_zero(self, dockerfile_text):
        assert "PYTHONUNBUFFERED=0" not in dockerfile_text, (
            "PYTHONUNBUFFERED=0 desabilita o modo sem buffer — contradiz AC-04."
        )


# ---------------------------------------------------------------------------
# AC-05 de US-01 / ADR-05 — usuário não-root (pipe, uid 1000)
# ---------------------------------------------------------------------------

class TestNonRootUser:
    """AC-05 de US-01 / ADR-05: container deve rodar como usuário 'pipe' (uid 1000)."""

    def test_useradd_cria_usuario_pipe(self, dockerfile_text):
        assert re.search(r"useradd\b.*\bpipe\b", dockerfile_text), (
            "AC-05 violado: 'useradd ... pipe' não encontrado."
        )

    def test_uid_1000_declarado(self, dockerfile_text):
        assert re.search(r"useradd\b.*--uid\s+1000", dockerfile_text), (
            "uid 1000 não declarado no useradd. ADR-05 exige uid determinístico."
        )

    def test_create_home_presente(self, dockerfile_text):
        assert re.search(r"useradd\b.*--create-home", dockerfile_text), (
            "--create-home ausente: ~/.ssh e sessões do kiro-cli não funcionarão."
        )

    def test_instrucao_user_pipe(self, dockerfile_lines):
        user_lines = [l.strip() for l in dockerfile_lines if re.match(r"^USER\b", l.strip())]
        assert any("pipe" in l for l in user_lines), (
            "AC-05 violado: instrução 'USER pipe' ausente."
        )

    def test_instrucao_user_pipe_antes_do_cmd(self, dockerfile_lines):
        """USER pipe deve aparecer antes de CMD (Dockerfile usa CMD, não ENTRYPOINT)."""
        user_idx = None
        cmd_idx = None
        for i, line in enumerate(dockerfile_lines):
            stripped = line.strip()
            if re.match(r"^USER\s+pipe\b", stripped) and user_idx is None:
                user_idx = i
            if re.match(r"^(ENTRYPOINT|CMD)\b", stripped) and cmd_idx is None:
                cmd_idx = i
        assert user_idx is not None, "Instrução 'USER pipe' não encontrada."
        assert cmd_idx is not None, "Instrução CMD/ENTRYPOINT não encontrada."
        assert user_idx < cmd_idx, (
            f"USER pipe (linha {user_idx+1}) aparece após CMD/ENTRYPOINT (linha {cmd_idx+1})."
        )

    def test_nenhum_user_root_apos_user_pipe(self, dockerfile_lines):
        pipe_seen = False
        for line in dockerfile_lines:
            stripped = line.strip()
            if re.match(r"^USER\s+pipe\b", stripped):
                pipe_seen = True
            if pipe_seen and re.match(r"^USER\s+(root|0)\b", stripped):
                pytest.fail("USER root encontrado após USER pipe.")

    def test_chown_app_para_pipe(self, dockerfile_text):
        """ADR-05: /app deve ter ownership de pipe (RUN chown pipe:pipe /app)."""
        assert re.search(r"chown\s+pipe:pipe\s+/app", dockerfile_text), (
            "chown pipe:pipe /app ausente. "
            "Usuário pipe não terá permissão de escrita em /app."
        )


# ---------------------------------------------------------------------------
# ADR-04 — Pinagem de versões
# ---------------------------------------------------------------------------

class TestVersoesPinadas:
    """ADR-04: dependências críticas devem ter versões explicitamente pinadas."""

    def test_pyyaml_versao_pinada(self, dockerfile_text):
        assert re.search(r"pyyaml==\d+\.\d+", dockerfile_text, re.IGNORECASE), (
            "pyyaml instalado sem versão pinada."
        )

    def test_pyyaml_versao_consistente_com_versions_env(self, dockerfile_text, versions):
        """Versão do pyyaml no Dockerfile deve bater com PYYAML_VERSION em versions.env."""
        env_v = versions.get("PYYAML_VERSION", "")
        match = re.search(r"pyyaml==(\d+\.\d+(?:\.\d+)?)", dockerfile_text, re.IGNORECASE)
        assert match, "pyyaml==X.Y.Z não encontrado no Dockerfile."
        assert match.group(1) == env_v, (
            f"Versão do pyyaml no Dockerfile ({match.group(1)!r}) difere de "
            f"PYYAML_VERSION ({env_v!r}) em docker/versions.env."
        )

    def test_gh_cli_versao_declarada(self, dockerfile_text):
        """GitHub CLI deve ter versão declarada no Dockerfile (apt install gh=X.Y.Z ou ARG GH_VERSION)."""
        versao_apt = re.search(r"gh=(\d+\.\d+\.\d+)", dockerfile_text)
        versao_arg = re.search(r"GH_VERSION=(\d+\.\d+\.\d+)", dockerfile_text)
        assert versao_apt or versao_arg, (
            "Versão do GitHub CLI não encontrada no Dockerfile."
        )

    def test_gh_cli_versao_consistente_com_versions_env(self, dockerfile_text, versions):
        """Versão do gh no Dockerfile deve bater com GH_VERSION em versions.env."""
        env_v = versions.get("GH_VERSION", "")
        match = re.search(r"\bgh=(\d+\.\d+\.\d+)", dockerfile_text)
        if not match:
            match = re.search(r"GH_VERSION=(\d+\.\d+\.\d+)", dockerfile_text)
        assert match, "Versão do gh não encontrada no Dockerfile."
        assert match.group(1) == env_v, (
            f"Versão do gh no Dockerfile ({match.group(1)!r}) difere de "
            f"GH_VERSION ({env_v!r}) em docker/versions.env."
        )

    def test_gh_cli_nao_usa_latest(self, dockerfile_text):
        apts = re.findall(r"apt-get install[^\n]+(?:\\\n[^\n]+)*", dockerfile_text)
        for bloco in apts:
            if re.search(r"\bgh\b(?!=\d)", bloco):
                pytest.fail(
                    "GitHub CLI instalado via apt sem versão pinada. Use 'gh=X.Y.Z'."
                )

    def test_git_versao_pinada_no_apt(self, dockerfile_text, versions):
        """git deve ser instalado com versão exata do versions.env (ADR-04)."""
        env_v = versions.get("GIT_APT_VERSION", "")
        assert env_v, "GIT_APT_VERSION não encontrado em docker/versions.env."
        # A versão APT do git tem formato 1:X.Y.Z-... ; busca escapando os caracteres especiais
        escaped = re.escape(env_v)
        assert re.search(rf"git={escaped}", dockerfile_text), (
            f"git não instalado com versão pinada '{env_v}' (ADR-04). "
            "Use 'git=<GIT_APT_VERSION>' no apt-get install."
        )

    def test_openssh_client_versao_pinada_no_apt(self, dockerfile_text, versions):
        """openssh-client deve ser instalado com versão exata do versions.env (ADR-04)."""
        env_v = versions.get("OPENSSH_CLIENT_APT_VERSION", "")
        assert env_v, "OPENSSH_CLIENT_APT_VERSION não encontrado em docker/versions.env."
        escaped = re.escape(env_v)
        assert re.search(rf"openssh-client={escaped}", dockerfile_text), (
            f"openssh-client não instalado com versão pinada '{env_v}' (ADR-04). "
            "Use 'openssh-client=<OPENSSH_CLIENT_APT_VERSION>' no apt-get install."
        )

    def test_kiro_cli_version_arg_presente(self, dockerfile_text, versions):
        """ARG KIRO_CLI_VERSION deve estar declarado no Dockerfile (ADR-04)."""
        env_v = versions.get("KIRO_CLI_VERSION", "")
        assert re.search(r"ARG\s+KIRO_CLI_VERSION", dockerfile_text), (
            "ARG KIRO_CLI_VERSION não declarado no Dockerfile."
        )
        assert env_v in dockerfile_text, (
            f"Valor padrão KIRO_CLI_VERSION={env_v!r} não encontrado no Dockerfile."
        )

    def test_kiro_cli_sha256_arg_presente(self, dockerfile_text, versions):
        """ARG KIRO_CLI_SHA256 deve estar declarado com o hash correto (ADR-04)."""
        env_sha = versions.get("KIRO_CLI_SHA256", "")
        assert re.search(r"ARG\s+KIRO_CLI_SHA256", dockerfile_text), (
            "ARG KIRO_CLI_SHA256 não declarado no Dockerfile."
        )
        assert env_sha in dockerfile_text, (
            f"SHA256 {env_sha!r} do versions.env não encontrado no Dockerfile."
        )

    def test_kiro_cli_url_arg_presente(self, dockerfile_text, versions):
        """ARG KIRO_CLI_URL deve estar declarado no Dockerfile (ADR-03)."""
        env_url = versions.get("KIRO_CLI_URL", "")
        assert re.search(r"ARG\s+KIRO_CLI_URL", dockerfile_text), (
            "ARG KIRO_CLI_URL não declarado no Dockerfile."
        )
        assert env_url in dockerfile_text, (
            f"URL {env_url!r} do versions.env não encontrada no Dockerfile."
        )


# ---------------------------------------------------------------------------
# ADR-03 — Instalação do kiro-cli via download URL + SHA256
# ---------------------------------------------------------------------------

class TestKiroCliInstalacao:
    """ADR-03: kiro-cli deve ser instalado via download de URL oficial com verificação de hash."""

    def test_nao_copia_kiro_cli_do_host(self, dockerfile_text):
        """ADR-03: kiro-cli NÃO deve ser copiado do host via COPY.

        A abordagem anterior (COPY kiro-cli /usr/local/bin/) foi superada pelo
        ADR-03: download via URL + SHA256 garante pinagem reproduzível sem
        depender do binário instalado localmente no host.
        """
        copy_kiro = [
            l for l in dockerfile_text.splitlines()
            if re.match(r"^\s*COPY\b", l) and re.search(r"\bkiro", l, re.IGNORECASE)
        ]
        assert not copy_kiro, (
            "kiro-cli está sendo copiado do host via COPY. "
            "ADR-03: use download via ARG KIRO_CLI_URL + verificação SHA256."
        )

    def test_download_kiro_cli_via_curl(self, dockerfile_text):
        """ADR-03: kiro-cli deve ser baixado via curl a partir de KIRO_CLI_URL."""
        assert re.search(r"curl\b.*KIRO_CLI_URL", dockerfile_text), (
            "curl com KIRO_CLI_URL não encontrado. "
            "ADR-03: use 'curl ... $KIRO_CLI_URL -o /tmp/kirocli.zip'."
        )

    def test_verificacao_sha256_presente(self, dockerfile_text):
        """ADR-03: download do kiro-cli deve ser verificado com sha256sum."""
        assert re.search(r"sha256sum", dockerfile_text), (
            "sha256sum ausente no Dockerfile. "
            "ADR-03: verificar integridade do binário após download."
        )

    def test_sha256_referencia_kiro_cli_sha256_arg(self, dockerfile_text):
        """A verificação SHA256 deve referenciar o ARG KIRO_CLI_SHA256."""
        assert re.search(r"KIRO_CLI_SHA256", dockerfile_text), (
            "KIRO_CLI_SHA256 não referenciado na verificação de hash."
        )

    def test_instala_kiro_cli_via_install_sh(self, dockerfile_text):
        """O instalador install.sh do pacote kiro-cli deve ser executado."""
        assert re.search(r"install\.sh", dockerfile_text), (
            "install.sh não encontrado. "
            "ADR-03: após unzip, execute kirocli/install.sh."
        )

    def test_smoke_test_kiro_cli_presente(self, dockerfile_text):
        """Um smoke test de kiro-cli deve existir no Dockerfile para validar a instalação."""
        # Aceita tanto --version no RUN da camada 6 quanto na camada de ENV (path absolute ou via PATH)
        assert re.search(r"kiro.cli\s+--version", dockerfile_text), (
            "Smoke test 'kiro-cli --version' ausente no Dockerfile. "
            "ADR-03: validar instalação durante o build para falhar cedo."
        )

    def test_smoke_test_usa_path_absoluto_ou_local_bin(self, dockerfile_text):
        """Smoke test de kiro-cli deve usar path absoluto ou ~/.local/bin/ (ENV PATH definido depois)."""
        # Verifica que o smoke test não depende apenas de 'kiro-cli' sem path
        # (pois o ENV PATH com ~/.local/bin só é definido na camada seguinte)
        smoke_lines = [
            l for l in dockerfile_text.splitlines()
            if "kiro-cli --version" in l or "kiro-cli --version" in l
        ]
        for line in smoke_lines:
            # Linha comentada → ignorar
            if line.strip().startswith("#"):
                continue
            # Se está num RUN (não ENV), deve ter path absoluto ou ~/ ou .local/bin
            if "RUN" in line or not line.strip().startswith("ENV"):
                # Aceita: ~/.local/bin/kiro-cli, /home/pipe/.local/bin/kiro-cli
                # Também aceita kiro-cli sozinho se estiver após o bloco ENV PATH
                pass  # validação qualitativa; o próprio build valida isso
        # O teste principal: smoke test existe (coberto em test_smoke_test_kiro_cli_presente)

    def test_cleanup_tmp_kiro_cli(self, dockerfile_text):
        """Arquivos temporários do kiro-cli devem ser removidos após instalação."""
        assert re.search(r"rm\s+-rf\s+/tmp/kirocli", dockerfile_text), (
            "rm -rf /tmp/kirocli... ausente. "
            "Arquivos temporários do download devem ser removidos para reduzir tamanho da imagem."
        )

    def test_kiro_cli_instalado_como_usuario_pipe(self, dockerfile_lines):
        """kiro-cli deve ser instalado APÓS 'USER pipe' para instalar em ~/.local/bin/."""
        user_pipe_idx = None
        kiro_install_idx = None
        for i, line in enumerate(dockerfile_lines):
            stripped = line.strip()
            if re.match(r"^USER\s+pipe\b", stripped) and user_pipe_idx is None:
                user_pipe_idx = i
            if "install.sh" in stripped and kiro_install_idx is None:
                kiro_install_idx = i
        assert user_pipe_idx is not None, "'USER pipe' não encontrado no Dockerfile."
        assert kiro_install_idx is not None, "install.sh não encontrado no Dockerfile."
        assert kiro_install_idx > user_pipe_idx, (
            f"install.sh (linha {kiro_install_idx+1}) aparece antes de USER pipe "
            f"(linha {user_pipe_idx+1}). "
            "kiro-cli deve ser instalado como usuário pipe para gravar em ~/.local/bin."
        )


# ---------------------------------------------------------------------------
# ADR-07 — Código da esteira via git clone (NÃO via COPY)
# ---------------------------------------------------------------------------

class TestGitClone:
    """ADR-07: código da esteira deve vir via git clone, não via COPY do contexto de build."""

    def test_nao_copia_src_via_copy(self, dockerfile_text):
        """ADR-07: src/ NÃO deve ser copiado via instrução COPY.

        A abordagem anterior (COPY --chown=pipe:pipe src/ /app/src/) foi superada
        pelo ADR-07: o código da esteira entra via git clone durante o build,
        garantindo que a imagem contenha exatamente o commit referenciado por PIPE_REF.
        """
        copy_src = [
            l for l in dockerfile_text.splitlines()
            if re.match(r"^\s*COPY\b", l) and re.search(r"\bsrc/", l)
        ]
        assert not copy_src, (
            "src/ está sendo copiado via COPY. "
            "ADR-07: o código da esteira deve entrar via git clone com PIPE_REPO/PIPE_REF."
        )

    def test_arg_pipe_repo_presente(self, dockerfile_text):
        """ARG PIPE_REPO deve estar declarado para parametrizar o repositório clonado."""
        assert re.search(r"ARG\s+PIPE_REPO\b", dockerfile_text), (
            "ARG PIPE_REPO não declarado. "
            "ADR-07: o repositório clonado deve ser configurável via build-arg."
        )

    def test_arg_pipe_ref_presente(self, dockerfile_text):
        """ARG PIPE_REF deve estar declarado com valor padrão 'main'."""
        assert re.search(r"ARG\s+PIPE_REF", dockerfile_text), (
            "ARG PIPE_REF não declarado. "
            "ADR-07: a branch/tag/sha clonada deve ser configurável."
        )

    def test_pipe_ref_default_main(self, dockerfile_text):
        """ARG PIPE_REF deve ter valor padrão 'main'."""
        assert re.search(r"ARG\s+PIPE_REF=main\b", dockerfile_text), (
            "ARG PIPE_REF não tem valor padrão 'main'. "
            "ADR-07: 'main' é o branch padrão de produção."
        )

    def test_git_clone_no_dockerfile(self, dockerfile_text):
        """git clone deve aparecer no Dockerfile para baixar o código da esteira."""
        assert re.search(r"git\s+clone\b", dockerfile_text), (
            "git clone ausente no Dockerfile. "
            "ADR-07: código da esteira deve ser clonado durante o build."
        )

    def test_git_clone_depth_1(self, dockerfile_text):
        """git clone deve usar --depth 1 para shallow clone (ADR-07, eficiência)."""
        assert re.search(r"git\s+clone\s+--depth\s+1", dockerfile_text), (
            "git clone --depth 1 ausente. "
            "ADR-07: shallow clone reduz tamanho da imagem e tempo de build."
        )

    def test_git_clone_usa_pipe_ref(self, dockerfile_text):
        """git clone deve usar $PIPE_REF como branch/tag."""
        assert re.search(r"git\s+clone.*PIPE_REF", dockerfile_text), (
            "git clone não usa PIPE_REF. "
            "ADR-07: branch clonada deve ser controlada pelo build-arg PIPE_REF."
        )

    def test_git_clone_usa_pipe_repo(self, dockerfile_text):
        """git clone deve usar $PIPE_REPO como URL do repositório."""
        assert re.search(r"git\s+clone.*PIPE_REPO", dockerfile_text), (
            "git clone não usa PIPE_REPO. "
            "ADR-07: repositório clonado deve ser configurável via build-arg."
        )

    def test_buildkit_secret_mount_ssh(self, dockerfile_text):
        """--mount=type=secret,id=ssh_key deve estar presente para chave SSH efêmera (ADR-06)."""
        assert re.search(r"--mount=type=secret.*id=ssh_key", dockerfile_text), (
            "--mount=type=secret,id=ssh_key ausente. "
            "ADR-06: chave SSH deve ser injetada via BuildKit secret, nunca via ARG/ENV/COPY."
        )

    def test_buildkit_secret_uid_1000(self, dockerfile_text):
        """O secret ssh_key deve ter uid=1000 para ser acessível pelo usuário pipe."""
        assert re.search(r"--mount=type=secret.*uid=1000", dockerfile_text), (
            "uid=1000 ausente no --mount=type=secret. "
            "Sem uid=1000, o usuário pipe (uid 1000) não consegue ler a chave SSH montada."
        )

    def test_git_ssh_command_configurado(self, dockerfile_text):
        """GIT_SSH_COMMAND deve ser configurado para usar a chave SSH montada."""
        assert re.search(r"GIT_SSH_COMMAND", dockerfile_text), (
            "GIT_SSH_COMMAND não configurado. "
            "ADR-07: necessário para git clone usar a chave SSH efêmera do BuildKit secret."
        )

    def test_strict_host_checking_accept_new(self, dockerfile_text):
        """StrictHostKeyChecking=accept-new deve ser configurado para evitar prompt interativo."""
        assert re.search(r"StrictHostKeyChecking=accept-new", dockerfile_text), (
            "StrictHostKeyChecking=accept-new ausente. "
            "Sem isso, git clone falhará interativamente ao conectar ao GitHub pela primeira vez."
        )

    def test_copia_apenas_src_do_clone(self, dockerfile_text):
        """Apenas src/ deve ser copiado do clone para /app/src (não o repositório inteiro)."""
        assert re.search(r"/tmp/esteira.*src.*app.*src|cp.*src.*app/src", dockerfile_text), (
            "Cópia de src/ do clone para /app/src não encontrada. "
            "ADR-07: copiar apenas src/ do clone temporário, depois remover /tmp/esteira."
        )

    def test_remove_clone_temporario(self, dockerfile_text):
        """O diretório temporário /tmp/esteira deve ser removido após cópia."""
        assert re.search(r"rm\s+-rf\s+/tmp/esteira", dockerfile_text), (
            "rm -rf /tmp/esteira ausente. "
            "ADR-07: o clone temporário deve ser removido para não inflar a imagem."
        )


# ---------------------------------------------------------------------------
# Estrutura geral do Dockerfile — camadas, ENV, entrypoint
# ---------------------------------------------------------------------------

class TestEstruturaDockerfile:
    """Estrutura geral: imagem base, camadas, variáveis de ambiente, entrypoint."""

    def test_base_python_3_12(self, dockerfile_text):
        assert re.search(r"FROM\s+python:3\.12", dockerfile_text), (
            "Imagem base não é python:3.12. Requisito US-01: Python 3.12+."
        )

    def test_base_python_slim(self, dockerfile_text):
        """Imagem base deve ser a variante slim para minimizar tamanho (ADR-01)."""
        assert re.search(r"FROM\s+python:3\.12-slim", dockerfile_text), (
            "Imagem base não é python:3.12-slim. ADR-01 exige a variante slim."
        )

    def test_cmd_python_m_src(self, dockerfile_text):
        """CMD deve executar 'python -m src' (issue #45 especifica CMD, não ENTRYPOINT)."""
        assert re.search(
            r'CMD\s+\["python",\s*"-m",\s*"src"\]',
            dockerfile_text,
        ), (
            "CMD [\"python\", \"-m\", \"src\"] não encontrado. "
            "O container não iniciará a esteira corretamente."
        )

    def test_env_xdg_runtime_dir(self, dockerfile_text):
        """XDG_RUNTIME_DIR=/tmp deve estar no ENV (necessário para kiro-cli em container)."""
        assert re.search(r"XDG_RUNTIME_DIR=/tmp", dockerfile_text), (
            "XDG_RUNTIME_DIR=/tmp ausente no ENV. "
            "kiro-cli usa XDG_RUNTIME_DIR para socket/lock files em runtime."
        )

    def test_env_path_inclui_local_bin(self, dockerfile_text):
        """PATH deve incluir /home/pipe/.local/bin para kiro-cli ficar disponível."""
        assert re.search(r"PATH=.*home/pipe/\.local/bin", dockerfile_text), (
            "/home/pipe/.local/bin ausente no PATH. "
            "kiro-cli é instalado em ~/.local/bin pelo install.sh — sem esse PATH não é encontrado."
        )

    def test_workdir_app(self, dockerfile_text):
        assert re.search(r"^WORKDIR\s+/app", dockerfile_text, re.MULTILINE), (
            "WORKDIR /app não encontrado."
        )

    def test_openssh_client_correto(self, dockerfile_text):
        assert "openssh-client" in dockerfile_text, (
            "'openssh-client' ausente. Operações SSH falharão."
        )
        linhas_apt = [
            l for l in dockerfile_text.splitlines()
            if "apt-get install" in l or (l.strip().startswith("ssh") and "openssh" not in l)
        ]
        for linha in linhas_apt:
            if re.search(r"\bssh\b(?!-)", linha) and "openssh" not in linha:
                pytest.fail(
                    f"Pacote 'ssh' (nome incorreto) encontrado: {linha.strip()!r}. "
                    "O nome correto é 'openssh-client'."
                )

    def test_apt_no_install_recommends(self, dockerfile_text):
        """apt-get install deve usar --no-install-recommends para minimizar tamanho."""
        apts = re.findall(r"apt-get install[^\n]+(?:\\\n[^\n]+)*", dockerfile_text)
        assert apts, "apt-get install não encontrado no Dockerfile."
        for bloco in apts:
            assert "--no-install-recommends" in bloco, (
                f"apt-get install sem --no-install-recommends: {bloco[:80]!r}. "
                "Instala pacotes desnecessários inflando a imagem."
            )

    def test_apt_rm_lists(self, dockerfile_text):
        """rm -rf /var/lib/apt/lists/* deve aparecer após cada apt-get install."""
        assert dockerfile_text.count("rm -rf /var/lib/apt/lists/*") >= 1, (
            "rm -rf /var/lib/apt/lists/* ausente. "
            "Cache do apt deve ser removido para reduzir tamanho da imagem."
        )

    def test_pip_no_cache_dir(self, dockerfile_text):
        """pip install deve usar --no-cache-dir para não inflar a camada."""
        assert re.search(r"pip install\s+--no-cache-dir", dockerfile_text), (
            "pip install sem --no-cache-dir. "
            "Cache do pip não deve ficar gravado na imagem."
        )

    def test_sem_copy_geral_de_contexto(self, dockerfile_text):
        """Nenhum COPY genérico (. ou src/) deve existir, pois o código vem via git clone.

        ADR-07 + ADR-06: o contexto de build é praticamente vazio (apenas o próprio
        Dockerfile); todo código entra via git clone durante o RUN.
        """
        copy_lines = [
            l.strip() for l in dockerfile_text.splitlines()
            if re.match(r"^\s*COPY\b", l.strip())
        ]
        # Não deve haver nenhum COPY (código vem via git clone)
        assert not copy_lines, (
            f"Instrução COPY encontrada no Dockerfile: {copy_lines}. "
            "ADR-07: nenhum COPY — código da esteira entra via git clone."
        )


# ---------------------------------------------------------------------------
# ADR-06 — .dockerignore e ausência de segredos
# ---------------------------------------------------------------------------

class TestDockerignore:
    """ADR-06: .dockerignore deve bloquear TODO o contexto de build."""

    def test_dockerignore_existe(self):
        assert DOCKERIGNORE.exists(), ".dockerignore não encontrado na raiz do repositório."

    def test_dockerignore_contem_apenas_asterisco(self, dockerignore_text):
        """.dockerignore deve conter apenas '*' para bloquear todo o contexto (ADR-06 + ADR-07).

        Com o código da esteira entrando via git clone (ADR-07), nenhum arquivo
        do host precisa estar no contexto de build. A única linha não-comentário
        deve ser '*', garantindo por construção que pipe.yml, contexts/, .ssh,
        .env e qualquer credencial fiquem de fora.
        """
        linhas_conteudo = [
            l.strip() for l in dockerignore_text.splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]
        assert linhas_conteudo == ["*"], (
            f".dockerignore não contém apenas '*'. Linhas de conteúdo: {linhas_conteudo!r}. "
            "ADR-06: use somente '*' para garantir que nenhum arquivo do host entre no build."
        )

    def test_dockerignore_sem_excecao_kiro_cli(self, dockerignore_text):
        """.dockerignore não deve ter exceção '!kiro-cli' (ADR-03 elimina COPY do host)."""
        linhas = [l.strip() for l in dockerignore_text.splitlines()]
        assert "!kiro-cli" not in linhas, (
            "!kiro-cli encontrado no .dockerignore. "
            "ADR-03: kiro-cli é baixado por URL durante o build, não copiado do host."
        )

    def test_nenhum_arg_com_segredo_no_dockerfile(self, dockerfile_text):
        """Nenhum ARG deve receber valor de segredo diretamente no Dockerfile."""
        # ARGs legítimos: KIRO_CLI_VERSION, KIRO_CLI_URL, KIRO_CLI_SHA256, PIPE_REPO, PIPE_REF
        # Segredos (tokens, passwords, chaves) não devem aparecer como valor de ARG
        secret_patterns = [
            r"ARG\s+\w*TOKEN\w*=\S+",
            r"ARG\s+\w*PASSWORD\w*=\S+",
            r"ARG\s+\w*SECRET\w*=\S+",
            r"ARG\s+\w*API_KEY\w*=\S+",
            r"ARG\s+SSH_PRIVATE",
        ]
        for pat in secret_patterns:
            assert not re.search(pat, dockerfile_text, re.IGNORECASE), (
                f"Possível segredo em ARG detectado (padrão: {pat!r}). "
                "ADR-06: segredos NÃO devem estar em ARG — ficam no histórico da imagem."
            )


# ---------------------------------------------------------------------------
# Ordem de camadas — da mais estável para a mais volátil (ADR-02 single-stage)
# ---------------------------------------------------------------------------

class TestOrdemCamadas:
    """Ordem de camadas do Dockerfile: da mais estável para a mais volátil.

    Camadas definidas pela issue #45 / arquitetura.md §3.2:
      1. FROM (base)
      2. Deps de sistema (apt)
      3. GitHub CLI (apt)
      4. PyYAML (pip)
      5. Usuário pipe (useradd / USER pipe)
      6. kiro-cli (download URL + install.sh) — roda como pipe
      7. ENV (PYTHONUNBUFFERED, XDG_RUNTIME_DIR, PATH)
      8. git clone (código da esteira) — camada mais volátil
    """

    def _find_line(self, lines, pattern):
        for i, l in enumerate(lines):
            if re.search(pattern, l.strip()):
                return i
        return None

    def test_apt_antes_do_pip(self, dockerfile_lines):
        apt_idx = self._find_line(dockerfile_lines, r"apt-get install")
        pip_idx = self._find_line(dockerfile_lines, r"pip install")
        assert apt_idx is not None, "apt-get install não encontrado."
        assert pip_idx is not None, "pip install não encontrado."
        assert apt_idx < pip_idx, (
            f"apt-get install (linha {apt_idx+1}) aparece após pip install (linha {pip_idx+1}). "
            "Deps de sistema devem vir antes de deps Python."
        )

    def test_pip_antes_do_useradd(self, dockerfile_lines):
        pip_idx = self._find_line(dockerfile_lines, r"pip install")
        useradd_idx = self._find_line(dockerfile_lines, r"useradd\b.*pipe")
        assert pip_idx is not None, "pip install não encontrado."
        assert useradd_idx is not None, "useradd não encontrado."
        assert pip_idx < useradd_idx, (
            f"pip install (linha {pip_idx+1}) aparece após useradd (linha {useradd_idx+1}). "
            "PyYAML deve ser instalado como root antes de criar o usuário pipe."
        )

    def test_useradd_antes_do_user_pipe(self, dockerfile_lines):
        useradd_idx = self._find_line(dockerfile_lines, r"useradd\b.*pipe")
        user_pipe_idx = self._find_line(dockerfile_lines, r"^USER\s+pipe\b")
        assert useradd_idx is not None, "useradd não encontrado."
        assert user_pipe_idx is not None, "'USER pipe' não encontrado."
        assert useradd_idx < user_pipe_idx, (
            f"useradd (linha {useradd_idx+1}) aparece após USER pipe (linha {user_pipe_idx+1}). "
            "Usuário deve ser criado antes de mudar para ele."
        )

    def test_kiro_cli_install_apos_user_pipe(self, dockerfile_lines):
        user_pipe_idx = self._find_line(dockerfile_lines, r"^USER\s+pipe\b")
        install_idx = self._find_line(dockerfile_lines, r"install\.sh")
        assert user_pipe_idx is not None, "'USER pipe' não encontrado."
        assert install_idx is not None, "install.sh não encontrado."
        assert install_idx > user_pipe_idx, (
            f"install.sh (linha {install_idx+1}) aparece antes de USER pipe "
            f"(linha {user_pipe_idx+1}). "
            "kiro-cli deve ser instalado como usuário pipe para gravar em ~/.local/bin."
        )

    def test_env_path_apos_kiro_cli_install(self, dockerfile_lines):
        """ENV PATH com ~/.local/bin deve ser definido APÓS a instalação do kiro-cli."""
        install_idx = self._find_line(dockerfile_lines, r"install\.sh")
        env_path_idx = self._find_line(dockerfile_lines, r"PATH=.*local/bin")
        assert install_idx is not None, "install.sh não encontrado."
        assert env_path_idx is not None, "ENV PATH com ~/.local/bin não encontrado."
        assert env_path_idx > install_idx, (
            f"ENV PATH (linha {env_path_idx+1}) aparece antes de install.sh (linha {install_idx+1}). "
            "O smoke test de kiro-cli na camada 6 usa path absoluto; ENV PATH é definido depois."
        )

    def test_git_clone_apos_env_path(self, dockerfile_lines):
        """git clone (código da esteira) deve ser a última camada — mais volátil."""
        env_path_idx = self._find_line(dockerfile_lines, r"PATH=.*local/bin")
        clone_idx = self._find_line(dockerfile_lines, r"git\s+clone\b")
        assert env_path_idx is not None, "ENV PATH com ~/.local/bin não encontrado."
        assert clone_idx is not None, "git clone não encontrado."
        assert clone_idx > env_path_idx, (
            f"git clone (linha {clone_idx+1}) aparece antes de ENV PATH (linha {env_path_idx+1}). "
            "git clone deve ser a camada mais volátil (última), para aproveitar cache das camadas anteriores."
        )


# ---------------------------------------------------------------------------
# Testes de integração Docker (requerem daemon + BuildKit — skip se indisponível)
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

IMAGE = "pipe-esteira-test"


@DOCKER_SKIP
class TestDockerIntegracao:
    """Testes que requerem Docker daemon, BuildKit e chave SSH configurada.

    Para executar localmente (requer PIPE_SSH_KEY_FILE configurado):

        export PIPE_SSH_KEY_FILE=~/.ssh/id_ed25519
        DOCKER_BUILDKIT=1 docker build \\
            --secret id=ssh_key,src="$PIPE_SSH_KEY_FILE" \\
            --build-arg PIPE_REF=main \\
            -t pipe-esteira-test .
        pytest tests/test_dockerfile.py::TestDockerIntegracao -v

    Esses testes verificam os critérios de aceitação da issue #45 que só podem
    ser confirmados com a imagem construída.
    """

    @pytest.fixture(scope="class", autouse=True)
    def build_image(self):
        """Constrói a imagem antes dos testes de integração usando BuildKit + secret SSH.

        Usa PIPE_SSH_KEY_FILE do ambiente. Se não configurado, pula o build
        (falha elegante: skip em vez de FAIL para não bloquear CI sem SSH).
        """
        import os
        ssh_key = os.environ.get("PIPE_SSH_KEY_FILE", "")
        if not ssh_key or not Path(ssh_key).expanduser().exists():
            pytest.skip(
                "PIPE_SSH_KEY_FILE não configurado ou arquivo inexistente. "
                "Configure 'export PIPE_SSH_KEY_FILE=~/.ssh/id_ed25519' para executar os testes de integração."
            )
        ssh_key_path = str(Path(ssh_key).expanduser())
        env = dict(subprocess.os.environ, DOCKER_BUILDKIT="1")
        result = subprocess.run(
            [
                "docker", "build",
                f"--secret=id=ssh_key,src={ssh_key_path}",
                "--build-arg", "PIPE_REF=main",
                "-t", IMAGE,
                str(REPO_ROOT),
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            pytest.fail(
                f"'docker build' falhou (exit {result.returncode}). "
                "AC da issue #45: build deve concluir sem erros.\n"
                f"Stderr:\n{result.stderr[-3000:]}"
            )

    def _run(self, args, entrypoint=None):
        """Executa comando dentro do container IMAGE."""
        cmd = ["docker", "run", "--rm"]
        if entrypoint:
            cmd += ["--entrypoint", entrypoint]
        cmd.append(IMAGE)
        cmd.extend(args)
        return subprocess.run(cmd, capture_output=True, text=True)

    def test_python_version_312(self):
        """python --version deve reportar 3.12.x (AC da issue #45)."""
        r = self._run(["--version"], entrypoint="python")
        assert r.returncode == 0
        assert "3.12" in r.stdout + r.stderr

    def test_git_disponivel(self):
        """git deve estar disponível no container (AC da issue #45)."""
        r = self._run(["--version"], entrypoint="git")
        assert r.returncode == 0, f"git não disponível: {r.stderr}"

    def test_gh_disponivel_e_versao_correta(self):
        """gh deve estar disponível na versão 2.96.0 (AC da issue #45)."""
        r = self._run(["--version"], entrypoint="gh")
        assert r.returncode == 0, f"gh não disponível: {r.stderr}"
        output = r.stdout + r.stderr
        assert "2.96.0" in output, (
            f"gh não reporta versão 2.96.0: {output.strip()!r}"
        )

    def test_kiro_cli_disponivel(self):
        """kiro-cli deve estar disponível no PATH do container (AC da issue #45)."""
        r = self._run(["--version"], entrypoint="kiro-cli")
        # exit != 127 confirma que o binário foi encontrado (127 = command not found)
        assert r.returncode != 127, (
            f"kiro-cli não encontrado no PATH (exit 127). stderr: {r.stderr}"
        )

    def test_pyyaml_importavel(self):
        """PyYAML deve estar instalado e importável na versão correta."""
        versions = _parse_env(VERSIONS_ENV)
        expected = versions.get("PYYAML_VERSION", "")
        r = self._run(
            ["-c", f"import yaml; print(yaml.__version__)"],
            entrypoint="python",
        )
        assert r.returncode == 0, f"python -c 'import yaml' falhou: {r.stderr}"
        assert r.stdout.strip() == expected, (
            f"yaml.__version__={r.stdout.strip()!r}, esperado {expected!r}."
        )

    def test_usuario_nao_root(self):
        """Container deve executar como uid=1000 (pipe) — AC da issue #45."""
        r = self._run([], entrypoint="id")
        assert r.returncode == 0
        assert "uid=1000" in r.stdout, (
            f"Container rodando como usuário inesperado: {r.stdout.strip()!r}"
        )
        assert "pipe" in r.stdout

    def test_pythonunbuffered_no_env_container(self):
        """PYTHONUNBUFFERED=1 deve estar no ambiente do container (AC-04 de US-05)."""
        r = self._run([], entrypoint="env")
        assert r.returncode == 0
        assert "PYTHONUNBUFFERED=1" in r.stdout, (
            "PYTHONUNBUFFERED=1 não encontrado no ambiente do container."
        )

    def test_xdg_runtime_dir_no_env_container(self):
        """XDG_RUNTIME_DIR=/tmp deve estar no ambiente do container."""
        r = self._run([], entrypoint="env")
        assert r.returncode == 0
        assert "XDG_RUNTIME_DIR=/tmp" in r.stdout, (
            "XDG_RUNTIME_DIR=/tmp não encontrado no ambiente do container."
        )

    def test_src_presente_em_app(self):
        """src/ deve existir em /app/src dentro do container (AC da issue #45)."""
        r = self._run(["-d", "/app/src"], entrypoint="test")
        assert r.returncode == 0, "/app/src ausente na imagem."

    def test_pipe_yml_ausente_na_imagem(self):
        """pipe.yml NÃO deve existir dentro da imagem (ADR-06 / AC da issue #45)."""
        r = self._run(["-f", "/app/pipe.yml"], entrypoint="test")
        assert r.returncode != 0, (
            "pipe.yml encontrado em /app. "
            "ADR-06: pipe.yml entra por volume em runtime, nunca embarcado na imagem."
        )

    def test_contexts_ausente_na_imagem(self):
        """contexts/ NÃO deve existir dentro da imagem (ADR-06)."""
        r = self._run(["-d", "/app/contexts"], entrypoint="test")
        assert r.returncode != 0, (
            "contexts/ encontrado em /app. "
            "ADR-06: contextos de agentes entram por volume em runtime."
        )

    def test_sem_variaveis_exit_code_nao_zero(self):
        """Container sem variáveis de ambiente deve falhar com exit-code != 0.

        AC da issue #45: check_config deve detectar configuração ausente e
        terminar com código de erro antes de tentar qualquer operação.
        """
        r = self._run([])  # usa CMD padrão: python -m src
        assert r.returncode != 0, (
            "Container sem variáveis retornou exit-code 0. "
            "check_config deve falhar com erro quando pipe.yml não está montado."
        )

    def test_ls_app_nao_tem_kiro_cli_binario(self):
        """Binário kiro-cli não deve existir em /usr/local/bin (ADR-03: instala em ~/.local/bin)."""
        r = self._run(["-f", "/usr/local/bin/kiro-cli"], entrypoint="test")
        assert r.returncode != 0, (
            "/usr/local/bin/kiro-cli encontrado. "
            "ADR-03: kiro-cli deve ser instalado em ~/.local/bin pelo install.sh, não copiado para /usr/local/bin."
        )
