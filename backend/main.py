"""
CodeAtlas Backend — FastAPI Application Entry Point.

Initializes the FastAPI app, mounts routes, configures CORS,
and sets up logging.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routes import chat, diagrams, repo

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-28s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)

# Suppress noisy loggers
logging.getLogger("chromadb").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    logger.info(">>> CodeAtlas Backend starting up")
    logger.info("   Groq model : %s", settings.groq_model)
    logger.info("   ChromaDB   : %s", settings.chroma_persist_dir)
    logger.info("   Clone dir  : %s", settings.clone_dir)
    logger.info("   CORS       : %s", settings.cors_origins)
    yield
    logger.info("<<< CodeAtlas Backend shutting down")


# ── FastAPI App ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="CodeAtlas API",
    description="GitHub Repository Analyzer & UML Diagram Generator",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ─────────────────────────────────────────────────────────────────────

app.include_router(repo.router)
app.include_router(chat.router)
app.include_router(diagrams.router)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "CodeAtlas API",
        "version": "0.1.0",
        "status": "operational",
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    return {
        "status": "healthy",
        "groq_configured": bool(settings.groq_api_key),
        "model": settings.groq_model,
    }


# ── Development Server ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_excludes=[
            "cloned_repos/*",
            "chroma_data/*",
            "repo_metadata/*",
            ".venv/*",
        ],
    )
