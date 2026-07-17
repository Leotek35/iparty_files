"""FastAPI application factory."""
from __future__ import annotations

from pathlib import Path

import math

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..core.config import settings
from .events import router as events_router
from .routes import router

WEB_DIR = Path(__file__).resolve().parents[3] / "web"


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION,
                  description="Verifier-gated party planning on the TTL reliability engine.")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(router, prefix="/api/v1")
    app.include_router(events_router, prefix="/api/v1")

    @app.exception_handler(RequestValidationError)
    async def _safe_validation_handler(request: Request, exc: RequestValidationError):
        # FastAPI's default handler json.dumps the offending input verbatim; a
        # non-finite float (NaN/Infinity) then raises inside the handler and
        # returns a 500 with a stack trace. Scrub non-JSON-safe values so a
        # crafted body can never crash the process or leak internals.
        def _clean(o):
            if isinstance(o, float) and not math.isfinite(o):
                return str(o)
            if isinstance(o, dict):
                return {k: _clean(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [_clean(v) for v in o]
            return o
        errors = [{k: _clean(v) for k, v in e.items() if k != "ctx"} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        # Defense-in-depth for the client: even if an unescaped value slips
        # through, inline-script injection is blocked. 'unsafe-inline' is kept
        # for the single-file styles/handlers this app ships.
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'"
        )
        return resp

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "version": settings.APP_VERSION, "backend": settings.LLM_BACKEND}

    if WEB_DIR.exists():
        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

        app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    return app


app = create_app()
