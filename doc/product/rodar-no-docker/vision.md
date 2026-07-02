# Vision — Rodar no Docker

Status: draft
Owner: product
Last updated: 2026-07-02

## Inputs
- Issue #1 "Rodar no Docker"
- README.md
- CONTEXT.md
- pipe.yml
- src/__main__.py (startup, _setup_ssh)
- src/adapters/kiro_cli_agent.py

## Problema
Hoje a esteira só roda em uma máquina física preparada manualmente: exige uma
chave SSH apontada por `PIPE_SSH_KEY_FILE`, o `gh` CLI autenticado e o
`kiro-cli` autenticado no ambiente. Isso prende o analista a um computador
específico e impede que a esteira seja executada de forma reprodutível e
autônoma em qualquer host.

## Solução
Empacotar a esteira em uma imagem de container e disponibilizar um
`docker-compose` que suba a esteira funcionando de ponta a ponta, sem
intervenção humana durante a execução. Toda configuração e todo segredo
(credenciais de Git/GitHub, autenticação do agente, parâmetros do `pipe.yml`)
devem ser fornecidos por fora — via variáveis de ambiente / arquivos montados
declarados no `docker-compose`. Acompanha uma documentação enxuta com o passo a
passo para colocar para rodar.

## Público-alvo
Analista/desenvolvedor que quer operar a esteira sem depender de uma máquina
física dedicada — em servidor, nuvem ou qualquer host com Docker.

## Proposta de valor
Portabilidade e reprodutibilidade: subir a esteira em qualquer lugar com um
único comando, com todas as configurações externas e nenhuma dependência de
setup manual da máquina hospedeira.

## Métricas de sucesso
- A esteira sobe e completa pelo menos um ciclo completo do loop principal
  dentro do container, sem nenhuma ação humana após o `up`.
- 100% dos parâmetros de configuração e segredos são injetáveis via
  docker-compose (nenhum valor sensível fixo na imagem).
- Um usuário novo consegue colocar a esteira para rodar seguindo apenas a
  documentação, sem conhecimento prévio do código.
- A imagem não contém segredos embutidos.
