"""Loopback-only FastAPI adapter and production SPA server."""

from __future__ import annotations

import hmac
import ipaddress
import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi import Path as ApiPath
from fastapi import Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from hedge_fund.runtime.root import RootContext
from hedge_fund.web.schemas import (
    ApprovalRequest,
    CapabilitiesResponse,
    CredentialRequest,
    DeployRequest,
    error_payload,
    HaltRequest,
    LifecycleAcceptRequest,
    LifecyclePreviewRequest,
    MandateCreateRequest,
    MandateRevisionRequest,
    ModelRequest,
    OperationAcceptRequest,
    OperationCancelRequest,
    OperationPreviewRequest,
    PaperResumeRequest,
    PaperTickAcceptRequest,
    PaperTickPreviewRequest,
    RunnerPreviewRequest,
    RunnerStartAcceptRequest,
    RuntimeSettingsRequest,
    ValuationRefreshRequest,
)
from hedge_fund.web.services import DeskService, ServiceError

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSP = "default-src 'self'; " "script-src 'self'; " "style-src 'self' 'unsafe-inline'; " "img-src 'self' data:; " "font-src 'self'; " "connect-src 'self'; " "object-src 'none'; " "base-uri 'self'; " "frame-ancestors 'none'; " "form-action 'self'"
_MAX_REQUEST_BODY_BYTES = 1_000_000
_SESSION_COOKIE = "aihf_operator_session"
_SESSION_MAX_AGE_SECONDS = 12 * 60 * 60


class RequestBodyLimitMiddleware:
    def __init__(self, app, max_bytes: int = _MAX_REQUEST_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        length = next(
            (value for name, value in scope.get("headers", []) if name.lower() == b"content-length"),
            None,
        )
        if length is not None:
            try:
                if int(length) > self.max_bytes:
                    await self._reject(scope, send)
                    return
            except ValueError:
                pass

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                await self._reject(scope, send)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        payload = bytes(body)
        replayed = False

        async def replay_receive():
            nonlocal replayed
            if replayed:
                return {"type": "http.disconnect"}
            replayed = True
            return {"type": "http.request", "body": payload, "more_body": False}

        await self.app(scope, replay_receive, send)

    async def _reject(self, scope, send) -> None:
        response = _error_response(413, "Request body exceeds the 1 MB limit.")
        _security_headers(response, scope.get("path", ""))
        await response(scope, _empty_receive, send)


async def _empty_receive():
    return {"type": "http.disconnect"}


def create_app(
    *,
    root: str | Path,
    allow_writes: bool = False,
    network_enabled: bool = False,
    demo: bool = False,
    static_dir: str | Path | None = None,
    data_client_factory=None,
    fund_factory=None,
    root_context: RootContext | None = None,
) -> FastAPI:
    """Create a disk-backed app; reads never initialize or mutate the root."""
    service = DeskService(
        root,
        allow_writes=allow_writes,
        network_enabled=network_enabled,
        demo=demo,
        data_client_factory=data_client_factory,
        fund_factory=fund_factory,
        root_context=root_context,
    )
    token = secrets.token_urlsafe(32) if service.allow_writes or service.emergency_halt_available else None
    requested_static = Path(static_dir) if static_dir is not None else Path(__file__).with_name("static")
    static_root = requested_static.resolve() if requested_static.is_dir() else None
    app = FastAPI(
        title="AI Hedge Fund Trading Desk",
        version="1",
        openapi_url="/api/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    app.add_middleware(RequestBodyLimitMiddleware)
    app.state.service = service
    app.state.capability_token = token
    app.state.static_root = static_root
    app.state.container_observer = False
    app.state.session_signing_key = secrets.token_bytes(32)
    app.add_event_handler("shutdown", service.close)

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        host = request.headers.get("host", "")
        parsed_host = _parse_loopback_host(host)
        operator_session = _read_operator_session(
            request.cookies.get(_SESSION_COOKIE),
            app.state.session_signing_key,
        )
        request.state.operator_session = operator_session
        method = request.method.upper()
        emergency_control = not service.allow_writes and service.emergency_halt_available and method == "POST" and _is_emergency_control_path(request.url.path)
        mutation_allowed = service.allow_writes or emergency_control
        if parsed_host is None:
            response = _error_response(403, "Host must be a loopback address.")
        else:
            origin = request.headers.get("origin")
            if origin is not None and not _same_origin(origin, host, request.url.scheme):
                response = _error_response(403, "Origin must match the loopback host.")
            elif method not in _SAFE_METHODS and not mutation_allowed:
                response = _error_response(403, "Write capability is disabled for this server.", code="read-only")
            elif method not in _SAFE_METHODS and mutation_allowed and not _is_loopback_peer(request.client.host if request.client else None):
                response = _error_response(403, "Writable server requires a loopback client connection.")
            elif method not in _SAFE_METHODS and mutation_allowed and operator_session is None:
                # A server restart rotates the signing key; the browser can renew read-only and resubmit only by review.
                response = _renewable_denial("A valid server-owned operator session is required.")
            elif method not in _SAFE_METHODS and origin is None:
                response = _error_response(403, "Mutation requires a same-origin request.")
            elif method not in _SAFE_METHODS and not _valid_token(request.headers.get("x-csrf-token"), token):
                response = _renewable_denial("Mutation token is missing or invalid.")
            else:
                response = await call_next(request)
        if operator_session is None and (service.allow_writes or service.emergency_halt_available) and _is_loopback_peer(request.client.host if request.client else None) and parsed_host is not None:
            session_id = secrets.token_hex(16)
            signature = _sign_operator_session(
                session_id,
                app.state.session_signing_key,
            )
            response.set_cookie(
                _SESSION_COOKIE,
                f"{session_id}.{signature}",
                max_age=_SESSION_MAX_AGE_SECONDS,
                httponly=True,
                secure=request.url.scheme == "https",
                samesite="strict",
                path="/",
            )
        _security_headers(response, request.url.path)
        return response

    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError):
        response = _error_response(
            exc.status_code,
            exc.detail,
            code=exc.code,
            subject_id=exc.subject_id if exc.subject_id is not None else _path_subject(request),
            request_id=exc.request_id,
            current_head=exc.current_head,
            retry_policy=exc.retry_policy,
            retry_after_seconds=exc.retry_after_seconds,
        )
        if exc.retry_after_seconds is not None:
            response.headers["Retry-After"] = str(exc.retry_after_seconds)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        response = _error_response(exc.status_code, detail)
        for name, value in (exc.headers or {}).items():
            response.headers[name] = value
        return response

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(request: Request, exc: RequestValidationError):
        details = [{"loc": [_safe_loc_part(part) for part in error.get("loc", ())], "type": _safe_loc_part(error.get("type", "value_error")), "message": "Invalid request."} for error in exc.errors()]
        return _error_response(400, details, code="invalid-request", subject_id=_path_subject(request))

    @app.exception_handler(Exception)
    async def safe_unhandled_handler(request: Request, _exc: Exception):
        # Runs in ServerErrorMiddleware, outside local_boundary, so headers are applied here.
        response = _error_response(500, "Internal server error.")
        _security_headers(response, request.url.path)
        return response

    @app.get("/api/capabilities", response_model=CapabilitiesResponse)
    def capabilities():
        return service.capabilities(token)

    @app.get("/api/catalog")
    def catalog():
        return service.catalog()

    @app.get("/api/home")
    def home():
        return service.home()

    @app.get("/api/lifecycle/archives")
    def lifecycle_archives():
        return service.list_lifecycle_archives()

    @app.get("/api/lifecycle/archives/{archive_id}")
    def lifecycle_archive(archive_id: str):
        return service.get_lifecycle_archive(archive_id)

    @app.post("/api/lifecycle/preview")
    def lifecycle_preview(body: LifecyclePreviewRequest, request: Request):
        return service.create_lifecycle_preview(
            body,
            operator_session=request.state.operator_session,
        )

    @app.post("/api/lifecycle/accept", status_code=202)
    def lifecycle_accept(body: LifecycleAcceptRequest, request: Request):
        return _with_request_identity(
            lambda: service.accept_lifecycle(body, operator_session=request.state.operator_session),
            request_id=body.request_id,
            subject_id=body.archive_id or body.identity,
        )

    @app.get("/api/mandates")
    def mandates():
        return service.list_mandates()

    @app.get("/api/mandates/{name}")
    def mandate(name: str):
        return service.get_mandate(name)

    @app.post("/api/mandates", status_code=201)
    def create_mandate(request: MandateCreateRequest):
        return service.create_mandate(request.spec)

    @app.put("/api/mandates/{name}")
    def update_mandate(name: str, request: MandateRevisionRequest):
        return service.update_mandate(
            name,
            request.spec,
            expected_hash=request.expected_hash,
        )

    @app.post("/api/mandates/{name}/clone", status_code=201)
    def clone_mandate(name: str, request: MandateRevisionRequest):
        return service.clone_mandate(
            name,
            request.spec,
            expected_hash=request.expected_hash,
        )

    @app.post("/api/mandates/{name}/deploy", status_code=201)
    def deploy_mandate(name: str, request: DeployRequest):
        return service.deploy_mandate(name, request)

    @app.get("/api/paper")
    def paper():
        return service.list_paper()

    @app.get("/api/paper/{name}")
    def paper_detail(name: str):
        return service.paper_detail(name)

    @app.get("/api/paper/{name}/reconciliation")
    def paper_reconciliation(name: str):
        return service.paper_reconciliation(name)

    @app.post("/api/paper/{name}/tick/preview", status_code=201)
    def paper_tick_preview(name: str, request: PaperTickPreviewRequest, http_request: Request):
        return service.create_manual_tick_preview(
            name,
            request,
            operator_session=http_request.state.operator_session,
        )

    @app.post("/api/paper/{name}/tick", status_code=202)
    def paper_tick(name: str, request: PaperTickAcceptRequest, http_request: Request):
        return _with_request_identity(
            lambda: service.accept_manual_tick(name, request, operator_session=http_request.state.operator_session),
            request_id=request.request_id,
            subject_id=name,
        )

    @app.post("/api/paper/{name}/runner/preview", status_code=201)
    def runner_preview(name: str, request: RunnerPreviewRequest, http_request: Request):
        return service.create_runner_preview(
            name,
            request,
            operator_session=http_request.state.operator_session,
        )

    @app.post("/api/paper/{name}/runner", status_code=202)
    def runner_start(name: str, request: RunnerStartAcceptRequest, http_request: Request):
        return _with_request_identity(
            lambda: service.accept_runner_start(name, request, operator_session=http_request.state.operator_session),
            request_id=request.request_id,
            subject_id=name,
        )

    @app.get("/api/paper/{name}/runner")
    def runner_status(name: str):
        return service.runner_status(name)

    @app.post("/api/paper/{name}/runner/stop")
    def runner_stop(name: str):
        return service.stop_runner(name)

    @app.get("/api/paper/{name}/valuation")
    def paper_valuation(name: str):
        return service.get_valuation(name)

    @app.post("/api/paper/{name}/valuation")
    def refresh_paper_valuation(name: str, request: ValuationRefreshRequest):
        return service.refresh_valuation(name, request)

    @app.get("/api/paper/{name}/sessions")
    def paper_sessions(
        name: str,
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=19),
        search: str | None = Query(default=None, max_length=128),
    ):
        return service.paper_sessions(name, limit=limit, cursor=cursor, search=search)

    @app.get("/api/paper/{name}/sessions/{session}")
    def session_report(name: str, session: str):
        return service.session_report(name, session)

    @app.get("/api/paper/{name}/sessions/{session}/download")
    def session_report_download(
        name: str,
        session: str,
        expected_hash: str = Query(pattern=r"^[a-f0-9]{64}$"),
    ):
        content = service.session_report_download(name, session, expected_hash)
        filename = f"{name}-{session.replace(':', '-')}.json"
        return Response(content, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.get("/api/paper/{name}/scorecard")
    def paper_scorecard(name: str):
        return service.paper_scorecard(name)

    @app.post("/api/paper/{name}/approval")
    def approval(name: str, request: ApprovalRequest):
        return _with_request_identity(
            lambda: service.approve(name, request),
            request_id=request.request_id,
            subject_id=name,
        )

    @app.post("/api/paper/{name}/halt")
    def halt(name: str, request: HaltRequest):
        return _with_request_identity(
            lambda: service.halt_fund(name, request.reason, request.request_id),
            request_id=request.request_id,
            subject_id=name,
        )

    @app.post("/api/paper/{name}/resume")
    def resume(name: str, request: PaperResumeRequest):
        return _with_request_identity(
            lambda: service.resume_fund(name, request),
            request_id=request.request_id if request is not None else None,
            subject_id=name,
        )

    @app.get("/api/research")
    def research(
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=186),
        search: str | None = Query(default=None, max_length=128),
    ):
        return service.list_research(limit=limit, cursor=cursor, search=search)

    @app.get("/api/research/{report_id}")
    def research_report(report_id: str):
        return service.research_report(report_id)

    @app.post("/api/operations/preview", status_code=201)
    def operation_preview(request: OperationPreviewRequest, http_request: Request):
        return service.create_operation_preview(
            request,
            operator_session=http_request.state.operator_session,
        )

    @app.post("/api/operations", status_code=202)
    def accept_operation(request: OperationAcceptRequest, http_request: Request):
        return _with_request_identity(
            lambda: service.accept_operation(request, operator_session=http_request.state.operator_session),
            request_id=request.request_id,
            subject_id=request.subject_id,
        )

    @app.get("/api/operations")
    def operations(limit: int = Query(default=100, ge=1, le=100)):
        return service.list_operations(limit=limit)

    @app.get("/api/operations/by-request/{request_id}")
    def operation_by_request(
        request_id: str = ApiPath(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"),
    ):
        return service.get_operation_by_request(request_id)

    @app.get("/api/operations/{operation_id}")
    def operation(operation_id: str):
        return service.get_operation(operation_id)

    @app.post("/api/operations/{operation_id}/cancel")
    def cancel_operation(operation_id: str, request: OperationCancelRequest):
        return _with_request_identity(
            lambda: service.cancel_operation(operation_id, request),
            request_id=request.request_id,
            subject_id=operation_id,
        )

    @app.get("/api/settings")
    def settings():
        return service.settings()

    @app.put("/api/settings")
    def save_settings(request: RuntimeSettingsRequest):
        return service.save_runtime_settings(request)

    @app.get("/api/credentials/status")
    def credential_status():
        return service.credential_status()

    @app.delete("/api/credentials/runtime/{provider}")
    def revoke_runtime_credential(
        provider: str,
        expected_generation: int = Query(ge=0, le=2**31 - 1),
    ):
        return service.revoke_external_credential(
            provider,
            expected_generation=expected_generation,
        )

    @app.post("/api/settings/model")
    def set_model(request: ModelRequest):
        return service.set_model(request)

    @app.post("/api/settings/credentials")
    def set_credential(request: CredentialRequest):
        return service.set_credential(request)

    @app.delete("/api/settings/credentials/{provider}")
    def delete_credential(
        provider: str,
        expected_version: int = Query(ge=0, le=2**31 - 1),
    ):
        return service.delete_credential(provider, expected_version=expected_version)

    @app.get("/")
    def index():
        return _spa_response(app.state.static_root, "")

    @app.get("/{path:path}")
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            return _error_response(404, "Not found.")
        return _spa_response(app.state.static_root, path)

    return app


def _parse_loopback_host(value: str) -> tuple[str, int | None] | None:
    if not value or value != value.strip() or any(char in value for char in "/\\@,#"):
        return None
    try:
        parsed = urlsplit(f"//{value}")
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if hostname is None or parsed.path or parsed.query or parsed.fragment:
        return None
    if port is not None and not 1 <= port <= 65535:
        return None
    normalized = hostname.casefold()
    if normalized != "localhost":
        try:
            if not ipaddress.ip_address(normalized).is_loopback:
                return None
        except ValueError:
            return None
    return normalized, port


def _is_loopback_peer(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def _sign_operator_session(session_id: str, key: bytes) -> str:
    return hmac.new(key, session_id.encode("ascii"), "sha256").hexdigest()


def _read_operator_session(value: str | None, key: bytes) -> str | None:
    if not isinstance(value, str):
        return None
    parts = value.split(".")
    if len(parts) != 2 or not re.fullmatch(r"[a-f0-9]{32}", parts[0]):
        return None
    if not re.fullmatch(r"[a-f0-9]{64}", parts[1]):
        return None
    expected = _sign_operator_session(parts[0], key)
    return parts[0] if hmac.compare_digest(parts[1], expected) else None


def _same_origin(origin: str, host: str, request_scheme: str) -> bool:
    try:
        parsed = urlsplit(origin)
        origin_host = _parse_loopback_host(parsed.netloc)
    except ValueError:
        return False
    request_host = _parse_loopback_host(host)
    if origin_host is None or request_host is None:
        return False
    if parsed.scheme != request_scheme or parsed.path or parsed.query or parsed.fragment:
        return False
    scheme_default = 443 if parsed.scheme == "https" else 80
    return (origin_host[0], origin_host[1] or scheme_default) == (
        request_host[0],
        request_host[1] or scheme_default,
    )


def _valid_token(supplied: str | None, expected: str | None) -> bool:
    return supplied is not None and expected is not None and hmac.compare_digest(supplied, expected)


def _is_emergency_control_path(value: str) -> bool:
    parts = value.split("/")
    return len(parts) == 5 and parts[0] == "" and parts[1] == "api" and parts[2] == "paper" and bool(parts[3]) and parts[4] in {"halt", "resume"}


_SAFE_LOC_PART = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}")


def _safe_loc_part(part):
    """Echo only bounded identifiers or indexes; request-supplied keys stay inert."""
    if type(part) is int:
        return part
    if isinstance(part, str) and _SAFE_LOC_PART.fullmatch(part):
        return part
    return "<redacted>"


def _error_response(status_code: int, detail, *, code: str | None = None, **identity) -> JSONResponse:
    return JSONResponse(error_payload(status_code, detail, code=code, **identity), status_code=status_code)


def _renewable_denial(detail: str) -> JSONResponse:
    """Session/token denial after restart or expiry: renew via read-only capabilities, never auto-resubmit."""
    return _error_response(403, detail, refresh_required=True, retry_policy="reload")


_SUBJECT_PATH_PARAMS = ("operation_id", "archive_id", "report_id", "name")


def _path_subject(request: Request) -> str | None:
    params = request.path_params or {}
    for key in _SUBJECT_PATH_PARAMS:
        value = params.get(key)
        if value is not None:
            return value
    return None


def _with_request_identity(call, *, request_id: str, subject_id: str | None = None):
    try:
        return call()
    except ServiceError as exc:
        raise exc.attach(subject_id=subject_id, request_id=request_id)


def _security_headers(response: Response, path: str) -> None:
    response.headers["Content-Security-Policy"] = _CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"


def _spa_response(static_root: Path | None, relative: str) -> Response:
    if static_root is None:
        return _error_response(503, "Frontend build is missing; run npm --prefix frontend ci and npm --prefix frontend run build.")
    if relative:
        candidate = static_root.joinpath(*Path(relative).parts)
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            resolved = None
        if resolved is not None and resolved != static_root and static_root in resolved.parents and resolved.is_file():
            return FileResponse(resolved)
        if relative.startswith("assets/"):
            return _error_response(404, "Asset not found.")
    index = static_root / "index.html"
    if not index.is_file() or index.is_symlink():
        return _error_response(503, "Frontend build is missing its index.")
    return FileResponse(index)
