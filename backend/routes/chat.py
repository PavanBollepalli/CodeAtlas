"""
Chat / Q&A Routes.

POST /api/chat/{repo_id}          — Ask a question (SSE streaming)
POST /api/chat/{repo_id}/sync     — Ask a question (full response)
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

from models.schemas import AnalysisStatus, ChatRequest
from services.rag import answer_question, stream_answer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _get_repo_state(repo_id: str) -> dict[str, Any]:
    """Validate that the repo exists and is ready for queries."""
    # Import here to avoid circular imports
    from routes.repo import _recover_repo_state, repo_states

    state = repo_states.get(repo_id)
    if state is None:
        state = _recover_repo_state(repo_id)

    if state is None:
        raise HTTPException(status_code=404, detail=f"Repository {repo_id} not found")

    if state["status"] != AnalysisStatus.READY:
        raise HTTPException(
            status_code=409,
            detail=f"Repository is not ready for queries. Status: {state['status']}",
        )

    return state


@router.post("/{repo_id}")
async def chat_stream(repo_id: str, request: ChatRequest):
    """
    Ask a question about a repository (SSE streaming response).

    Returns a Server-Sent Events stream with:
      - `citations`: Source code references
      - `token`: Individual response tokens
      - `done`: Completion signal
    """
    _get_repo_state(repo_id)

    return StreamingResponse(
        stream_answer(repo_id, request.message, request.history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{repo_id}/sync")
async def chat_sync(repo_id: str, request: ChatRequest):
    """
    Ask a question about a repository (full JSON response).

    Use this endpoint when you don't need streaming.
    """
    _get_repo_state(repo_id)

    response = await answer_question(repo_id, request.message, request.history)
    return response
