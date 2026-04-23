"""
Persistent repository metadata storage.

ChromaDB stores the searchable code chunks, but the UI also needs stable
repository metadata such as the project name, URL, language stats, file tree,
and generated diagrams after the API process restarts.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from config import settings
from models.schemas import Diagram, RepoInfo

logger = logging.getLogger(__name__)

_SAFE_REPO_ID = re.compile(r"^[a-zA-Z0-9_-]{3,64}$")


def _base_dir() -> Path:
    path = Path(settings.repo_metadata_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _repo_dir(repo_id: str, *, create: bool = False) -> Path:
    if not _SAFE_REPO_ID.match(repo_id):
        raise ValueError(f"Invalid repository id: {repo_id}")

    path = _base_dir() / repo_id
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _repo_info_path(repo_id: str) -> Path:
    return _repo_dir(repo_id) / "info.json"


def _diagrams_path(repo_id: str) -> Path:
    return _repo_dir(repo_id) / "diagrams.json"


def save_repo_info(info: RepoInfo) -> None:
    """Persist analyzed repository metadata for recovery after restarts."""
    path = _repo_dir(info.repo_id, create=True) / "info.json"
    path.write_text(
        json.dumps(info.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    logger.info("Saved repo metadata for %s to %s", info.repo_id, path)


def load_repo_info(repo_id: str) -> RepoInfo | None:
    """Load persisted repository metadata, if present."""
    try:
        path = _repo_info_path(repo_id)
    except ValueError:
        return None

    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return RepoInfo.model_validate(data)
    except Exception as exc:
        logger.warning("Could not load repo metadata for %s: %s", repo_id, exc)
        return None


def save_diagrams(repo_id: str, diagrams: list[Diagram]) -> None:
    """Persist generated diagrams so the diagrams tab survives restarts."""
    path = _repo_dir(repo_id, create=True) / "diagrams.json"
    data = [diagram.model_dump(mode="json") for diagram in diagrams]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Saved %d diagrams for %s to %s", len(diagrams), repo_id, path)


def load_diagrams(repo_id: str) -> list[Diagram]:
    """Load persisted diagrams, if present."""
    try:
        path = _diagrams_path(repo_id)
    except ValueError:
        return []

    if not path.is_file():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [Diagram.model_validate(item) for item in data]
    except Exception as exc:
        logger.warning("Could not load diagrams for %s: %s", repo_id, exc)
        return []


def delete_repo_metadata(repo_id: str) -> None:
    """Delete all persisted metadata for a repository."""
    try:
        path = _repo_dir(repo_id)
    except ValueError:
        return

    if not path.is_dir():
        return

    for child in path.iterdir():
        if child.is_file():
            child.unlink(missing_ok=True)
    path.rmdir()
