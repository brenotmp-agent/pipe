"""Testes de validação do arquivo docker/versions.env.

Verificam se o manifesto de versões atende os critérios de aceitação da issue #44:
  - O arquivo docker/versions.env existe com todos os campos preenchidos.
  - Não há placeholders '<...>' no arquivo.
  - O campo KIRO_CLI_SHA256 contém um hash SHA-256 real (64 hex chars).
  - PYYAML_VERSION e GH_VERSION estão no formato semântico correto.
  - A versão do pyyaml é consistente entre versions.env e o Dockerfile.
  - A versão do gh é consistente entre versions.env e o Dockerfile.
  - Não há credenciais, tokens ou chaves SSH no arquivo.

Estes testes são estáticos e não requerem Docker ou rede.
"""

import re
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_ENV = REPO_ROOT / "docker" / "versions.env"
DOCKERFILE = REPO_ROOT / "Dockerfile"

# Campos obrigatórios definidos pelos critérios de aceitação da issue #44
REQUIRED_KEYS = [
    "BASE_IMAGE",
    "GH_VERSION",
    "PYYAML_VERSION",
    "KIRO_CLI_VERSION",
    "KIRO_CLI_SHA256",
    "KIRO_CLI_URL",
]


# ---------------------------------------------------------------------------
# Fixture: parse do versions.env como dicionário
# ---------------------------------------------------------------------------

def _parse_env(path: Path) -> dict:
    """Lê um arquivo .env e retorna dicionário key→value, ignorando comentários."""
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


@pytest.fixture(scope="module")
def versions_env_text():
    assert VERSIONS_ENV.exists(), (
        f"docker/versions.env não encontrado em {VERSIONS_ENV}. "
        "Critério de aceitação #44: o arquivo deve existir no repositório."
    )
    return VERSIONS_ENV.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def versions_env(versions_env_text):
    return _parse_env(VERSIONS_ENV)


@pytest.fixture(scope="module")
def dockerfile_text():
    assert DOCKERFILE.exists(), f"Dockerfile não encontrado em {DOCKERFILE}"
    return DOCKERFILE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Existência e completude
# ---------------------------------------------------------------------------

class TestVersõesEnvExistência:
    """O arquivo docker/versions.env deve existir e estar completo."""

    def test_arquivo_existe(self):
        """docker/versions.env deve existir na raiz do repositório (issues #44 AC-1)."""
        assert VERSIONS_ENV.exists(), (
            "docker/versions.env não encontrado. "
            "A task de requisitos deve ter criado esse arquivo antes desta etapa."
        )

    def test_arquivo_nao_vazio(self, versions_env_text):
        """O arquivo não pode ser vazio."""
        assert versions_env_text.strip(), "docker/versions.env está vazio."

    def test_chaves_obrigatorias_presentes(self, versions_env):
        """Todos os campos obrigatórios devem estar presentes (issue #44 AC-1)."""
        ausentes = [k for k in REQUIRED_KEYS if k not in versions_env]
        assert not ausentes, (
            f"Campos obrigatórios ausentes em docker/versions.env: {ausentes}. "
            "Critério de aceitação: arquivo com TODOS os campos preenchidos."
        )

    def test_sem_placeholders(self, versions_env_text):
        """Nenhum valor de campo pode conter placeholder '<...>' (issue #44 AC-1).

        Apenas linhas de valor (key=value, sem '#') são verificadas.
        Comentários podem conter '<...>' como metavariáveis de documentação.
        """
        value_lines = [
            line for line in versions_env_text.splitlines()
            if line.strip() and not line.strip().startswith("#") and "=" in line
        ]
        placeholders_em_valores = []
        for line in value_lines:
            _, _, value = line.partition("=")
            found = re.findall(r"<[^>]+>", value)
            if found:
                placeholders_em_valores.extend(found)
        assert not placeholders_em_valores, (
            f"Placeholders encontrados em valores de docker/versions.env: {placeholders_em_valores}. "
            "Todos os campos devem estar preenchidos com valores reais."
        )

    def test_valores_nao_vazios(self, versions_env):
        """Nenhum campo obrigatório pode ter valor vazio."""
        vazios = [k for k in REQUIRED_KEYS if not versions_env.get(k, "").strip()]
        assert not vazios, (
            f"Campos com valor vazio: {vazios}. "
            "Todos os campos obrigatórios devem ter valor preenchido."
        )


# ---------------------------------------------------------------------------
# Formato e validade dos valores
# ---------------------------------------------------------------------------

class TestFormatoCampos:
    """Valida formato e integridade dos valores de cada campo."""

    def test_gh_version_formato_semver(self, versions_env):
        """GH_VERSION deve seguir o formato semântico X.Y.Z (sem prefixo 'v')."""
        v = versions_env.get("GH_VERSION", "")
        assert re.match(r"^\d+\.\d+\.\d+$", v), (
            f"GH_VERSION='{v}' não está no formato X.Y.Z. "
            "apt-get install requer versão sem prefixo 'v'."
        )

    def test_gh_version_sem_prefixo_v(self, versions_env):
        """GH_VERSION não deve ter prefixo 'v' (apt-get install gh=<versão> exige sem 'v')."""
        v = versions_env.get("GH_VERSION", "")
        assert not v.startswith("v"), (
            f"GH_VERSION='{v}' contém prefixo 'v'. "
            "Use somente o número: ex. '2.96.0' em vez de 'v2.96.0'."
        )

    def test_pyyaml_version_formato_semver(self, versions_env):
        """PYYAML_VERSION deve seguir o formato X.Y.Z."""
        v = versions_env.get("PYYAML_VERSION", "")
        assert re.match(r"^\d+\.\d+(\.\d+)?$", v), (
            f"PYYAML_VERSION='{v}' não está no formato X.Y[.Z]."
        )

    def test_kiro_cli_version_formato_semver(self, versions_env):
        """KIRO_CLI_VERSION deve seguir o formato X.Y.Z."""
        v = versions_env.get("KIRO_CLI_VERSION", "")
        assert re.match(r"^\d+\.\d+\.\d+$", v), (
            f"KIRO_CLI_VERSION='{v}' não está no formato X.Y.Z."
        )

    def test_kiro_cli_sha256_formato_hex_64(self, versions_env):
        """KIRO_CLI_SHA256 deve ser um hash SHA-256 válido: 64 caracteres hexadecimais (issue #44 AC-2)."""
        sha = versions_env.get("KIRO_CLI_SHA256", "")
        assert re.match(r"^[0-9a-fA-F]{64}$", sha), (
            f"KIRO_CLI_SHA256='{sha}' não é um hash SHA-256 válido. "
            "Deve ter exatamente 64 caracteres hexadecimais."
        )

    def test_kiro_cli_url_https(self, versions_env):
        """KIRO_CLI_URL deve usar HTTPS."""
        url = versions_env.get("KIRO_CLI_URL", "")
        assert url.startswith("https://"), (
            f"KIRO_CLI_URL='{url}' não usa HTTPS. "
            "Download de binários deve sempre usar canal seguro."
        )

    def test_kiro_cli_url_aponta_para_zip(self, versions_env):
        """KIRO_CLI_URL deve apontar para um arquivo .zip."""
        url = versions_env.get("KIRO_CLI_URL", "")
        assert url.endswith(".zip"), (
            f"KIRO_CLI_URL='{url}' não aponta para um arquivo .zip. "
            "O instalador do kiro-cli é distribuído como zip."
        )

    def test_base_image_python_312(self, versions_env):
        """BASE_IMAGE deve ser python:3.12-slim (imagem base conforme requisito)."""
        img = versions_env.get("BASE_IMAGE", "")
        assert "python:3.12" in img, (
            f"BASE_IMAGE='{img}' não é python:3.12-slim. "
            "Requisito US-01: Python 3.12+."
        )

    def test_base_image_nao_e_latest(self, versions_env):
        """BASE_IMAGE não deve ser 'python:latest' ou variante sem versão explícita."""
        img = versions_env.get("BASE_IMAGE", "")
        assert "latest" not in img.lower(), (
            f"BASE_IMAGE='{img}' usa 'latest'. "
            "ADR-04: imagem base deve ter versão explícita."
        )


# ---------------------------------------------------------------------------
# Consistência com o Dockerfile
# ---------------------------------------------------------------------------

class TestConsistênciaComDockerfile:
    """Versões em docker/versions.env devem ser consistentes com o Dockerfile."""

    def test_pyyaml_versao_consistente_com_dockerfile(self, versions_env, dockerfile_text):
        """PYYAML_VERSION em versions.env deve ser igual à versão usada no Dockerfile (issue #44 AC-3)."""
        env_version = versions_env.get("PYYAML_VERSION", "")
        # Extrai versão do Dockerfile: pyyaml==X.Y.Z
        match = re.search(r"pyyaml==(\d+\.\d+(?:\.\d+)?)", dockerfile_text, re.IGNORECASE)
        assert match, (
            "Não foi possível encontrar 'pyyaml==X.Y.Z' no Dockerfile. "
            "O Dockerfile deve instalar pyyaml com versão pinada."
        )
        dockerfile_version = match.group(1)
        assert env_version == dockerfile_version, (
            f"Inconsistência: PYYAML_VERSION={env_version!r} em versions.env "
            f"≠ {dockerfile_version!r} no Dockerfile. "
            "O manifesto e o Dockerfile devem referenciar a mesma versão."
        )

    def test_gh_versao_consistente_com_dockerfile(self, versions_env, dockerfile_text):
        """GH_VERSION em versions.env deve ser igual à versão usada no Dockerfile (issue #44 AC-3)."""
        env_version = versions_env.get("GH_VERSION", "")
        # Extrai versão do Dockerfile: gh=X.Y.Z ou ARG GH_VERSION=X.Y.Z
        match_apt = re.search(r"\bgh=(\d+\.\d+\.\d+)", dockerfile_text)
        match_arg = re.search(r"GH_VERSION=(\d+\.\d+\.\d+)", dockerfile_text)
        match = match_apt or match_arg
        assert match, (
            "Versão do GitHub CLI não encontrada no Dockerfile. "
            "Use 'gh=X.Y.Z' no apt install ou 'ARG GH_VERSION=X.Y.Z'."
        )
        dockerfile_version = match.group(1)
        assert env_version == dockerfile_version, (
            f"Inconsistência: GH_VERSION={env_version!r} em versions.env "
            f"≠ {dockerfile_version!r} no Dockerfile. "
            "O manifesto e o Dockerfile devem referenciar a mesma versão."
        )

    def test_base_image_consistente_com_dockerfile(self, versions_env, dockerfile_text):
        """BASE_IMAGE em versions.env deve ser consistente com FROM no Dockerfile."""
        env_image = versions_env.get("BASE_IMAGE", "")
        # FROM python:3.12-slim ou FROM python:3.12-slim-...
        match = re.search(r"^FROM\s+(\S+)", dockerfile_text, re.MULTILINE)
        assert match, "Instrução FROM não encontrada no Dockerfile."
        dockerfile_image = match.group(1)
        # Verifica que a família (ex.: python:3.12-slim) é a mesma
        assert env_image in dockerfile_image or dockerfile_image.startswith(env_image.split(":")[0]), (
            f"Inconsistência: BASE_IMAGE={env_image!r} em versions.env "
            f"≠ {dockerfile_image!r} no Dockerfile. "
        )


# ---------------------------------------------------------------------------
# Ausência de segredos
# ---------------------------------------------------------------------------

class TestAusenciaDeSegredos:
    """O arquivo versions.env não deve conter credenciais ou tokens (issue #44 AC-4)."""

    # Padrões de segredos: tokens, chaves, senhas
    SECRET_PATTERNS = [
        (r"ghp_[A-Za-z0-9]{36}", "GitHub Personal Access Token (ghp_...)"),
        (r"gho_[A-Za-z0-9]{36}", "GitHub OAuth Token (gho_...)"),
        (r"ghs_[A-Za-z0-9]{36}", "GitHub App Token (ghs_...)"),
        (r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----", "Chave privada PEM"),
        (r"(?i)\bpassword\s*=\s*\S+", "Campo 'password' com valor"),
        (r"(?i)\bsecret\s*=\s*\S+", "Campo 'secret' com valor"),
        (r"(?i)\btoken\s*=\s*\S+", "Campo 'token' com valor"),
        (r"(?i)\bapikey\s*=\s*\S+", "Campo 'apikey' com valor"),
        (r"KIRO_API_KEY\s*=\s*\S+", "KIRO_API_KEY com valor"),
        (r"GH_TOKEN\s*=\s*\S+", "GH_TOKEN com valor"),
        (r"SSH_PRIVATE_KEY\s*=\s*\S+", "Chave SSH privada"),
    ]

    def test_sem_tokens_github(self, versions_env_text):
        """Nenhum token GitHub (ghp_, gho_, ghs_) deve estar presente."""
        for pattern, descricao in self.SECRET_PATTERNS[:3]:
            assert not re.search(pattern, versions_env_text), (
                f"Possível segredo detectado em docker/versions.env: {descricao}. "
                "Critério AC-4: sem credenciais no arquivo."
            )

    def test_sem_chave_privada(self, versions_env_text):
        """Chaves privadas não devem estar no arquivo."""
        assert not re.search(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----", versions_env_text), (
            "Chave privada PEM detectada em docker/versions.env. "
            "Critério AC-4: sem chaves SSH no arquivo."
        )

    def test_sem_campos_de_credencial(self, versions_env_text):
        """Campos como TOKEN, SECRET, PASSWORD, API_KEY não devem ter valores."""
        for pattern, descricao in self.SECRET_PATTERNS[4:]:
            assert not re.search(pattern, versions_env_text), (
                f"Campo sensível detectado: {descricao}. "
                "docker/versions.env deve conter apenas versões e checksums."
            )
