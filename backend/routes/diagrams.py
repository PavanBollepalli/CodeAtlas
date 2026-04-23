"""
Diagram Generation Routes.

POST /api/diagrams/{repo_id}/generate  — Generate diagrams
GET  /api/diagrams/{repo_id}           — Get cached diagrams
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from models.schemas import AnalysisStatus, Diagram, DiagramGenerateRequest, DiagramType
from services.diagram_generator import generate_all_diagrams
from services.repo_store import load_diagrams, save_diagrams

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diagrams", tags=["diagrams"])

# ── In-Memory Diagram Cache ───────────────────────────────────────────────────
diagram_cache: dict[str, list[Diagram]] = {}


def _get_repo_state(repo_id: str) -> dict[str, Any]:
    """Validate that the repo exists and is ready."""
    from routes.repo import _recover_repo_state, repo_states

    state = repo_states.get(repo_id)
    if state is None:
        state = _recover_repo_state(repo_id)

    if state is None:
        raise HTTPException(status_code=404, detail=f"Repository {repo_id} not found")

    if state["status"] != AnalysisStatus.READY:
        raise HTTPException(
            status_code=409,
            detail=f"Repository is not ready. Status: {state['status']}",
        )

    return state


@router.post("/{repo_id}/generate")
async def generate_diagrams(
    repo_id: str,
    request: DiagramGenerateRequest | None = None,
):
    """
    Generate architecture diagrams for an analyzed repository.

    Generates Mermaid.js syntax for the requested diagram types.
    Results are cached per repo_id.
    """
    _get_repo_state(repo_id)

    diagram_types = (
        request.types if request
        else [DiagramType.CLASS, DiagramType.DEPENDENCY, DiagramType.ARCHITECTURE]
    )

    try:
        diagrams = await generate_all_diagrams(repo_id, diagram_types)
        diagram_cache[repo_id] = diagrams
        save_diagrams(repo_id, diagrams)
        return {"repo_id": repo_id, "diagrams": [d.model_dump() for d in diagrams]}
    except Exception as exc:
        logger.error("Diagram generation failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate diagrams: {str(exc)}",
        )


@router.get("/{repo_id}")
async def get_diagrams(repo_id: str):
    """Get cached diagrams for a repository. Returns empty list if not yet generated."""
    _get_repo_state(repo_id)

    diagrams = diagram_cache.get(repo_id)
    if diagrams is None:
        diagrams = load_diagrams(repo_id)
        if diagrams:
            diagram_cache[repo_id] = diagrams
    return {"repo_id": repo_id, "diagrams": [d.model_dump() for d in diagrams]}
