"""Loopback-only FastAPI adapter and production SPA server."""

from __future__ import annotations

import hmac
import ipaddress
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response

from hedge_fund.paths import USER_DIR
from hedge_fund.web.schemas import (
    ApprovalRequest,
    BacktestRequest,
    CapabilitiesResponse,
    CredentialRequest,
    DeployRequest,
    HaltRequest,
    MandateCreateRequest,
    ModelRequest,
)
from hedge_fund.web.services import DeskService, ServiceError

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSP = "default-src 'self'; " "script-src 'self'; " "style-src 'self' 'unsafe-inline'; " "img-src 'self' data:; " "font-src 'self'; " "connect-src 'self'; " "object-src 'none'; " "base-uri 'self'; " "frame-ancestors 'none'; " "form-action 'self'"


def create_app(
    *,
    root: str | Path = USER_DIR,
    allow_writes: bool = False,
    network_enabled: bool = False,
    demo: bool = False,
    static_dir: str | Path | None = None,
    data_client_factory=None,
    fund_factory=None,
) -> FastAPI:
    """Create a disk-backed app; reads never initialize or mutate the root."""
    service = DeskService(
        root,
        allow_writes=allow_writes,
        network_enabled=network_enabled,
        demo=demo,
        data_client_factory=data_client_factory,
        fund_factory=fund_factory,
    )
    token = secrets.token_urlsafe(32) if allow_writes else None
    requested_static = Path(static_dir) if static_dir is not None else Path(__file__).with_name("static")
    static_root = requested_static.resolve() if requested_static.is_dir() else None
    app = FastAPI(
        title="AI Hedge Fund Trading Desk",
        version="1",
        openapi_url="/api/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    app.state.service = service
    app.state.capability_token = token
    app.state.static_root = static_root
    app.add_event_handler("shutdown", service.close)

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        host = request.headers.get("host", "")
        parsed_host = _parse_loopback_host(host)
        if parsed_host is None:
            response = JSONResponse({"detail": "Host must be a loopback address."}, status_code=403)
        else:
            origin = request.headers.get("origin")
            if origin is not None and not _same_origin(origin, host, request.url.scheme):
                response = JSONResponse({"detail": "Origin must match the loopback host."}, status_code=403)
            elif request.method.upper() not in _SAFE_METHODS and not allow_writes:
                response = JSONResponse({"detail": "Write capability is disabled for this server."}, status_code=403)
            elif request.method.upper() not in _SAFE_METHODS and origin is None:
                response = JSONResponse({"detail": "Mutation requires a same-origin request."}, status_code=403)
            elif request.method.upper() not in _SAFE_METHODS and not _valid_token(request.headers.get("x-csrf-token"), token):
                response = JSONResponse({"detail": "Mutation token is missing or invalid."}, status_code=403)
            else:
                content_length = request.headers.get("content-length")
                if content_length is not None and content_length.isdigit() and int(content_length) > 1_000_000:
                    response = JSONResponse({"detail": "Request body exceeds the 1 MB limit."}, status_code=413)
                else:
                    response = await call_next(request)
        response.headers["Content-Security-Policy"] = _CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ServiceError)
    async def service_error_handler(_request: Request, exc: ServiceError):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_request: Request, exc: RequestValidationError):
        details = [{"loc": list(error.get("loc", ())), "type": error.get("type", "value_error"), "message": "Invalid request."} for error in exc.errors()]
        return JSONResponse({"detail": details}, status_code=422)

    @app.exception_handler(Exception)
    async def safe_unhandled_handler(_request: Request, _exc: Exception):
        return JSONResponse({"detail": "Internal server error."}, status_code=500)

    @app.get("/api/capabilities", response_model=CapabilitiesResponse)
    def capabilities():
        return service.capabilities(token)

    @app.get("/api/catalog")
    def catalog():
        return service.catalog()

    @app.get("/api/home")
    def home():
        return service.home()

    @app.get("/api/mandates")
    def mandates():
        return service.list_mandates()

    @app.get("/api/mandates/{name}")
    def mandate(name: str):
        return service.get_mandate(name)

    @app.post("/api/mandates", status_code=201)
    def create_mandate(request: MandateCreateRequest):
        return service.create_mandate(request.spec)

    @app.post("/api/mandates/{name}/deploy", status_code=201)
    def deploy_mandate(name: str, request: DeployRequest):
        return service.deploy_mandate(name, request)

    @app.get("/api/paper")
    def paper():
        return service.list_paper()

    @app.get("/api/paper/{name}")
    def paper_detail(name: str):
        return service.paper_detail(name)

    @app.get("/api/paper/{name}/sessions")
    def paper_sessions(name: str):
        detail = service.paper_detail(name)
        return {"items": detail["sessions"], "ledger": detail["ledger"]}

    @app.get("/api/paper/{name}/sessions/{session}")
    def session_report(name: str, session: str):
        return service.session_report(name, session)

    @app.get("/api/paper/{name}/scorecard")
    def paper_scorecard(name: str):
        return service.paper_scorecard(name)

    @app.post("/api/paper/{name}/approval")
    def approval(name: str, request: ApprovalRequest):
        return service.approve(name, request)

    @app.post("/api/paper/{name}/halt")
    def halt(name: str, request: HaltRequest):
        return service.halt_fund(name, request.reason)

    @app.post("/api/paper/{name}/resume")
    def resume(name: str):
        return service.resume_fund(name)

    @app.get("/api/research")
    def research():
        return service.list_research()

    @app.get("/api/research/{report_id}")
    def research_report(report_id: str):
        return service.research_report(report_id)

    @app.post("/api/backtests", status_code=202)
    def start_backtest(request: BacktestRequest):
        return service.submit_backtest(request)

    @app.get("/api/jobs")
    def jobs():
        return service.list_jobs()

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        return service.get_job(job_id)

    @app.get("/api/settings")
    def settings():
        return service.settings()

    @app.post("/api/settings/model")
    def set_model(request: ModelRequest):
        return service.set_model(request)

    @app.post("/api/settings/credentials")
    def set_credential(request: CredentialRequest):
        return service.set_credential(request)

    @app.get("/")
    def index():
        return _spa_response(app.state.static_root, "")

    @app.get("/{path:path}")
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            return JSONResponse({"detail": "Not found."}, status_code=404)
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


def _spa_response(static_root: Path | None, relative: str) -> Response:
    if static_root is None:
        return JSONResponse(
            {"detail": "Frontend build is missing; run npm --prefix frontend ci and npm --prefix frontend run build."},
            status_code=503,
        )
    if relative:
        candidate = static_root.joinpath(*Path(relative).parts)
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            resolved = None
        if resolved is not None and resolved != static_root and static_root in resolved.parents and resolved.is_file():
            return FileResponse(resolved)
        if Path(relative).suffix:
            return JSONResponse({"detail": "Asset not found."}, status_code=404)
    index = static_root / "index.html"
    if not index.is_file() or index.is_symlink():
        return JSONResponse({"detail": "Frontend build is missing its index."}, status_code=503)
    return FileResponse(index)
