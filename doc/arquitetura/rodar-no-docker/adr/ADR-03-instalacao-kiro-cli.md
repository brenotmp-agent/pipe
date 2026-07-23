# ADR-03 — Instalação do kiro-cli via zip installer (não `.deb`)

Status: aceito
Data: 2026-07-07
Relacionado: RNF-02, RNF-05, R-2, ADR-05
Refina: US-01 AC-01 (que citava o método `.deb`)

## Contexto

O kiro-cli é um binário nativo (não um pacote npm). A documentação oficial
(`https://kiro.dev/docs/cli/installation/`, atualizada em 2026-06-03) oferece,
para Linux x86_64:

1. **`.deb`** (seção "Ubuntu"): `wget .../latest/kiro-cli.deb` + `dpkg -i` +
   `apt-get install -f`.
2. **zip installer** (seção "With a zip file"):
   `curl .../latest/kirocli-x86_64-linux.zip` → `unzip` → `./kirocli/install.sh`,
   que instala em `~/.local/bin`. Requer glibc ≥ 2.34.
3. AppImage e variante musl (para glibc < 2.34).

O requisito US-01 AC-01 citou o `.deb`. Esta ADR reavalia a escolha do ponto de
vista arquitetural.

## Decisão

Instalar o kiro-cli pela **variante zip** (`kirocli-x86_64-linux.zip` →
`install.sh` em `~/.local/bin`), executada **como o usuário não-root** `pipe`.
O `.deb` fica documentado como fallback.

## Justificativa

- O `.deb` vem do canal `desktop-release` e o `apt-get install -f` pode arrastar
  dependências de ambiente desktop/GUI — peso e superfície desnecessários numa
  imagem `slim` headless (RNF-02).
- O zip instala num diretório previsível (`~/.local/bin`) e **por usuário**, o
  que casa naturalmente com o usuário não-root (ADR-05) e com o `$HOME`
  gravável — sem precisar de `dpkg`/`root` no passo do agente.
- `python:3.12-slim` tem glibc ≥ 2.36, então a variante padrão (não-musl)
  serve; a variante musl fica reservada caso a base mude.
- Menos efeitos colaterais de `apt` = build mais determinístico (RNF-05).

## Risco R-2 e mitigação

Nenhuma das URLs é versionada — todas apontam para `/latest/`. Consequências:

- A pinagem "de verdade" é feita registrando a **versão validada** em
  `ARG KIRO_CLI_VERSION` (comentário/label) e **verificando o `sha256` do zip**
  no build (`sha256sum -c`), que falha o build se o artefato mudar sob os pés.
- Após instalar, o build roda **`kiro-cli --version` como smoke test**: se o
  binário não executar na imagem, o build falha imediatamente (fecha R-2).
- Auto-update: o kiro-cli se atualiza sozinho em background no uso desktop; em
  container efêmero isso é irrelevante e não é dependência do nosso fluxo.

## Alternativas descartadas

- **`.deb`:** puxa dependências desktop e exige root no momento da instalação;
  mantido só como fallback documentado.
- **AppImage:** exige FUSE/`--appimage-extract` em container; atrito extra sem
  ganho.

## Consequências

- `curl` e `unzip` entram como dependências de build.
- O `PATH` da imagem inclui `/home/pipe/.local/bin`.
- Se um dia a base migrar para musl/alpine, trocar para o artefato `-musl.zip`.
