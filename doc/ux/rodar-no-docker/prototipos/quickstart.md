# PROTÓTIPO DE ONBOARDING — Quickstart (US-03)

Status: protótipo para validação · Autora: Talita Souza — User Experience

> Microtexto de onboarding para alimentar o runbook (US-06). O objetivo de UX é
> levar o operador **do zero ao loop rodando em 4 passos**, deixando explícito
> que trocar configuração **não exige rebuild**.

---

## Pré-requisitos (confira antes de começar)

- [ ] Docker com Compose V2 (`docker compose version` responde).
- [ ] Chave SSH privada cadastrada no GitHub.
- [ ] PAT do GitHub com escopos `repo` e `project`.
- [ ] `KIRO_API_KEY` gerada em app.kiro.dev (requer plano Pro ou superior).

## Subir a esteira em 4 passos

```bash
# 1. Configure os segredos (copie o exemplo e preencha)
cp env.example .env
$EDITOR .env

# 2. Ajuste a configuração da esteira e os contextos dos agentes
$EDITOR pipe.yml
#   preencha contexts/<plataforma>/<agente>.md conforme necessário

# 3. Suba em background
docker compose up -d

# 4. Acompanhe os logs até ver o loop iniciar
docker compose logs -f
```

## Verificar

```bash
docker compose ps        # estado do serviço
docker compose logs -f   # acompanhar o loop em tempo real
```

## Trocar a configuração — SEM REBUILD

Este é o ponto central: para mudar `pipe.yml`, os contextos ou qualquer
credencial, **edite o arquivo e suba de novo** — nada de `docker build`.

```bash
$EDITOR pipe.yml        # ou .env, ou contexts/
docker compose up -d    # aplica a nova configuração, sem rebuild
```

> Só é necessário reconstruir a imagem (`docker build`) se você mudar o
> código-fonte (`src/`) ou o próprio `Dockerfile`.

## Parar

```bash
docker compose down      # o estado persiste nos volumes nomeados
```
