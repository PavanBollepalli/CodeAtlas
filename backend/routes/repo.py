"""
Repository Analysis Routes.

POST /api/repo/analyze     — Start analyzing a repository
GET  /api/repo/{id}/status — Get analysis progress
GET  /api/repo/{id}/info   — Get repo metadata and stats
DELETE /api/repo/{id}      — Clean up repo data
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from config import settings
from models.schemas import (
    AnalysisStatus,
    RepoAnalyzeRequest,
    RepoInfo,
    RepoStatusResponse,
)
from services.chunker import chunk_repository
from services.cloner import (
    CloneError,
    InvalidRepoURLError,
    RepoNotFoundError,
    RepoTooLargeError,
    cleanup_repository,
    clone_repository,
    fetch_repo_metadata,
    validate_github_url,
)
from services.repo_store import delete_repo_metadata, load_repo_info, save_repo_info
from services.vector_store import delete_collection, get_collection_info, store_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/repo", tags=["repository"])

# ── In-Memory State ───────────────────────────────────────────────────────────
# Stores analysis state per repo_id. In production, this would be a database.

repo_states: dict[str, dict[str, Any]] = {}


def _repo_identity_from_clone(clone_path: Path, fallback_name: str) -> tuple[str, str]:
    """Infer repo name and URL from the cloned repository's Git config."""
    config_path = clone_path / ".git" / "config"
    if not config_path.is_file():
        return fallback_name, ""

    try:
        config_text = config_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return fallback_name, ""

    match = re.search(r"^\s*url\s*=\s*(?P<url>\S+)\s*$", config_text, re.MULTILINE)
    if not match:
        return fallback_name, ""

    url = match.group("url")
    repo_name = url.rstrip("/").removesuffix(".git").split("/")[-1] or fallback_name
    return repo_name, url


def _recover_repo_state(repo_id: str) -> dict[str, Any] | None:
    """
    If the server restarted (e.g., --reload), the in-memory state is lost.
    Restore the full repo metadata from disk, then fall back to ChromaDB for
    older analyses that were created before metadata persistence existed.
    """
    from services.chunker import chunk_repository

    saved_info = load_repo_info(repo_id)
    if saved_info is not None:
        recovered = {
            "status": AnalysisStatus.READY,
            "progress": "Analysis complete (recovered)",
            "error": None,
            "url": saved_info.url,
            "info": saved_info,
        }
        repo_states[repo_id] = recovered
        logger.info("Recovered state for repo %s from persisted metadata", repo_id)
        return recovered

    collection_info = get_collection_info(repo_id)
    if collection_info is None:
        return None

    # Try to rebuild file tree and languages from the cloned repo on disk
    clone_path = Path(settings.clone_dir) / repo_id
    file_tree = None
    languages: list = []
    total_files = 0
    repo_name = collection_info.get("name", repo_id)
    repo_url = collection_info.get("url", "")

    if clone_path.is_dir():
        inferred_name, inferred_url = _repo_identity_from_clone(clone_path, repo_name)
        repo_name = inferred_name
        repo_url = inferred_url or repo_url
        try:
            chunk_result = chunk_repository(str(clone_path))
            file_tree = chunk_result.file_tree
            languages = chunk_result.languages
            total_files = chunk_result.total_files
            logger.info("Rebuilt file tree for repo %s from disk (%d files)", repo_id, total_files)
        except Exception as exc:
            logger.warning("Could not rebuild file tree for %s: %s", repo_id, exc)

    # Reconstruct RepoInfo
    recovered = {
        "status": AnalysisStatus.READY,
        "progress": "Analysis complete (recovered)",
            "error": None,
        "url": repo_url,
        "info": RepoInfo(
            repo_id=repo_id,
            name=repo_name,
            url=repo_url,
            total_files=total_files or collection_info.get("total_files", 0),
            total_chunks=collection_info.get("total_chunks", 0),
            languages=languages,
            file_tree=file_tree,
            analyzed_at=collection_info.get("analyzed_at", datetime.now(timezone.utc).isoformat()),
        ),
    }

    # Cache it so subsequent requests don't need to rebuild
    repo_states[repo_id] = recovered
    save_repo_info(recovered["info"])
    logger.info(
        "Recovered state for repo %s from ChromaDB (%d chunks)",
        repo_id,
        collection_info.get("total_chunks", 0),
    )
    return recovered


# ── Background Task ───────────────────────────────────────────────────────────


def _process_repository(repo_id: str, url: str) -> None:
    """
    Background task that runs the full analysis pipeline:
    clone → parse → chunk → embed → ready.
    """
    try:
        # ── Step 1: Clone ──────────────────────────────────────────
        repo_states[repo_id]["status"] = AnalysisStatus.CLONING
        repo_states[repo_id]["progress"] = "Cloning repository..."

        clone_result = clone_repository(url, repo_id=repo_id)

        # ── Step 2: Parse & Chunk ──────────────────────────────────
        repo_states[repo_id]["status"] = AnalysisStatus.PARSING
        repo_states[repo_id]["progress"] = "Parsing source files..."

        chunk_result = chunk_repository(clone_result.clone_path)

        # ── Step 3: Embed & Store ──────────────────────────────────
        repo_states[repo_id]["status"] = AnalysisStatus.EMBEDDING
        repo_states[repo_id]["progress"] = (
            f"Embedding {len(chunk_result.chunks)} code chunks..."
        )

        stored_count = store_chunks(repo_id, chunk_result.chunks)

        # ── Step 4: Build Info ─────────────────────────────────────
        # Extract repo name from URL
        parts = url.rstrip("/").split("/")
        repo_name = parts[-1].replace(".git", "") if parts else repo_id

        info = RepoInfo(
            repo_id=repo_id,
            name=repo_name,
            url=url,
            total_files=chunk_result.total_files,
            total_chunks=stored_count,
            languages=chunk_result.languages,
            file_tree=chunk_result.file_tree,
            analyzed_at=datetime.now(timezone.utc).isoformat(),
        )

        repo_states[repo_id]["status"] = AnalysisStatus.READY
        repo_states[repo_id]["progress"] = "Analysis complete"
        repo_states[repo_id]["info"] = info
        save_repo_info(info)

        logger.info(
            "Analysis complete for %s: %d files, %d chunks",
            repo_id, chunk_result.total_files, stored_count,
        )

    except Exception as exc:
        logger.error("Analysis failed for %s: %s", repo_id, exc, exc_info=True)
        repo_states[repo_id]["status"] = AnalysisStatus.ERROR
        repo_states[repo_id]["error"] = str(exc)
        repo_states[repo_id]["progress"] = "Analysis failed"

        # Clean up on failure
        try:
            cleanup_repository(repo_id)
            delete_collection(repo_id)
        except Exception:
            pass


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/analyze")
async def analyze_repo(
    request: RepoAnalyzeRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start analyzing a public GitHub repository.

    Validates the URL, checks repo size via GitHub API,
    then kicks off the analysis pipeline in the background.
    """
    url = request.url.strip()

    # Validate URL format
    try:
        owner, repo_name = validate_github_url(url)
    except InvalidRepoURLError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Check repo metadata (size, existence)
    try:
        metadata = await fetch_repo_metadata(owner, repo_name)
    except RepoNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RepoTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc))

    # Generate repo ID and initialize state
    repo_id = uuid.uuid4().hex[:12]
    repo_states[repo_id] = {
        "status": AnalysisStatus.QUEUED,
        "progress": "Queued for analysis",
        "info": None,
        "error": None,
        "url": url,
        "metadata": metadata,
    }

    # Start background analysis
    background_tasks.add_task(_process_repository, repo_id, url)

    return {
        "repo_id": repo_id,
        "status": AnalysisStatus.QUEUED,
        "message": f"Analysis started for {owner}/{repo_name}",
    }


@router.get("/{repo_id}/status")
async def get_repo_status(repo_id: str):
    """Get the current analysis status for a repository."""
    state = repo_states.get(repo_id)

    # Fallback: try to recover from ChromaDB if in-memory state was lost
    if state is None:
        state = _recover_repo_state(repo_id)

    if state is None:
        raise HTTPException(status_code=404, detail=f"Repository {repo_id} not found")

    return RepoStatusResponse(
        repo_id=repo_id,
        status=state["status"],
        progress=state.get("progress"),
        info=state.get("info"),
        error=state.get("error"),
    )


@router.get("/{repo_id}/info")
async def get_repo_info(repo_id: str):
    """Get full repository info (only available after analysis is complete)."""
    state = repo_states.get(repo_id)

    # Fallback: try to recover from ChromaDB if in-memory state was lost
    if state is None:
        state = _recover_repo_state(repo_id)

    if state is None:
        raise HTTPException(status_code=404, detail=f"Repository {repo_id} not found")

    if state["status"] != AnalysisStatus.READY:
        raise HTTPException(
            status_code=409,
            detail=f"Analysis is not complete. Current status: {state['status']}",
        )

    info = state.get("info")
    if info is None:
        raise HTTPException(status_code=500, detail="Repository info not available")

    return info


@router.delete("/{repo_id}")
async def delete_repo(repo_id: str):
    """Clean up all data for a repository (cloned files + vector store)."""
    state = repo_states.get(repo_id)
    if state is None:
        state = _recover_repo_state(repo_id)

    if state is None:
        raise HTTPException(status_code=404, detail=f"Repository {repo_id} not found")

    # Clean up
    cleanup_repository(repo_id)
    delete_collection(repo_id)
    delete_repo_metadata(repo_id)
    repo_states.pop(repo_id, None)

    return {"message": f"Repository {repo_id} deleted successfully"}
