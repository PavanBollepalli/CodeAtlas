"""
Repository Chunker Service.

Walks a cloned repository directory, parses all supported files,
builds a file tree, and computes language statistics.
"""

import logging
import os
from collections import defaultdict
from pathlib import Path

from config import settings
from models.schemas import CodeChunk, FileTreeNode, LanguageStat
from services.parser import (
    detect_language,
    parse_file,
    should_skip,
    should_skip_dir,
)

logger = logging.getLogger(__name__)


# ── Data Structures ────────────────────────────────────────────────────────────


class ChunkResult:
    """Aggregated result of chunking a repository."""

    def __init__(self):
        self.chunks: list[CodeChunk] = []
        self.file_tree: FileTreeNode | None = None
        self.total_files: int = 0
        self.languages: list[LanguageStat] = []


# ── Public API ─────────────────────────────────────────────────────────────────


def chunk_repository(repo_path: str) -> ChunkResult:
    """
    Walk a repository directory, parse all files, and return structured chunks.

    Args:
        repo_path: Absolute path to the cloned repository.

    Returns:
        ChunkResult with all chunks, file tree, and statistics.
    """
    root = Path(repo_path)
    if not root.is_dir():
        raise FileNotFoundError(f"Repository path not found: {repo_path}")

    result = ChunkResult()
    lang_file_counts: dict[str, int] = defaultdict(int)
    lang_chunk_counts: dict[str, int] = defaultdict(int)
    file_count = 0

    # Walk the directory tree
    for dirpath, dirnames, filenames in os.walk(root):
        # Filter out skippable directories (in-place modification)
        dirnames[:] = [
            d for d in dirnames
            if not should_skip_dir(d)
        ]

        for filename in filenames:
            file_path = Path(dirpath) / filename

            # Skip non-code / binary / large files
            if should_skip(file_path):
                continue

            # Detect language
            language = detect_language(str(file_path))
            if language is None:
                continue

            file_count += 1

            # Enforce file count limit
            if file_count > settings.max_files:
                logger.warning(
                    "File limit reached (%d). Stopping parse.", settings.max_files
                )
                break

            # Parse the file
            relative_path = str(file_path.relative_to(root)).replace("\\", "/")
            try:
                chunks = parse_file(str(file_path))
                # Rewrite file_path to relative
                for chunk in chunks:
                    chunk.file_path = relative_path

                result.chunks.extend(chunks)
                lang_file_counts[language] += 1
                lang_chunk_counts[language] += len(chunks)
            except Exception:
                logger.debug("Failed to parse: %s", relative_path, exc_info=True)

        # Break outer loop too if limit reached
        if file_count > settings.max_files:
            break

    result.total_files = file_count

    # Build file tree
    result.file_tree = _build_file_tree(root)

    # Compute language statistics
    total_chunks = len(result.chunks)
    for lang in sorted(lang_file_counts.keys()):
        result.languages.append(LanguageStat(
            language=lang,
            file_count=lang_file_counts[lang],
            chunk_count=lang_chunk_counts[lang],
            percentage=round(
                lang_chunk_counts[lang] / total_chunks * 100, 1
            ) if total_chunks > 0 else 0.0,
        ))

    logger.info(
        "Chunked %d files → %d chunks across %d languages",
        file_count,
        len(result.chunks),
        len(result.languages),
    )

    return result


# ── File Tree Builder ──────────────────────────────────────────────────────────


def _build_file_tree(root: Path, max_depth: int = 6) -> FileTreeNode:
    """
    Build a recursive file tree representation of the repository.

    Limits depth to prevent excessively deep trees.
    """
    return _scan_dir(root, root, depth=0, max_depth=max_depth)


def _scan_dir(path: Path, root: Path, depth: int, max_depth: int) -> FileTreeNode:
    """Recursively scan a directory and build a FileTreeNode."""
    relative = str(path.relative_to(root)).replace("\\", "/")
    if relative == ".":
        relative = ""

    node = FileTreeNode(
        name=path.name or root.name,
        path=relative,
        is_dir=True,
    )

    if depth >= max_depth:
        return node

    try:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return node

    for entry in entries:
        if entry.is_dir():
            if should_skip_dir(entry.name):
                continue
            child = _scan_dir(entry, root, depth + 1, max_depth)
            node.children.append(child)
        else:
            if should_skip(entry):
                continue
            language = detect_language(str(entry))
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0

            node.children.append(FileTreeNode(
                name=entry.name,
                path=str(entry.relative_to(root)).replace("\\", "/"),
                is_dir=False,
                language=language,
                size=size,
            ))

    return node
