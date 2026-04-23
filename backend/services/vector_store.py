"""
ChromaDB Vector Store Service.

Wraps ChromaDB to provide per-repository collections with automatic
embedding (default all-MiniLM-L6-v2 via onnxruntime) and metadata-rich
storage and retrieval.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import chromadb

from config import settings
from models.schemas import CodeChunk, SourceCitation

logger = logging.getLogger(__name__)

# ── Singleton Client ───────────────────────────────────────────────────────────

_client: chromadb.ClientAPI | None = None


def get_client() -> chromadb.ClientAPI:
    """Get or create the ChromaDB persistent client."""
    global _client
    if _client is None:
        persist_dir = Path(settings.chroma_persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(persist_dir))
        logger.info("ChromaDB client initialized at %s", persist_dir)
    return _client


# ── Data Classes ───────────────────────────────────────────────────────────────


@dataclass
class RetrievedChunk:
    """A chunk retrieved from the vector store with similarity info."""

    chunk_id: str = ""
    source_code: str = ""
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    chunk_type: str = ""
    name: str = ""
    qualified_name: str = ""
    language: str = ""
    distance: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_citation(self) -> SourceCitation:
        """Convert to a SourceCitation for API responses."""
        return SourceCitation(
            file_path=self.file_path,
            start_line=self.start_line,
            end_line=self.end_line,
            chunk_type=self.chunk_type,
            name=self.name,
        )


# ── Collection Management ─────────────────────────────────────────────────────


def _collection_name(repo_id: str) -> str:
    """Generate a valid ChromaDB collection name from repo_id."""
    # ChromaDB collection names must be 3-63 chars, alphanumeric + underscore/hyphen
    name = f"repo_{repo_id}"
    return name[:63]


def create_collection(repo_id: str) -> chromadb.Collection:
    """Create a new ChromaDB collection for a repository."""
    client = get_client()
    name = _collection_name(repo_id)

    # Delete existing collection if it exists (re-analysis)
    try:
        client.delete_collection(name)
    except Exception:
        pass

    collection = client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info("Created collection '%s' for repo %s", name, repo_id)
    return collection


def get_collection(repo_id: str) -> chromadb.Collection:
    """Get an existing collection for a repository."""
    client = get_client()
    return client.get_collection(_collection_name(repo_id))


def delete_collection(repo_id: str) -> None:
    """Delete the collection for a repository."""
    client = get_client()
    try:
        client.delete_collection(_collection_name(repo_id))
        logger.info("Deleted collection for repo %s", repo_id)
    except Exception:
        logger.debug("Collection for repo %s not found", repo_id)


def get_collection_info(repo_id: str) -> dict | None:
    """
    Check if a ChromaDB collection exists for a repo and return basic info.
    Returns None if no collection exists. Used to recover state after server restarts.
    """
    client = get_client()
    try:
        collection = client.get_collection(_collection_name(repo_id))
        count = collection.count()
        if count == 0:
            return None

        # Try to extract repo name from the first chunk's file path
        sample = collection.peek(limit=1)
        name = repo_id
        if sample and sample.get("metadatas") and sample["metadatas"]:
            file_path = sample["metadatas"][0].get("file_path", "")
            # The file path might look like "src/main.py" — repo name isn't here,
            # so we'll use repo_id as the name. The URL isn't stored in ChromaDB.
            if file_path:
                name = repo_id

        return {
            "total_chunks": count,
            "total_files": 0,  # Not stored in ChromaDB metadata
            "name": name,
            "url": "",
            "analyzed_at": "",
        }
    except Exception:
        return None


# ── Document Operations ───────────────────────────────────────────────────────


def store_chunks(repo_id: str, chunks: list[CodeChunk]) -> int:
    """
    Store code chunks in the vector store.

    ChromaDB handles embedding automatically using its default embedding function.

    Args:
        repo_id: Repository identifier.
        chunks: List of CodeChunk objects to store.

    Returns:
        Number of chunks stored.
    """
    if not chunks:
        return 0

    collection = create_collection(repo_id)

    # Prepare documents in batches (ChromaDB recommends < 5000 per batch)
    batch_size = 500
    stored = 0

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]

        ids = []
        documents = []
        metadatas = []

        for j, chunk in enumerate(batch):
            chunk_id = f"{repo_id}_{i + j}"

            # Build the document text for embedding
            # Include type and name for better semantic matching
            doc_text = (
                f"{chunk.chunk_type.value} {chunk.qualified_name}:\n"
                f"{chunk.source_code}"
            )

            meta = {
                "file_path": chunk.file_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "chunk_type": chunk.chunk_type.value,
                "name": chunk.name,
                "qualified_name": chunk.qualified_name,
                "language": chunk.language,
            }

            ids.append(chunk_id)
            documents.append(doc_text)
            metadatas.append(meta)

        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )
        stored += len(batch)
        logger.debug("Stored batch %d-%d (%d chunks)", i, i + len(batch), len(batch))

    logger.info("Stored %d chunks for repo %s", stored, repo_id)
    return stored


def query_chunks(
    repo_id: str,
    query_text: str,
    top_k: int | None = None,
    chunk_type: str | None = None,
    language: str | None = None,
) -> list[RetrievedChunk]:
    """
    Query the vector store for similar code chunks.

    Args:
        repo_id: Repository identifier.
        query_text: The search query.
        top_k: Number of results to return (default from settings).
        chunk_type: Optional filter by chunk type.
        language: Optional filter by language.

    Returns:
        List of RetrievedChunk objects, sorted by relevance.
    """
    if top_k is None:
        top_k = settings.top_k

    try:
        collection = get_collection(repo_id)
    except Exception:
        logger.error("Collection not found for repo %s", repo_id)
        return []

    # Build where filter
    where_filter = None
    conditions = []
    if chunk_type:
        conditions.append({"chunk_type": chunk_type})
    if language:
        conditions.append({"language": language})

    if len(conditions) == 1:
        where_filter = conditions[0]
    elif len(conditions) > 1:
        where_filter = {"$and": conditions}

    try:
        results = collection.query(
            query_texts=[query_text],
            n_results=min(top_k, collection.count()),
            where=where_filter if where_filter else None,
        )
    except Exception as exc:
        logger.error("Query failed for repo %s: %s", repo_id, exc)
        return []

    chunks: list[RetrievedChunk] = []

    if results and results["ids"] and results["ids"][0]:
        for i, chunk_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            doc = results["documents"][0][i] if results["documents"] else ""
            distance = results["distances"][0][i] if results["distances"] else 0.0

            # Extract source code from document (remove the header line)
            source_lines = doc.split("\n", 1)
            source_code = source_lines[1] if len(source_lines) > 1 else doc

            chunks.append(RetrievedChunk(
                chunk_id=chunk_id,
                source_code=source_code,
                file_path=meta.get("file_path", ""),
                start_line=meta.get("start_line", 0),
                end_line=meta.get("end_line", 0),
                chunk_type=meta.get("chunk_type", ""),
                name=meta.get("name", ""),
                qualified_name=meta.get("qualified_name", ""),
                language=meta.get("language", ""),
                distance=distance,
                metadata=meta,
            ))

    return chunks


def get_all_chunks_by_type(
    repo_id: str, chunk_type: str, limit: int = 100,
) -> list[RetrievedChunk]:
    """
    Retrieve all chunks of a specific type from a repository.
    Used by the diagram generator to get all classes, functions, etc.
    """
    try:
        collection = get_collection(repo_id)
    except Exception:
        return []

    try:
        count = collection.count()
        results = collection.get(
            where={"chunk_type": chunk_type},
            limit=min(limit, count),
        )
    except Exception:
        return []

    chunks: list[RetrievedChunk] = []

    if results and results["ids"]:
        for i, chunk_id in enumerate(results["ids"]):
            meta = results["metadatas"][i] if results["metadatas"] else {}
            doc = results["documents"][i] if results["documents"] else ""

            source_lines = doc.split("\n", 1)
            source_code = source_lines[1] if len(source_lines) > 1 else doc

            chunks.append(RetrievedChunk(
                chunk_id=chunk_id,
                source_code=source_code,
                file_path=meta.get("file_path", ""),
                start_line=meta.get("start_line", 0),
                end_line=meta.get("end_line", 0),
                chunk_type=meta.get("chunk_type", ""),
                name=meta.get("name", ""),
                qualified_name=meta.get("qualified_name", ""),
                language=meta.get("language", ""),
                metadata=meta,
            ))

    return chunks
