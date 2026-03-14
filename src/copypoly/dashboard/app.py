"""Dashboard FastAPI application.

Serves the REST API and the static SPA frontend.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from copypoly.dashboard.api import router as api_router
from copypoly.dashboard.routes_performance import router as perf_router

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    """Create and configure the FastAPI dashboard app."""
    app = FastAPI(
        title="CopyPoly Dashboard",
        description="Polymarket Copy Trading Dashboard",
        version="0.1.0",
    )

    # CORS (allow all for local dev)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(api_router)
    app.include_router(perf_router)

    # Serve static frontend
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"message": "CopyPoly API", "docs": "/docs"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


dashboard_app = create_app()
