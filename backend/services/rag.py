"""
RAG (Retrieval-Augmented Generation) Pipeline.

Retrieves relevant code chunks from the vector store, constructs a
context-aware prompt, and generates answers using Groq (Llama 3.3 70B).
Supports both full responses and SSE streaming.
"""

import json
import logging
from typing import AsyncGenerator

from groq import AsyncGroq

from config import settings
from models.schemas import ChatResponse, SourceCitation
from services.vector_store import RetrievedChunk, query_chunks

logger = logging.getLogger(__name__)

# ── Groq Client ────────────────────────────────────────────────────────────────

_async_client: AsyncGroq | None = None


def _get_async_client() -> AsyncGroq:
    """Get or create the async Groq client."""
    global _async_client
    if _async_client is None:
        if not settings.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. "
                "Please set it in your .env file or environment variables."
            )
        _async_client = AsyncGroq(api_key=settings.groq_api_key)
    return _async_client


# ── System Prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are CodeAtlas, a sharp code analysis assistant. You answer questions about codebases concisely and precisely.

Rules:
- Be CONCISE. Get to the point fast. No filler, no fluff, no "In conclusion" paragraphs.
- Lead with the answer, then support with code.
- Show relevant code snippets using fenced code blocks with the correct language tag.
- Reference files as inline code like `path/to/file.py`.
- Use short bullet points over long paragraphs.
- Skip generic explanations of well-known patterns — focus on what THIS codebase does specifically.
- If context is insufficient, say so in one line.
- Never repeat the question back. Never add a closing summary paragraph.
- Keep total response under 300 words unless code snippets make it longer."""


# ── Context Builder ────────────────────────────────────────────────────────────


def _build_context(chunks: list[RetrievedChunk]) -> str:
    """Build a context string from retrieved chunks for the LLM prompt."""
    if not chunks:
        return "No relevant code chunks were found for this query."

    parts = []
    for i, chunk in enumerate(chunks, 1):
        header = (
            f"--- Source #{i}: {chunk.file_path} "
            f"(L{chunk.start_line}-{chunk.end_line}) "
            f"[{chunk.chunk_type}: {chunk.qualified_name}] ---"
        )
        parts.append(f"{header}\n{chunk.source_code}")

    return "\n\n".join(parts)


def _build_messages(
    question: str,
    context: str,
    history: list[dict],
) -> list[dict]:
    """Build the message list for the Groq API call."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add chat history (limited to last 10 exchanges to stay within context limits)
    recent_history = history[-20:]  # 20 messages = 10 exchanges
    for msg in recent_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    # Add the current query with context
    user_message = f"""Code context from the repo:

{context}

Question: {question}

Answer concisely. Show relevant code. Reference file paths."""

    messages.append({"role": "user", "content": user_message})
    return messages


# ── Public API ─────────────────────────────────────────────────────────────────


async def answer_question(
    repo_id: str,
    question: str,
    history: list[dict] | None = None,
) -> ChatResponse:
    """
    Answer a question about a repository using RAG.

    1. Retrieve top-k relevant chunks from ChromaDB
    2. Build context-enriched prompt
    3. Call Groq for generation
    4. Return answer with source citations

    Args:
        repo_id: Repository identifier.
        question: User's question.
        history: Previous chat messages.

    Returns:
        ChatResponse with answer and citations.
    """
    if history is None:
        history = []

    # 1. Retrieve context
    retrieved = query_chunks(repo_id, question)
    context = _build_context(retrieved)
    messages = _build_messages(question, context, history)

    # 2. Generate answer
    try:
        client = _get_async_client()
        completion = await client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            temperature=0.3,
            max_tokens=4096,
        )
        answer = completion.choices[0].message.content or ""
    except Exception as exc:
        logger.error("Groq API call failed: %s", exc)
        answer = f"I encountered an error while generating the answer: {str(exc)}"

    # 3. Build citations
    citations = [chunk.to_citation() for chunk in retrieved[:5]]

    return ChatResponse(answer=answer, citations=citations)


async def stream_answer(
    repo_id: str,
    question: str,
    history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Stream an answer using Server-Sent Events format.

    Yields SSE-formatted strings: `data: {"type": ..., "content": ...}\n\n`

    Event types:
        - "citation": Source citations (sent first)
        - "token": Individual response tokens
        - "done": Completion signal
        - "error": Error message
    """
    if history is None:
        history = []

    try:
        # 1. Retrieve context
        retrieved = query_chunks(repo_id, question)
        context = _build_context(retrieved)
        messages = _build_messages(question, context, history)

        # 2. Send citations first
        citations = [chunk.to_citation().model_dump() for chunk in retrieved[:5]]
        yield f"data: {json.dumps({'type': 'citations', 'content': citations})}\n\n"

        # 3. Stream response tokens
        client = _get_async_client()
        stream = await client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            temperature=0.3,
            max_tokens=4096,
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield f"data: {json.dumps({'type': 'token', 'content': delta.content})}\n\n"

    except Exception as exc:
        logger.error("Groq streaming failed: %s", exc)
        yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"

    # 4. Signal completion
    yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"
