"""FastAPI application entrypoint.

Kept intentionally small: create the app, wire up the database, mount the
router. All actual logic lives in app/api, app/services, app/agent, and
app/tools — this file's only job is to assemble them.
"""

import logging

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.database import init_db

settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title="Agent Checker",
    description=(
        "Verifies claims against on-chain data (The Graph) and a GRC-20 "
        "knowledge graph, with full evidence trails."
    ),
    version="0.1.0",
)


@app.on_event("startup")
def on_startup() -> None:
    """Create database tables before serving any requests."""
    init_db()


@app.get("/health")
def health() -> dict:
    """Report basic liveness and which data source the app is running against."""
    return {"status": "ok", "data_source": settings.data_source}


app.include_router(router)
