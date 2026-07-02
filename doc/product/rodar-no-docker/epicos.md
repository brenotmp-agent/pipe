# Épicos — Rodar no Docker

Status: draft
Owner: product
Last updated: 2026-07-02

## Inputs
- Issue #1 "Rodar no Docker"
- doc/product/rodar-no-docker/vision.md
- doc/product/rodar-no-docker/problem-space.md

## Épico: Imagem containerizada da esteira

**Objetivo:** ter uma imagem que contenha a esteira e todas as suas
dependências de runtime (Python 3.12+, Git, GitHub CLI, kiro-cli), pronta para
executar `python -m src` sem preparação manual do host.
**Escopo:**
- Empacotamento da aplicação e dependências numa imagem.
- Execução do loop principal dentro do container.
**Fora de escopo:**
- Alteração da lógica de negócio da esteira.
- Publicação da imagem em registries (definido em etapas posteriores, se
  necessário).

## Épico: Configuração e segredos por fora (docker-compose)

**Objetivo:** permitir que toda configuração e todo segredo sejam informados
via `docker-compose`, sem nada sensível fixo na imagem.
**Escopo:**
- `pipe.yml`, `contexts/`, chave SSH, credencial do GitHub e autenticação do
  agente injetáveis via ambiente/volumes declarados no compose.
- Persistência do estado de runtime (`.pipe/`, `logs/`, `repo/`) conforme
  necessidade do usuário.
**Fora de escopo:**
- Escolha da tecnologia de gestão de segredos (decisão de arquitetura).
- Definição de como o `kiro-cli` autentica em ambiente headless (a validar —
  ver Não objetivos e dúvidas).

## Épico: Operação autônoma sem humano

**Objetivo:** garantir que, uma vez configurado, o ciclo completo rode sem
intervenção humana durante a execução.
**Escopo:**
- Execução do loop sem prompts interativos.
- Comportamento previsível em falhas de credencial/setup (falha clara no
  arranque, não travamento silencioso).
**Fora de escopo:**
- Colunas do fluxo que, por design, exigem intervenção humana
  (`need_human`: aprovação de negócio, validações, homologação). Essas
  continuam sendo pontos de espera humana — "sem humano" refere-se à operação
  do runtime, não à eliminação dos gates de aprovação do fluxo.

## Épico: Documentação de operação

**Objetivo:** documentação simples e completa do que é necessário para colocar
a esteira para rodar em Docker.
**Escopo:**
- Pré-requisitos, variáveis/segredos necessários, passo a passo de subida,
  verificação de que está rodando.
**Fora de escopo:**
- Documentação interna de arquitetura da solução Docker (pertence às etapas
  técnicas).
