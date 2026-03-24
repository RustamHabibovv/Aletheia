"""Aletheia FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Aletheia backend starting up")
    # Auto-create tables only for local dev/testing (skipped when using Alembic migrations)
    if settings.auto_create_tables:
        from sqlmodel import SQLModel

        from app.db.session import engine
        from app.models import models  # noqa: F401 — import to register tables

        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("Tables auto-created (AUTO_CREATE_TABLES=true)")
    yield
    logger.info("Aletheia backend shutting down")


app = FastAPI(
    title="Aletheia API",
    description="AI-powered fact verification, source checking, and misinformation detection.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(v1_router)


@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint for uptime monitoring."""
    return {"status": "healthy", "version": "0.1.0"}
