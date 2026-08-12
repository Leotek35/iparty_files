"""FastAPI application factory."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..core.config import settings
from .bookings import router as bookings_router
from .events import router as events_router
from .routes import router
from .vendors import router as vendors_router

WEB_DIR = Path(__file__).resolve().parents[3] / "web"


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION,
                  description="Verifier-gated party planning on the TTL reliability engine.")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(router, prefix="/api/v1")
    app.include_router(events_router, prefix="/api/v1")
    app.include_router(bookings_router, prefix="/api/v1")
    app.include_router(vendors_router, prefix="/api/v1")

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Inline <style>/<script> in the single-file UI require 'unsafe-inline';
        # everything else is locked to same-origin. object/base/frame denied.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        )
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

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
