"""
Pydantic schemas for all API request/response payloads and internal data models.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────────


class AnalysisStatus(str, Enum):
    """Lifecycle states of a repository analysis."""

    QUEUED = "queued"
    CLONING = "cloning"
    PARSING = "parsing"
    EMBEDDING = "embedding"
    GENERATING_DIAGRAMS = "generating_diagrams"
    READY = "ready"
    ERROR = "error"


class DiagramType(str, Enum):
    """Types of architecture diagrams that can be generated."""

    CLASS = "class"
    DEPENDENCY = "dependency"
    FLOW = "flow"
    ARCHITECTURE = "architecture"


class ChunkType(str, Enum):
    """Category of a parsed code chunk."""

    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    IMPORT = "import"
    MODULE = "module"
    TEXT = "text"


# ── Request Models ─────────────────────────────────────────────────────────────


class RepoAnalyzeRequest(BaseModel):
    """Payload for POST /api/repo/analyze."""

    url: str = Field(..., description="Public GitHub repository URL")


class ChatRequest(BaseModel):
    """Payload for POST /api/chat/{repo_id}."""

    message: str = Field(..., min_length=1, max_length=4000)
    history: list[dict] = Field(
        default_factory=list,
        description="Previous messages as [{role, content}, ...]",
    )


class DiagramGenerateRequest(BaseModel):
    """Payload for POST /api/diagrams/{repo_id}/generate."""

    types: list[DiagramType] = Field(
        default_factory=lambda: [
            DiagramType.CLASS,
            DiagramType.DEPENDENCY,
            DiagramType.ARCHITECTURE,
        ],
    )


# ── Internal Data Models ───────────────────────────────────────────────────────


class CodeChunk(BaseModel):
    """A single parsed unit of code (class, function, method, etc.)."""

    chunk_type: ChunkType
    name: str
    qualified_name: str = ""
    source_code: str
    file_path: str
    start_line: int = 0
    end_line: int = 0
    language: str = "unknown"
    metadata: dict = Field(default_factory=dict)


# ── Response Models ────────────────────────────────────────────────────────────


class FileTreeNode(BaseModel):
    """Recursive representation of a file/directory in the repo tree."""

    name: str
    path: str
    is_dir: bool = False
    children: list[FileTreeNode] = Field(default_factory=list)
    language: Optional[str] = None
    size: Optional[int] = None


class LanguageStat(BaseModel):
    """Language distribution statistics for an analyzed repo."""

    language: str
    file_count: int = 0
    chunk_count: int = 0
    percentage: float = 0.0


class RepoInfo(BaseModel):
    """Full metadata about an analyzed repository."""

    repo_id: str
    name: str
    url: str
    total_files: int = 0
    total_chunks: int = 0
    languages: list[LanguageStat] = Field(default_factory=list)
    file_tree: Optional[FileTreeNode] = None
    analyzed_at: str = ""


class RepoStatusResponse(BaseModel):
    """Response for GET /api/repo/{id}/status."""

    repo_id: str
    status: AnalysisStatus
    progress: Optional[str] = None
    info: Optional[RepoInfo] = None
    error: Optional[str] = None


class SourceCitation(BaseModel):
    """A reference to the source code that informed an answer."""

    file_path: str
    start_line: int = 0
    end_line: int = 0
    chunk_type: str = ""
    name: str = ""


class ChatResponse(BaseModel):
    """Response for POST /api/chat/{repo_id}."""

    answer: str = ""
    citations: list[SourceCitation] = Field(default_factory=list)


class Diagram(BaseModel):
    """A single generated diagram."""

    type: DiagramType
    title: str
    description: str = ""
    mermaid_code: str = ""
