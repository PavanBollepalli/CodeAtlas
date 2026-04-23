"""
CodeAtlas Backend Configuration.

All settings are loaded from environment variables (or .env file).
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── LLM ────────────────────────────────────────────────────
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # ── Storage ────────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_data"
    clone_dir: str = "./cloned_repos"
    repo_metadata_dir: str = "./repo_metadata"

    # ── Limits ─────────────────────────────────────────────────
    max_repo_size_mb: int = 100
    max_files: int = 5000

    # ── Chunking ───────────────────────────────────────────────
    max_chunk_chars: int = 1500
    chunk_overlap: int = 200

    # ── RAG ────────────────────────────────────────────────────
    top_k: int = 10

    # ── Server ─────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
