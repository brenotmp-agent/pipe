"""GitHub Board Adapter - implementa BoardPort para GitHub Projects V2."""

import json
import subprocess
import time
import re
from datetime import datetime, timedelta

from src.core.board import BoardPort, Issue, PenaltyException
from src.core.log import log


# Sentinela para diferenciar "não informado" (buscar do board) de None
# (valor conhecido = sem parent). Usado nos setters que aceitam estado conhecido.
_UNSET = object()


class GitHubBoardAdapter(BoardPort):
    """Adapter para GitHub Projects V2."""

    # Penalty
    _in_penalty: bool = False
    _penalty_ttl: datetime = None
    _penalty_value: int = 1
    _penalty_cooldown: datetime = None

    # Throttle
    _throttle_value: int = 16
    _throttle_cooldown: datetime = None
    _throttle_file: str = ".pipe/throttle"

    # Offline (sem conexão) - backoff de reconexão
    _offline_value: int = 1
    _offline_max: int = 300

    # Config
    _repo: str = None

    # Cache de metadados por board_id (preenchido em sync_boards):
    # {board_id: {project_id, status_field_id, options: {col: option_id}}}
    _projects: dict = None

    def _board_meta(self, board_id: str) -> dict:
        """Retorna metadados cacheados do board ou levanta erro se ausente."""
        meta = (self._projects or {}).get(board_id)
        if not meta:
            raise Exception(
                f"Board '{board_id}' não resolvido - execute sync_boards antes"
            )
        return meta

    def _penalty_check(self):
        if self._in_penalty:
            if self._penalty_ttl and self._penalty_ttl > datetime.now():
                remaining = max(1, int((self._penalty_ttl - datetime.now()).total_seconds()))
                raise PenaltyException(remaining)
            else:
                self._in_penalty = False
                log.info("GitHub", "Penalty desativado")
                self._penalty_cooldown = datetime.now() + timedelta(hours=1)

        if self._penalty_cooldown is None:
            self._penalty_cooldown = datetime.now() + timedelta(hours=1)

        if self._penalty_cooldown < datetime.now():
            if self._penalty_value > 1:
                self._penalty_value //= 2
            self._penalty_cooldown = datetime.now() + timedelta(hours=1)

    def _penalty_hit(self) -> PenaltyException:
        self._penalty_ttl = datetime.now() + timedelta(hours=self._penalty_value)
        self._penalty_value *= 2
        self._in_penalty = True
        log.warning("GitHub", f"Penalty ativado por {self._penalty_value // 2}h")
        remaining = int((self._penalty_ttl - datetime.now()).total_seconds())
        return PenaltyException(remaining)

    def _throttle(self):
        if self._throttle_cooldown is None:
            self._throttle_cooldown = datetime.now() + timedelta(hours=1)

        if self._throttle_cooldown < datetime.now():
            if self._throttle_value > 1:
                self._throttle_value //= 2
                self._save_throttle()
                log.info("GitHub", f"Throttle reduzido para {self._throttle_value}s (cooldown)")
            self._throttle_cooldown = datetime.now() + timedelta(hours=1)

        time.sleep(self._throttle_value)

    def _throttle_hit(self):
        if self._throttle_value >= 64:
            raise self._penalty_hit()

        self._throttle_value = min(self._throttle_value * 2, 64)
        self._throttle_cooldown = datetime.now() + timedelta(hours=1)
        self._save_throttle()
        log.info("GitHub", f"Throttle aumentado para {self._throttle_value}s")

    def _save_throttle(self):
        """Persiste throttle_value em arquivo para sobreviver a reinícios."""
        from pathlib import Path
        f = Path(self._throttle_file)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(str(self._throttle_value), encoding="utf-8")

    def _load_throttle(self):
        """Carrega throttle_value persistido (se existir)."""
        from pathlib import Path
        f = Path(self._throttle_file)
        if f.exists():
            try:
                val = int(f.read_text(encoding="utf-8").strip())
                if val > self._throttle_value:
                    self._throttle_value = val
                    log.info("GitHub", f"Throttle restaurado: {val}s")
            except (ValueError, OSError):
                pass

    def _extract_retry_after(self, text: str) -> int | None:
        """Extrai retry-after de headers ou mensagem de erro."""
        m = re.search(r'retry.?after[:\s]+(\d+)', text, re.IGNORECASE)
        if m:
            return int(m.group(1))
        return None

    def _graphql_rate_limited(self, output: str) -> bool:
        """Detecta rate limit REAL numa resposta GraphQL (HTTP 200 + errors).

        O GitHub sinaliza rate limit no GraphQL com HTTP 200 e um array
        ``errors`` contendo ``type == "RATE_LIMITED"``. Inspecionamos APENAS
        essa seção estruturada — nunca o conteúdo de issues (title/body), que
        pode conter a expressão "rate limit" e causar falso-positivo.
        """
        if not output:
            return False
        try:
            data = json.loads(output)
        except (ValueError, TypeError):
            return False
        if not isinstance(data, dict):
            return False
        errors = data.get("errors")
        if not isinstance(errors, list):
            return False
        for err in errors:
            if not isinstance(err, dict):
                continue
            etype = str(err.get("type", "")).upper()
            if etype in ("RATE_LIMITED", "FORBIDDEN"):
                return True
            # Mensagem do próprio erro da API (não do conteúdo da issue).
            msg = str(err.get("message", "")).lower()
            if "rate limit" in msg or "was submitted too quickly" in msg:
                return True
        return False

    def _get_rate_limit_info(self) -> dict:
        """Consulta status do rate limit via GET /rate_limit.

        Retorna dict com limit, remaining, reset (epoch), used, resource.
        Prioriza o recurso que está esgotado (remaining == 0).
        Não conta contra o primary rate limit.

        NOTA: chamada de dentro de _handle_rate_limit (que roda dentro de
        _gh/_gql). NÃO pode ser roteada por _gh (recursão infinita). Respeita
        o throttle chamando self._throttle() diretamente.
        """
        try:
            self._throttle()
            result = subprocess.run(
                ["gh", "api", "rate_limit"],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                return {}
            body = json.loads(result.stdout)
            resources = body.get("resources", {})

            # Encontrar o recurso esgotado (remaining == 0)
            exhausted = None
            for key in ("core", "graphql", "search", "code_search"):
                r = resources.get(key, {})
                if r.get("remaining", 1) == 0:
                    exhausted = dict(r)
                    exhausted["resource"] = key
                    break

            if exhausted:
                return {
                    "limit": exhausted.get("limit", 0),
                    "remaining": 0,
                    "used": exhausted.get("used", 0),
                    "reset": exhausted.get("reset", 0),
                    "resource": exhausted["resource"],
                }
            return {}
        except Exception:
            return {}

    def _handle_rate_limit(self, output: str, error: str, headers: dict = None) -> bool:
        """Detecta e trata rate limit a partir da saída do gh.

        IMPORTANTE: a detecção usa SOMENTE sinais de transporte — status HTTP
        (403/429), stderr do gh e a seção estruturada ``errors`` de uma resposta
        GraphQL. O corpo da resposta (``output``) NUNCA é escaneado em busca da
        expressão "rate limit", pois o título/body de uma issue pode conter esse
        texto e provocar falso-positivo em toda listagem (o que dispararia
        throttle/penalty indevidos).

        Retorna True se era rate limit (já aguardou; caller deve repetir a
        chamada), False caso contrário.
        """
        headers = headers or {}
        status = headers.get("__status__")
        err_lc = (error or "").lower()

        # Sinais de rate limit (apenas transporte / erro estruturado):
        #  - HTTP 403 ou 429 na linha de status da resposta
        #  - stderr do gh menciona rate limit (mensagem da própria CLI/API)
        #  - resposta GraphQL com errors[].type == RATE_LIMITED/FORBIDDEN
        status_signal = status in (403, 429)
        stderr_signal = "rate limit" in err_lc
        graphql_signal = self._graphql_rate_limited(output)

        if not (status_signal or stderr_signal or graphql_signal):
            return False

        # retry-after: só de stderr e headers (nunca do corpo da resposta).
        retry_after = self._extract_retry_after(error or "")
        if not retry_after and headers.get("retry-after"):
            try:
                retry_after = int(headers["retry-after"])
            except ValueError:
                pass

        # Classificação secondary vs primary — só depois de confirmado o limite:
        #  - remaining > 0 (ainda há cota) => secondary/abuse
        #  - retry-after presente => secondary
        #  - menção explícita a "secondary rate limit" no stderr => secondary
        h_remaining = headers.get("x-ratelimit-remaining")
        remaining_int = None
        if h_remaining is not None:
            try:
                remaining_int = int(h_remaining)
            except ValueError:
                remaining_int = None

        is_secondary = (
            "secondary rate limit" in err_lc
            or retry_after is not None
            or (remaining_int is not None and remaining_int > 0)
        )

        if is_secondary:
            # Usar o maior entre retry-after e throttle*4 (backoff exponencial)
            min_wait = self._throttle_value * 4
            wait = max(retry_after or 0, min_wait, 60)
            back_at = (datetime.now() + timedelta(seconds=wait)).strftime("%H:%M:%S")
            log.warning("GitHub",
                        f"Secondary rate limit (pontos restantes: {h_remaining or '?'}, "
                        f"throttle: {self._throttle_value}s) "
                        f"- aguardando {wait}s (retorna às {back_at})",
                        wait_seconds=wait, retry_after=retry_after,
                        remaining=h_remaining, throttle=self._throttle_value,
                        status=status)
            self._throttle_hit()
            time.sleep(wait)
            return True

        # Primary rate limit - usar headers da resposta (remaining == 0)
        h_reset = headers.get("x-ratelimit-reset")
        h_limit = headers.get("x-ratelimit-limit")
        h_used = headers.get("x-ratelimit-used")
        h_resource = headers.get("x-ratelimit-resource", "core")

        if h_reset:
            reset_epoch = int(h_reset)
            wait = max(1, reset_epoch - int(time.time()) + 5)
            back_at = datetime.fromtimestamp(reset_epoch).strftime("%H:%M:%S")
            log.warning("GitHub",
                        f"Primary rate limit ({h_resource}) - "
                        f"{h_used or '?'}/{h_limit or '?'} usado, "
                        f"0 restante, "
                        f"reset às {back_at} (aguardando {wait}s)",
                        resource=h_resource, limit=h_limit,
                        remaining=0, used=h_used,
                        reset=reset_epoch, wait_seconds=wait)
            time.sleep(wait)
            return True

        # Fallback: consultar /rate_limit endpoint
        info = self._get_rate_limit_info()
        if info:
            reset_epoch = info.get("reset", 0)
            wait = max(1, reset_epoch - int(time.time()) + 5)
            back_at = datetime.fromtimestamp(reset_epoch).strftime("%H:%M:%S")
            log.warning("GitHub",
                        f"Primary rate limit ({info['resource']}) - "
                        f"{info['used']}/{info['limit']} usado, "
                        f"0 restante, "
                        f"reset às {back_at} (aguardando {wait}s)",
                        resource=info["resource"], limit=info["limit"],
                        remaining=0, used=info["used"],
                        reset=reset_epoch, wait_seconds=wait)
            time.sleep(wait)
            return True

        # Fallback final
        wait = 60
        back_at = (datetime.now() + timedelta(seconds=wait)).strftime("%H:%M:%S")
        log.warning("GitHub",
                    f"Rate limit (sem detalhes) - aguardando {wait}s "
                    f"(retorna às {back_at})",
                    wait_seconds=wait, stdout=output[:300], stderr=error[:300])
        time.sleep(60)
        return True

    def _handle_offline(self, output: str, error: str) -> bool:
        """Detecta falta de conexão a partir da saída do gh.

        Erro transitório: aguarda um backoff crescente (até _offline_max) e
        sinaliza retry. Não derruba a esteira. Retorna True se era offline.
        """
        combined = f"{output} {error}".lower()
        offline_signs = (
            "error connecting to",
            "could not resolve host",
            "no such host",
            "network is unreachable",
            "connection refused",
            "connection reset",
            "timeout",
            "timed out",
            "temporary failure in name resolution",
            "dial tcp",
        )
        if not any(sign in combined for sign in offline_signs):
            return False

        wait = self._offline_value
        back_at = (datetime.now() + timedelta(seconds=wait)).strftime("%H:%M:%S")
        log.warning("GitHub", f"Sem conexão - nova tentativa às {back_at}",
                    wait_seconds=wait, attempt=self._offline_value, error=error[:200])
        time.sleep(wait)
        self._offline_value = min(self._offline_value * 2, self._offline_max)
        return True

    def _gh(self, *args, stdin: str = None) -> str:
        """Executa comando gh com tratamento de rate limit e falta de conexão.

        Se stdin for fornecido, envia os dados via stdin do processo (útil para --input -).
        Para chamadas 'gh api', injeta -i para capturar headers de rate limit.
        """
        # Detectar se é uma chamada gh api (para injetar -i e parsear headers)
        is_api = len(args) > 0 and args[0] == "api"
        # Não injetar -i se já tem -i ou --include
        has_include = "-i" in args or "--include" in args
        if is_api and not has_include:
            # Inserir -i após 'api'
            args = (args[0], "-i", *args[1:])

        attempt = 0
        while True:
            attempt += 1
            if attempt > 1:
                log.info("GitHub", f"[{self._throttle_value}s] Tentando novamente (tentativa {attempt})",
                         attempt=attempt, command=args[0] if args else "")
            self._throttle()
            result = subprocess.run(["gh", *args], capture_output=True, text=True,
                                    input=stdin)
            raw_output = result.stdout.strip()
            error = result.stderr.strip()

            # Separar headers do body quando -i foi injetado
            output = raw_output
            if is_api and not has_include:
                output, headers = self._split_response(raw_output)
                self._log_rate_limit_headers(headers)
            else:
                headers = {}

            if self._handle_rate_limit(output, error, headers):
                continue

            if result.returncode != 0 and self._handle_offline(output, error):
                continue

            if result.returncode != 0:
                raise Exception(error or output or f"gh retornou código {result.returncode}")

            self._offline_value = 1
            return output

    def _split_response(self, raw: str) -> tuple[str, dict]:
        """Separa headers HTTP do body na resposta com -i.

        Retorna (body, headers_dict).
        """
        # gh api -i retorna: HTTP/1.1 200 OK\r\n<headers>\r\n\r\n<body>
        # ou com \n\n como separador
        separators = ["\r\n\r\n", "\n\n"]
        for sep in separators:
            if sep in raw:
                header_block, body = raw.split(sep, 1)
                headers = self._parse_headers(header_block)
                return body.strip(), headers
        return raw, {}

    def _parse_headers(self, header_block: str) -> dict:
        """Parse dos headers HTTP em um dict (chaves lowercase).

        A linha de status ("HTTP/2 403 Forbidden") é guardada sob a chave
        sintética "__status__" (int) para permitir detecção de rate limit sem
        inspecionar o corpo da resposta.
        """
        headers = {}
        for line in header_block.splitlines():
            stripped = line.strip()
            # Linha de status HTTP: "HTTP/1.1 403 Forbidden" / "HTTP/2 200"
            if stripped.upper().startswith("HTTP/"):
                parts = stripped.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    headers["__status__"] = int(parts[1])
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        return headers

    def _log_rate_limit_headers(self, headers: dict) -> None:
        """Loga informações de rate limit extraídas dos headers da resposta."""
        remaining = headers.get("x-ratelimit-remaining")
        limit = headers.get("x-ratelimit-limit")
        reset = headers.get("x-ratelimit-reset")
        used = headers.get("x-ratelimit-used")
        resource = headers.get("x-ratelimit-resource", "core")

        if remaining is None:
            return

        remaining_int = int(remaining)
        limit_int = int(limit) if limit else 0
        reset_str = ""
        if reset:
            try:
                reset_str = datetime.fromtimestamp(int(reset)).strftime("%H:%M:%S")
            except (ValueError, OSError):
                reset_str = reset

        # Logar sempre como debug (nível INFO só quando está baixo)
        if remaining_int <= 100:
            log.warning("GitHub",
                        f"Rate limit baixo: {remaining}/{limit} restante "
                        f"({resource}), reset às {reset_str}",
                        remaining=remaining_int, limit=limit_int,
                        used=used, resource=resource, reset=reset_str)
        elif remaining_int <= 500:
            log.info("GitHub",
                     f"Rate limit: {remaining}/{limit} restante "
                     f"({resource}), reset às {reset_str}",
                     remaining=remaining_int, limit=limit_int,
                     used=used, resource=resource, reset=reset_str)

    def _gql(self, query: str, **variables) -> dict:
        """Executa query GraphQL com tratamento de rate limit e falta de conexão."""
        attempt = 0
        while True:
            attempt += 1
            if attempt > 1:
                log.info("GitHub", f"[{self._throttle_value}s] Tentando novamente (tentativa {attempt})",
                         attempt=attempt, query=query[:80])
            self._throttle()
            args = ["gh", "api", "-i", "graphql", "-f", f"query={query}"]
            for k, v in variables.items():
                args += self._field_arg(k, v)

            result = subprocess.run(args, capture_output=True, text=True)
            raw_output = result.stdout.strip()
            error = result.stderr.strip()

            # Separar headers do body
            output, headers = self._split_response(raw_output)
            self._log_rate_limit_headers(headers)

            if self._handle_rate_limit(output, error, headers):
                continue

            if result.returncode != 0 and self._handle_offline(output, error):
                continue

            if not output:
                raise Exception(error or "Resposta vazia do GraphQL")

            data = json.loads(output)
            if "errors" in data and "data" not in data:
                raise Exception(str(data["errors"]))

            self._offline_value = 1
            return data.get("data", {})

    def _resolve_owner(self, owner: str) -> tuple[str, str]:
        log.info("GitHub", f"[{self._throttle_value}s] {owner} - Resolvendo owner",
                 operation="resolve_owner", owner=owner)
        data = self._gql(
            "query($login:String!){organization(login:$login){id} user(login:$login){id}}",
            login=owner,
        )
        if data.get("organization") and data["organization"].get("id"):
            return data["organization"]["id"], "organization"
        return data["user"]["id"], "user"

    def _list_projects(self, owner: str, owner_type: str) -> list[dict]:
        log.info("GitHub", f"[{self._throttle_value}s] {owner} - Listando projects",
                 operation="list_projects", owner=owner, owner_type=owner_type)
        entity = "organization" if owner_type == "organization" else "user"
        query = f"query($login:String!){{{entity}(login:$login){{projectsV2(first:50){{nodes{{id number title}}}}}}}}"
        data = self._gql(query, login=owner)
        return data[entity]["projectsV2"]["nodes"]

    def _create_project(self, owner_id: str, title: str) -> dict:
        log.info("GitHub", f"[{self._throttle_value}s] {title} - Criando project",
                 operation="create_project", owner_id=owner_id, title=title)
        data = self._gql(
            "mutation($ownerId:ID!,$title:String!){createProjectV2(input:{ownerId:$ownerId,title:$title}){projectV2{id number title}}}",
            ownerId=owner_id,
            title=title,
        )
        return data["createProjectV2"]["projectV2"]

    def _get_status_field(self, project_id: str) -> dict | None:
        log.info("GitHub", f"[{self._throttle_value}s] {project_id[:8]}... - Buscando campo Status",
                 operation="get_status_field", project_id=project_id)
        data = self._gql(
            "query($id:ID!){node(id:$id){...on ProjectV2{fields(first:20){nodes{...on ProjectV2SingleSelectField{id name options{id name}}}}}}}",
            id=project_id,
        )
        for field in data["node"]["fields"]["nodes"]:
            if field.get("name") == "Status":
                return field
        return None

    def _create_status_field(self, project_id: str, columns: list[str]) -> None:
        log.info("GitHub", f"[{self._throttle_value}s] {project_id[:8]}... - Criando campo Status",
                 operation="create_status_field", project_id=project_id, columns=columns)
        opts = "[" + ",".join(f'{{name:"{col}",color:GRAY,description:""}}' for col in columns) + "]"
        self._gql(
            f'mutation($pid:ID!){{createProjectV2Field(input:{{projectId:$pid,dataType:SINGLE_SELECT,name:"Status",singleSelectOptions:{opts}}}){{projectV2Field{{...on ProjectV2SingleSelectField{{id}}}}}}}}',
            pid=project_id,
        )

    def _update_status_options(self, field_id: str, columns: list[str], existing: dict[str, str]) -> None:
        log.info("GitHub", f"[{self._throttle_value}s] {field_id[:8]}... - Atualizando opções do Status",
                 operation="update_status_options", field_id=field_id, columns=columns)
        parts = []
        for col in columns:
            if col in existing:
                parts.append(f'{{id:"{existing[col]}",name:"{col}",color:GRAY,description:""}}')
            else:
                parts.append(f'{{name:"{col}",color:GRAY,description:""}}')
        opts = "[" + ",".join(parts) + "]"
        self._gql(
            f'mutation($fid:ID!){{updateProjectV2Field(input:{{fieldId:$fid,singleSelectOptions:{opts}}}){{projectV2Field{{...on ProjectV2SingleSelectField{{id}}}}}}}}',
            fid=field_id,
        )

    def connect(self, config: dict) -> None:
        repos = config.get("git", {}).get("repo", {})
        self._repo = list(repos.values())[0] if repos else None
        if self._repo and self._repo.startswith("git@github.com:"):
            self._repo = self._repo.replace("git@github.com:", "").replace(".git", "")
        self._load_throttle()
        log.info("GitHub", f"Repositório: {self._repo} (throttle: {self._throttle_value}s)")

    def check_access(self, config: dict) -> None:
        """Valida acesso e permissão de escrita no repositório ANTES de rodar.

        Usa chamadas diretas ao ``gh`` (sem passar por ``_gh``) para não acionar
        o tratamento de rate limit/penalty durante a verificação de startup —
        um 403 aqui significa "sem permissão", não "rate limit".

        Levanta ``BoardAccessError`` quando:
          - não há repositório configurado;
          - o token não está autenticado;
          - o repositório não existe ou é inacessível pelo token;
          - o token não tem permissão de escrita (push/maintain/admin).
        """
        from src.core.board import BoardAccessError

        if not self._repo:
            raise BoardAccessError("Repositório não configurado em git.repo")

        # 1. Usuário autenticado
        who = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True, text=True,
        )
        if who.returncode != 0:
            raise BoardAccessError(
                "Token do gh não autenticado ou inválido: "
                + (who.stderr.strip() or "falha ao consultar /user")
            )
        login = who.stdout.strip()

        # 2. Acesso e permissões no repositório
        result = subprocess.run(
            ["gh", "api", f"repos/{self._repo}"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            raise BoardAccessError(
                f"Sem acesso ao repositório '{self._repo}' como '{login}': {err}"
            )

        try:
            data = json.loads(result.stdout)
        except (ValueError, TypeError):
            raise BoardAccessError(
                f"Resposta inválida ao consultar repositório '{self._repo}'"
            )

        perms = data.get("permissions") or {}
        can_write = bool(
            perms.get("admin") or perms.get("maintain") or perms.get("push")
        )
        if not can_write:
            level = next(
                (name for name, key in (
                    ("admin", "admin"), ("maintain", "maintain"),
                    ("push", "push"), ("triage", "triage"), ("pull", "pull"),
                ) if perms.get(key)),
                "nenhuma",
            )
            raise BoardAccessError(
                f"Token '{login}' não tem permissão de escrita em "
                f"'{self._repo}' (nível atual: {level}). "
                f"É necessário push, maintain ou admin."
            )

        log.info("GitHub", f"Permissões OK: '{login}' com escrita em '{self._repo}'")

    def sync_boards(self, boards: list[dict]) -> None:
        self._penalty_check()

        if not self._repo:
            log.warning("GitHub", "Repositório não configurado")
            return

        if self._projects is None:
            self._projects = {}

        owner = self._repo.split("/")[0]
        owner_id, owner_type = self._resolve_owner(owner)
        projects = self._list_projects(owner, owner_type)
        projects_by_title = {p["title"]: p for p in projects}

        for board in boards:
            board_id = board["id"]
            board_name = board["name"]
            columns = board["columns"]

            project = projects_by_title.get(board_name)
            if not project:
                log.info("GitHub", f"Criando board '{board_name}'")
                project = self._create_project(owner_id, board_name)
                projects_by_title[board_name] = project

            status_field = self._get_status_field(project["id"])
            if not status_field:
                log.info("GitHub", f"Criando campo Status para '{board_name}'")
                self._create_status_field(project["id"], columns)
                status_field = self._get_status_field(project["id"])
            else:
                existing = {o["name"]: o["id"] for o in status_field.get("options", [])}
                current_order = [o["name"] for o in status_field.get("options", [])]
                if current_order != columns:
                    log.info("GitHub", f"Atualizando colunas de '{board_name}'")
                    self._update_status_options(status_field["id"], columns, existing)
                    status_field = self._get_status_field(project["id"])

            # Cacheia metadados para list_issues/move_issue
            self._projects[board_id] = {
                "project_id": project["id"],
                "status_field_id": status_field["id"] if status_field else None,
                "options": {
                    o["name"]: o["id"]
                    for o in (status_field.get("options", []) if status_field else [])
                },
            }

        log.info("GitHub", "Boards sincronizados")

    def list_issues(self, board_id: str) -> list[Issue]:
        self._penalty_check()
        meta = self._board_meta(board_id)
        project_id = meta["project_id"]

        log.info("GitHub", f"[{self._throttle_value}s] {board_id} - Listando issues",
                 operation="list_issues", board_id=board_id, project_id=project_id)

        query = """query($pid:ID!,$cursor:String){
          node(id:$pid){...on ProjectV2{
            items(first:5,after:$cursor){
              pageInfo{hasNextPage endCursor}
              nodes{
                id
                isArchived
                fieldValues(first:10){nodes{...on ProjectV2ItemFieldSingleSelectValue{field{...on ProjectV2SingleSelectField{name}} name}}}
                content{...on Issue{number title body updatedAt labels(first:20){nodes{name}}}}
              }
            }
          }}
        }"""

        issues: list[Issue] = []
        cursor = ""
        page_num = 0
        while True:
            page_num += 1
            if page_num > 1:
                log.info("GitHub", f"[{self._throttle_value}s] {board_id} - Página {page_num}",
                         operation="list_issues_page", board_id=board_id, page=page_num)
            data = self._gql(query, pid=project_id, cursor=cursor) if cursor \
                else self._gql(query, pid=project_id)

            node = data.get("node") or {}
            page = node.get("items", {})
            for item in page.get("nodes", []):
                if item.get("isArchived"):
                    continue
                content = item.get("content")
                if not content or not content.get("number"):
                    continue

                column = ""
                for fv in item.get("fieldValues", {}).get("nodes", []):
                    if (fv.get("field") or {}).get("name") == "Status":
                        column = fv.get("name", "")
                        break

                labels = [
                    l["name"]
                    for l in (content.get("labels", {}) or {}).get("nodes", [])
                ]

                issues.append(Issue(
                    id=str(content["number"]),
                    title=content.get("title", ""),
                    body=content.get("body", ""),
                    column=column,
                    labels=labels,
                    updated_at=content.get("updatedAt", ""),
                ))

            page_info = page.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info["endCursor"]

        return issues

    def list_issues_since(self, board_id: str, since: str) -> list[Issue]:
        """Lista issues modificadas desde `since` usando list_issues + filtro client-side."""
        self._penalty_check()
        all_issues = self.list_issues(board_id)
        return [i for i in all_issues if i.updated_at and i.updated_at > since]

    def get_issue(self, board_id: str, issue_id: str, fullsync: bool = False) -> Issue:
        self._penalty_check()
        log.info("GitHub", f"[{self._throttle_value}s] #{issue_id} - Buscando issue"
                 + (" (fullsync)" if fullsync else ""),
                 operation="get_issue", board_id=board_id, issue_id=issue_id,
                 fullsync=fullsync)
        # Chamada única: propriedades + labels + parent + children + status
        # (coluna) + isArchived do item do project. Dependencies (blocked_by/
        # blocks) NÃO existem no GraphQL (só REST) e só são buscadas quando
        # fullsync=True, via _get_dependencies (2 chamadas REST).
        data = self._gql(
            "query($owner:String!,$repo:String!,$number:Int!){repository(owner:$owner,name:$repo){issue(number:$number){"
            "number title body state updatedAt "
            "labels(first:50){nodes{name}} "
            "parent{number} "
            "subIssues(first:50){nodes{number}} "
            "projectItems(first:10){nodes{isArchived project{id} "
            "fieldValues(first:10){nodes{...on ProjectV2ItemFieldSingleSelectValue{field{...on ProjectV2SingleSelectField{name}} name}}}}}"
            "}}}",
            owner=self._repo.split("/")[0],
            repo=self._repo.split("/")[1],
            number=int(issue_id),
        )
        issue = data["repository"]["issue"]
        labels = [l["name"] for l in (issue.get("labels", {}) or {}).get("nodes", [])]
        parent_node = issue.get("parent") or {}
        parent = str(parent_node["number"]) if parent_node.get("number") else None
        children = [
            str(n["number"])
            for n in (issue.get("subIssues", {}) or {}).get("nodes", [])
            if n.get("number")
        ]

        # Coluna (Status) e arquivamento a partir do item do project deste board.
        column = ""
        archived = False
        target_pid = (self._projects or {}).get(board_id, {}).get("project_id")
        for pi in (issue.get("projectItems", {}) or {}).get("nodes", []):
            pid = (pi.get("project") or {}).get("id")
            if target_pid and pid != target_pid:
                continue
            archived = bool(pi.get("isArchived"))
            for fv in (pi.get("fieldValues", {}) or {}).get("nodes", []):
                if (fv.get("field") or {}).get("name") == "Status":
                    column = fv.get("name", "")
                    break
            break

        # Dependencies só no fullsync (2 chamadas REST extras).
        blocked_by, blocks = ([], [])
        if fullsync:
            blocked_by, blocks = self._get_dependencies(issue_id)

        return Issue(
            id=str(issue["number"]),
            title=issue.get("title", ""),
            body=issue.get("body", ""),
            column=column,
            labels=labels,
            updated_at=issue.get("updatedAt", ""),
            parent=parent,
            children=children,
            blocked_by=blocked_by,
            blocks=blocks,
            state=(issue.get("state") or "").lower(),
            archived=archived,
        )

    def create_issue(self, board_id: str, title: str, body: str, column: str) -> Issue:
        self._penalty_check()
        log.info("GitHub", f"[{self._throttle_value}s] {board_id} - Criando issue '{title}'",
                 operation="create_issue", board_id=board_id, title=title)
        # 'gh issue create' NÃO suporta --json; ele imprime a URL da issue
        # criada no stdout (ex.: https://github.com/owner/repo/issues/42).
        result = self._gh("issue", "create", "--repo", self._repo,
                          "--title", title, "--body", body)
        issue_url = result.strip().splitlines()[-1].strip() if result.strip() else ""
        issue_id = issue_url.rstrip("/").split("/")[-1]
        if not issue_id.isdigit():
            raise Exception(
                f"Não foi possível extrair o número da issue da saída de 'gh issue create': {result!r}"
            )
        # Buscar node_id e updatedAt em uma única query GraphQL.
        info = self._gql(
            "query($owner:String!,$repo:String!,$number:Int!){repository(owner:$owner,name:$repo){issue(number:$number){id updatedAt}}}",
            owner=self._repo.split("/")[0],
            repo=self._repo.split("/")[1],
            number=int(issue_id),
        )
        issue_node = (info.get("repository") or {}).get("issue") or {}
        node_id = issue_node.get("id")
        updated_at = issue_node.get("updatedAt", "")
        # Adicionar ao project e mover para coluna
        meta = self._board_meta(board_id)
        # Adicionar issue ao project
        add_data = self._gql(
            "mutation($pid:ID!,$contentId:ID!){addProjectV2ItemById(input:{projectId:$pid,contentId:$contentId}){item{id}}}",
            pid=meta["project_id"],
            contentId=node_id,
        )
        item_id = add_data["addProjectV2ItemById"]["item"]["id"]
        # Mover para coluna correta
        option_id = meta["options"].get(column)
        if option_id:
            self._gql(
                "mutation($pid:ID!,$itemId:ID!,$fieldId:ID!,$optionId:String!){updateProjectV2ItemFieldValue(input:{projectId:$pid,itemId:$itemId,fieldId:$fieldId,value:{singleSelectOptionId:$optionId}}){projectV2Item{id}}}",
                pid=meta["project_id"], itemId=item_id,
                fieldId=meta["status_field_id"], optionId=option_id,
            )
        return Issue(
            id=issue_id, title=title, body=body, column=column,
            updated_at=updated_at,
        )

    def _get_issue_node_id(self, issue_id: str) -> str:
        data = self._gql(
            "query($owner:String!,$repo:String!,$number:Int!){repository(owner:$owner,name:$repo){issue(number:$number){id}}}",
            owner=self._repo.split("/")[0],
            repo=self._repo.split("/")[1],
            number=int(issue_id),
        )
        return data["repository"]["issue"]["id"]

    def move_issue(self, board_id: str, issue_id: str, column: str, from_column: str = None) -> None:
        self._penalty_check()
        meta = self._board_meta(board_id)
        option_id = meta["options"].get(column)
        if not option_id:
            log.warning("GitHub", f"Coluna '{column}' não encontrada no board '{board_id}'")
            return
        move_label = f"{from_column} -> {column}" if from_column else f"-> {column}"
        log.info("GitHub", f"[{self._throttle_value}s] #{issue_id} {move_label}",
                 operation="move_issue", board_id=board_id, issue_id=issue_id, column=column)
        item_id = self._find_item_id(board_id, issue_id)
        if not item_id:
            log.warning("GitHub", f"Issue #{issue_id} não encontrada no project")
            return
        self._gql(
            "mutation($pid:ID!,$itemId:ID!,$fieldId:ID!,$optionId:String!){updateProjectV2ItemFieldValue(input:{projectId:$pid,itemId:$itemId,fieldId:$fieldId,value:{singleSelectOptionId:$optionId}}){projectV2Item{id}}}",
            pid=meta["project_id"], itemId=item_id,
            fieldId=meta["status_field_id"], optionId=option_id,
        )

    def _find_item_id(self, board_id: str, issue_id: str) -> str | None:
        """Busca o item_id do project para uma issue pelo number."""
        meta = self._board_meta(board_id)
        data = self._gql(
            "query($pid:ID!){node(id:$pid){...on ProjectV2{items(first:100){nodes{id content{...on Issue{number}}}}}}}",
            pid=meta["project_id"],
        )
        for item in data.get("node", {}).get("items", {}).get("nodes", []):
            content = item.get("content") or {}
            if str(content.get("number")) == str(issue_id):
                return item["id"]
        return None

    def update_issue(self, board_id: str, issue_id: str, title: str = None, body: str = None) -> None:
        self._penalty_check()
        log.info("GitHub", f"[{self._throttle_value}s] #{issue_id} - Atualizando issue",
                 operation="update_issue", board_id=board_id, issue_id=issue_id)
        args = ["issue", "edit", issue_id, "--repo", self._repo]
        if title:
            args += ["--title", title]
        if body:
            args += ["--body", body]
        self._gh(*args)

    def add_comment(self, board_id: str, issue_id: str, comment: str) -> None:
        self._penalty_check()
        log.info("GitHub", f"[{self._throttle_value}s] #{issue_id} - Adicionando comentário",
                 operation="add_comment", board_id=board_id, issue_id=issue_id)
        self._gh("issue", "comment", issue_id, "--repo", self._repo, "--body", comment)

    def list_comments(self, board_id: str, issue_id: str) -> list[dict]:
        self._penalty_check()
        log.info("GitHub", f"[{self._throttle_value}s] #{issue_id} - Listando comentários",
                 operation="list_comments", board_id=board_id, issue_id=issue_id)
        result = self._gh("issue", "view", issue_id, "--repo", self._repo,
                          "--json", "comments")
        data = json.loads(result)
        return [
            {"author": c.get("author", {}).get("login", ""), "date": c.get("createdAt", ""), "body": c.get("body", "")}
            for c in data.get("comments", [])
        ]

    def close_issue(self, board_id: str, issue_id: str) -> None:
        self._penalty_check()
        log.info("GitHub", f"[{self._throttle_value}s] #{issue_id} - Fechando issue",
                 operation="close_issue", board_id=board_id, issue_id=issue_id)
        self._gh("issue", "close", issue_id, "--repo", self._repo)

    def reopen_issue(self, board_id: str, issue_id: str) -> None:
        self._penalty_check()
        log.info("GitHub", f"[{self._throttle_value}s] #{issue_id} - Reabrindo issue",
                 operation="reopen_issue", board_id=board_id, issue_id=issue_id)
        self._gh("issue", "reopen", issue_id, "--repo", self._repo)

    # ── Resolução de databaseId ───────────────────────────────────────────────

    def _get_issue_db_id(self, issue_number: str) -> int | None:
        """Resolve o databaseId (inteiro REST) a partir do number da issue."""
        data = self._gql(
            "query($owner:String!,$repo:String!,$number:Int!){repository(owner:$owner,name:$repo){issue(number:$number){fullDatabaseId}}}",
            owner=self._repo.split("/")[0],
            repo=self._repo.split("/")[1],
            number=int(issue_number),
        )
        issue = (data.get("repository") or {}).get("issue") or {}
        db_id = issue.get("fullDatabaseId")
        return int(db_id) if db_id else None

    @staticmethod
    def _field_arg(key, value) -> list[str]:
        """Serializa um campo para o ``gh api``.

        Usa ``-F`` (typed) para bool/int/float e ``-f`` (string) para o resto.
        Booleanos são emitidos como os literais JSON ``true``/``false``: o gh só
        reconhece a conversão mágica com literais minúsculos, então ``str(True)``
        == ``"True"`` seria enviado como string e rejeitado pela API
        (ex.: ``Invalid property /replace_parent: "True" is not of type boolean``).
        """
        if isinstance(value, bool):
            return ["-F", f"{key}={'true' if value else 'false'}"]
        if isinstance(value, (int, float)):
            return ["-F", f"{key}={value}"]
        return ["-f", f"{key}={value}"]

    def _api(self, method: str, path: str, **fields) -> str:
        """Chama a REST API via gh api (método + path + campos -f/-F)."""
        args = ["api", "-X", method,
                "-H", "Accept: application/vnd.github+json", path]
        for k, v in fields.items():
            args += self._field_arg(k, v)
        return self._gh(*args)

    # ── Sub-issues (parent / children) ────────────────────────────────────────

    def _list_sub_issue_numbers(self, parent_number: str) -> list[str]:
        """Lista os numbers das sub-issues de uma issue."""
        owner, repo = self._repo.split("/")
        try:
            result = self._gh(
                "api", f"/repos/{owner}/{repo}/issues/{parent_number}/sub_issues",
                "-H", "Accept: application/vnd.github+json",
            )
        except Exception as e:
            log.warning("GitHub", f"#{parent_number} - falha ao listar sub-issues: {e}")
            return []
        data = json.loads(result) if result else []
        return [str(i.get("number")) for i in data if i.get("number")]

    def _add_sub_issue(self, parent_number: str, child_number: str) -> None:
        owner, repo = self._repo.split("/")
        child_db = self._get_issue_db_id(child_number)
        if not child_db:
            log.warning("GitHub", f"#{child_number} - databaseId não resolvido")
            return
        self._api("POST", f"/repos/{owner}/{repo}/issues/{parent_number}/sub_issues",
                  sub_issue_id=child_db, replace_parent=True)

    def _remove_sub_issue(self, parent_number: str, child_number: str) -> None:
        owner, repo = self._repo.split("/")
        child_db = self._get_issue_db_id(child_number)
        if not child_db:
            return
        self._api("DELETE", f"/repos/{owner}/{repo}/issues/{parent_number}/sub_issue",
                  sub_issue_id=child_db)

    def set_children(self, board_id: str, issue_id: str, children_ids: list[str],
                     known_current: list[str] | None = None) -> None:
        """SET das sub-issues: adiciona faltantes e remove as não declaradas.

        known_current (se fornecido) evita o GET de listagem das sub-issues.
        """
        self._penalty_check()
        desired = {str(c) for c in (children_ids or [])}
        if known_current is not None:
            current = {str(c) for c in known_current}
        else:
            current = set(self._list_sub_issue_numbers(issue_id))
        log.info("GitHub", f"[{self._throttle_value}s] #{issue_id} - children {sorted(desired)}",
                 operation="set_children", board_id=board_id, issue_id=issue_id)
        for child in desired - current:
            self._add_sub_issue(issue_id, child)
        for child in current - desired:
            self._remove_sub_issue(issue_id, child)

    def set_parent(self, board_id: str, issue_id: str, parent_id: str | None,
                   known_current=_UNSET) -> None:
        """Define o parent desta issue (sub-issue de parent_id). None remove.

        known_current (se != _UNSET) evita o GET do parent atual; passe o
        number do parent conhecido ou None se sabidamente sem parent.
        """
        self._penalty_check()
        owner, repo = self._repo.split("/")
        # Parent atual
        if known_current is not _UNSET:
            current_parent = str(known_current) if known_current else None
        else:
            current_parent = None
            try:
                result = self._gh(
                    "api", f"/repos/{owner}/{repo}/issues/{issue_id}/parent",
                    "-H", "Accept: application/vnd.github+json",
                )
                if result:
                    current_parent = str(json.loads(result).get("number"))
            except Exception:
                current_parent = None

        log.info("GitHub", f"[{self._throttle_value}s] #{issue_id} - parent {parent_id}",
                 operation="set_parent", board_id=board_id, issue_id=issue_id)

        if parent_id:
            if str(parent_id) != current_parent:
                self._add_sub_issue(str(parent_id), issue_id)
        elif current_parent:
            self._remove_sub_issue(current_parent, issue_id)

    # ── Dependências (blocked_by / blocks) ────────────────────────────────────

    def _get_dependencies(self, issue_number: str) -> tuple[list[str], list[str]]:
        """Retorna (blocked_by, blocks) como listas de numbers via REST."""
        owner, repo = self._repo.split("/")
        blocked_by, blocks = [], []
        try:
            r = self._gh("api", f"/repos/{owner}/{repo}/issues/{issue_number}/dependencies/blocked_by",
                         "-H", "Accept: application/vnd.github+json")
            blocked_by = [str(i.get("number")) for i in (json.loads(r) if r else []) if i.get("number")]
        except Exception as e:
            log.warning("GitHub", f"#{issue_number} - falha ao listar blocked_by: {e}")
        try:
            r = self._gh("api", f"/repos/{owner}/{repo}/issues/{issue_number}/dependencies/blocking",
                         "-H", "Accept: application/vnd.github+json")
            blocks = [str(i.get("number")) for i in (json.loads(r) if r else []) if i.get("number")]
        except Exception as e:
            log.warning("GitHub", f"#{issue_number} - falha ao listar blocking: {e}")
        return blocked_by, blocks

    def set_blocked_by(self, board_id: str, issue_id: str, blocker_ids: list[str],
                       known_current: list[str] | None = None) -> None:
        """SET das issues que bloqueiam esta (blocked_by).

        known_current (se fornecido) evita as 2 chamadas REST de _get_dependencies.
        """
        self._penalty_check()
        owner, repo = self._repo.split("/")
        desired = {str(b) for b in (blocker_ids or [])}
        if known_current is not None:
            current = {str(b) for b in known_current}
        else:
            current_by, _ = self._get_dependencies(issue_id)
            current = set(current_by)
        log.info("GitHub", f"[{self._throttle_value}s] #{issue_id} - blocked_by {sorted(desired)}",
                 operation="set_blocked_by", board_id=board_id, issue_id=issue_id)
        for b in desired - current:
            db = self._get_issue_db_id(b)
            if db:
                self._api("POST", f"/repos/{owner}/{repo}/issues/{issue_id}/dependencies/blocked_by",
                          issue_id=db)
        for b in current - desired:
            db = self._get_issue_db_id(b)
            if db:
                self._gh("api", "-X", "DELETE",
                         "-H", "Accept: application/vnd.github+json",
                         f"/repos/{owner}/{repo}/issues/{issue_id}/dependencies/blocked_by/{db}")

    def set_blocks(self, board_id: str, issue_id: str, blocked_ids: list[str],
                   known_current: list[str] | None = None) -> None:
        """SET das issues que esta bloqueia.

        A API só escreve no lado blocked_by; 'blocks' em N equivale a
        blocked_by desta em N. Implementado adicionando/removendo esta issue
        como blocker em cada N declarado.

        known_current (se fornecido) evita as 2 chamadas REST de _get_dependencies.
        """
        self._penalty_check()
        owner, repo = self._repo.split("/")
        desired = {str(b) for b in (blocked_ids or [])}
        if known_current is not None:
            current = {str(b) for b in known_current}
        else:
            _, current_blocks = self._get_dependencies(issue_id)
            current = set(current_blocks)
        if desired == current:
            return
        this_db = self._get_issue_db_id(issue_id)
        if not this_db:
            log.warning("GitHub", f"#{issue_id} - databaseId não resolvido para set_blocks")
            return
        log.info("GitHub", f"[{self._throttle_value}s] #{issue_id} - blocks {sorted(desired)}",
                 operation="set_blocks", board_id=board_id, issue_id=issue_id)
        for n in desired - current:
            self._api("POST", f"/repos/{owner}/{repo}/issues/{n}/dependencies/blocked_by",
                      issue_id=this_db)
        for n in current - desired:
            self._gh("api", "-X", "DELETE",
                     "-H", "Accept: application/vnd.github+json",
                     f"/repos/{owner}/{repo}/issues/{n}/dependencies/blocked_by/{this_db}")

    # ── Labels ────────────────────────────────────────────────────────────────

    def set_labels(self, board_id: str, issue_id: str, labels: list[str]) -> None:
        """SET das labels da issue (substitui todas via PUT REST)."""
        self._penalty_check()
        owner, repo = self._repo.split("/")
        log.info("GitHub", f"[{self._throttle_value}s] #{issue_id} - labels {labels}",
                 operation="set_labels", board_id=board_id, issue_id=issue_id)
        # PUT substitui todas as labels; usa --input - com JSON para garantir
        # que a API receba um array válido (inclusive array vazio).
        payload = json.dumps({"labels": labels or []})
        args = ["api", "-X", "PUT",
                "-H", "Accept: application/vnd.github+json",
                "--input", "-",
                f"/repos/{owner}/{repo}/issues/{issue_id}/labels"]
        self._gh(*args, stdin=payload)

    def add_label(self, board_id: str, issue_id: str, label: str) -> None:
        """Adiciona uma única label (mantém as demais) via POST REST."""
        self._penalty_check()
        owner, repo = self._repo.split("/")
        log.info("GitHub", f"[{self._throttle_value}s] #{issue_id} - +label '{label}'",
                 operation="add_label", board_id=board_id, issue_id=issue_id)
        self._api("POST", f"/repos/{owner}/{repo}/issues/{issue_id}/labels",
                  **{"labels[]": label})

    def remove_label(self, board_id: str, issue_id: str, label: str) -> None:
        """Remove uma única label (mantém as demais) via DELETE REST."""
        self._penalty_check()
        owner, repo = self._repo.split("/")
        log.info("GitHub", f"[{self._throttle_value}s] #{issue_id} - -label '{label}'",
                 operation="remove_label", board_id=board_id, issue_id=issue_id)
        try:
            self._gh("api", "-X", "DELETE",
                     "-H", "Accept: application/vnd.github+json",
                     f"/repos/{owner}/{repo}/issues/{issue_id}/labels/{label}")
        except Exception as e:
            # 404 se a label não está na issue - ignora
            log.info("GitHub", f"#{issue_id} - label '{label}' não removida: {e}")

    # ── Arquivamento (ProjectV2 item) ─────────────────────────────────────────

    def archive_issue(self, board_id: str, issue_id: str) -> None:
        self._penalty_check()
        meta = self._board_meta(board_id)
        item_id = self._find_item_id(board_id, issue_id)
        if not item_id:
            log.warning("GitHub", f"#{issue_id} não encontrada no project para arquivar")
            return
        log.info("GitHub", f"[{self._throttle_value}s] #{issue_id} - Arquivando item",
                 operation="archive_issue", board_id=board_id, issue_id=issue_id)
        self._gql(
            "mutation($pid:ID!,$itemId:ID!){archiveProjectV2Item(input:{projectId:$pid,itemId:$itemId}){item{id}}}",
            pid=meta["project_id"], itemId=item_id,
        )

    def unarchive_issue(self, board_id: str, issue_id: str) -> None:
        self._penalty_check()
        meta = self._board_meta(board_id)
        item_id = self._find_item_id(board_id, issue_id)
        if not item_id:
            # Item arquivado pode não aparecer em _find_item_id (que filtra). Ignora silenciosamente.
            return
        log.info("GitHub", f"[{self._throttle_value}s] #{issue_id} - Desarquivando item",
                 operation="unarchive_issue", board_id=board_id, issue_id=issue_id)
        self._gql(
            "mutation($pid:ID!,$itemId:ID!){unarchiveProjectV2Item(input:{projectId:$pid,itemId:$itemId}){item{id}}}",
            pid=meta["project_id"], itemId=item_id,
        )
