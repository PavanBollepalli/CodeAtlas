"""
Diagram Generator Service.

Uses the Groq LLM and code chunks from the vector store to generate
Mermaid.js diagram syntax for various architecture views:
  - Class diagrams
  - Module dependency graphs
  - Call flow (sequence) diagrams
  - High-level architecture overviews
"""

import json
import logging
import re
from typing import Optional

from groq import AsyncGroq

from config import settings
from models.schemas import Diagram, DiagramType
from services.vector_store import (
    RetrievedChunk,
    get_all_chunks_by_type,
    query_chunks,
)

logger = logging.getLogger(__name__)

# ── Groq Client ────────────────────────────────────────────────────────────────

_async_client: AsyncGroq | None = None


def _get_async_client() -> AsyncGroq:
    """Get or create the async Groq client."""
    global _async_client
    if _async_client is None:
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not set.")
        _async_client = AsyncGroq(api_key=settings.groq_api_key)
    return _async_client


# ── Prompt Templates ───────────────────────────────────────────────────────────

_CLASS_DIAGRAM_PROMPT = """Analyze the following code chunks containing class and type definitions from a codebase.
Generate a Mermaid.js class diagram that shows:
- All major classes/types with their key attributes and methods
- Inheritance relationships (using <|--)
- Composition/association relationships (using *-- or o--)
- Interface implementations

Rules:
1. Output ONLY valid Mermaid.js classDiagram syntax -- no explanations, no markdown fences.
2. Start with `classDiagram`
3. Use proper Mermaid class diagram syntax
4. Keep method signatures short (just name and return type)
5. Limit to the 15 most important classes to keep the diagram readable
6. Use proper visibility markers (+, -, #)
7. NEVER use emoji or unicode symbols in labels -- ASCII only
8. All node IDs must be unique alphanumeric identifiers

Code chunks:
{context}"""

_DEPENDENCY_DIAGRAM_PROMPT = """Analyze the following import/module chunks from a codebase.
Generate a Mermaid.js flowchart showing the dependency relationships between modules/files.

Rules:
1. Output ONLY valid Mermaid.js flowchart syntax -- no explanations, no markdown fences.
2. Start with `flowchart TD`
3. Group related modules in subgraphs by directory
4. Use arrows to show import dependencies (A --> B means A imports from B)
5. Label nodes with short module names (not full paths)
6. Limit to the 20 most important modules
7. Use descriptive subgraph labels
8. NEVER use emoji or unicode symbols in labels -- ASCII only
9. Every subgraph MUST have a unique name -- do not reuse subgraph names
10. All node IDs must be unique alphanumeric identifiers

Code chunks:
{context}"""

_FLOW_DIAGRAM_PROMPT = """Analyze the following function and method definitions from a codebase.
Generate a Mermaid.js sequence diagram showing the main call flows.

Rules:
1. Output ONLY valid Mermaid.js sequenceDiagram syntax -- no explanations, no markdown fences.
2. Start with `sequenceDiagram`
3. Identify the main entry points and trace their call chains
4. Show interactions between major components/modules
5. Keep it focused on the 3-5 most important flows
6. Use descriptive participant names (ASCII only, no emoji)
7. All participant names must be unique

Code chunks:
{context}"""

_ARCHITECTURE_DIAGRAM_PROMPT = """Analyze the following code chunks from a codebase and generate a high-level architecture diagram.
Identify the major components, layers, and their interactions.

Rules:
1. Output ONLY valid Mermaid.js flowchart syntax -- no explanations, no markdown fences.
2. Start with `flowchart TB`
3. Use subgraphs to represent layers or component groups
4. Show data flow between components
5. Include external dependencies (databases, APIs, etc.) if evident
6. NEVER use emoji or unicode symbols anywhere -- use ASCII-only labels
7. Every subgraph MUST have a globally unique name
8. All node IDs must be unique alphanumeric identifiers (no spaces, no special chars)
9. Make it a clear, professional architecture overview
10. Node labels should be descriptive text in brackets, e.g. NodeId["Descriptive Label"]

Code chunks:
{context}"""


_PROMPT_MAP = {
    DiagramType.CLASS: _CLASS_DIAGRAM_PROMPT,
    DiagramType.DEPENDENCY: _DEPENDENCY_DIAGRAM_PROMPT,
    DiagramType.FLOW: _FLOW_DIAGRAM_PROMPT,
    DiagramType.ARCHITECTURE: _ARCHITECTURE_DIAGRAM_PROMPT,
}

_TITLE_MAP = {
    DiagramType.CLASS: "Class Diagram",
    DiagramType.DEPENDENCY: "Module Dependencies",
    DiagramType.FLOW: "Call Flow",
    DiagramType.ARCHITECTURE: "System Architecture",
}

_DESCRIPTION_MAP = {
    DiagramType.CLASS: "Shows class hierarchies, attributes, methods, and relationships.",
    DiagramType.DEPENDENCY: "Shows how modules and files depend on each other via imports.",
    DiagramType.FLOW: "Shows the main call chains and interactions between components.",
    DiagramType.ARCHITECTURE: "High-level overview of system layers and component interactions.",
}


# ── Context Builders ───────────────────────────────────────────────────────────


def _build_class_context(repo_id: str) -> str:
    """Gather class-type chunks for the class diagram."""
    chunks = get_all_chunks_by_type(repo_id, "class", limit=50)
    if not chunks:
        # Try querying for class-related content
        chunks = query_chunks(repo_id, "class definition inheritance methods attributes", top_k=20)
    return _format_chunks(chunks)


def _build_dependency_context(repo_id: str) -> str:
    """Gather import chunks for the dependency diagram."""
    chunks = get_all_chunks_by_type(repo_id, "import", limit=50)
    if not chunks:
        chunks = query_chunks(repo_id, "import require from module dependency", top_k=20)
    return _format_chunks(chunks)


def _build_flow_context(repo_id: str) -> str:
    """Gather function/method chunks for the flow diagram."""
    funcs = get_all_chunks_by_type(repo_id, "function", limit=30)
    methods = get_all_chunks_by_type(repo_id, "method", limit=20)
    return _format_chunks(funcs + methods)


def _build_architecture_context(repo_id: str) -> str:
    """Gather a diverse sample of chunks for the architecture overview."""
    chunks: list[RetrievedChunk] = []
    for chunk_type in ("class", "function", "import", "module"):
        type_chunks = get_all_chunks_by_type(repo_id, chunk_type, limit=10)
        chunks.extend(type_chunks)
    return _format_chunks(chunks)


_CONTEXT_BUILDERS = {
    DiagramType.CLASS: _build_class_context,
    DiagramType.DEPENDENCY: _build_dependency_context,
    DiagramType.FLOW: _build_flow_context,
    DiagramType.ARCHITECTURE: _build_architecture_context,
}


def _format_chunks(chunks: list[RetrievedChunk]) -> str:
    """Format chunks as context text for the LLM prompt."""
    if not chunks:
        return "No relevant code chunks found."

    parts = []
    for chunk in chunks:
        header = f"[{chunk.file_path} | {chunk.chunk_type}: {chunk.qualified_name}]"
        parts.append(f"{header}\n{chunk.source_code}")
    return "\n\n".join(parts)


# ── Diagram Generation ─────────────────────────────────────────────────────────


async def generate_diagram(repo_id: str, diagram_type: DiagramType) -> Diagram:
    """
    Generate a single Mermaid.js diagram for a repository.

    Args:
        repo_id: Repository identifier.
        diagram_type: Type of diagram to generate.

    Returns:
        Diagram object with Mermaid code.
    """
    # Build context from stored chunks
    context_builder = _CONTEXT_BUILDERS.get(diagram_type, _build_architecture_context)
    context = context_builder(repo_id)

    # Build the prompt
    prompt_template = _PROMPT_MAP[diagram_type]
    prompt = prompt_template.format(context=context)

    # Call Groq
    client = _get_async_client()
    try:
        completion = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a software architect specializing in generating "
                        "accurate Mermaid.js diagrams from code analysis. "
                        "Output ONLY valid Mermaid syntax. No markdown fences, "
                        "no explanations, no extra text. CRITICAL: Never use "
                        "emoji or unicode symbols. Use only ASCII characters in "
                        "all node labels, IDs, and subgraph names. Every subgraph "
                        "name must be globally unique."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=4096,
        )
        mermaid_code = completion.choices[0].message.content or ""
    except Exception as exc:
        logger.error("Diagram generation failed for %s: %s", diagram_type, exc)
        mermaid_code = _fallback_diagram(diagram_type)

    # Clean up the Mermaid code
    mermaid_code = _clean_mermaid(mermaid_code)

    return Diagram(
        type=diagram_type,
        title=_TITLE_MAP[diagram_type],
        description=_DESCRIPTION_MAP[diagram_type],
        mermaid_code=mermaid_code,
    )


async def generate_all_diagrams(
    repo_id: str,
    types: list[DiagramType] | None = None,
) -> list[Diagram]:
    """Generate multiple diagram types for a repository."""
    if types is None:
        types = [DiagramType.CLASS, DiagramType.DEPENDENCY, DiagramType.ARCHITECTURE]

    diagrams = []
    for dt in types:
        try:
            diagram = await generate_diagram(repo_id, dt)
            diagrams.append(diagram)
        except Exception as exc:
            logger.error("Failed to generate %s diagram: %s", dt, exc)
            diagrams.append(Diagram(
                type=dt,
                title=_TITLE_MAP[dt],
                description=f"Failed to generate: {str(exc)}",
                mermaid_code=_fallback_diagram(dt),
            ))

    return diagrams


# ── Helpers ────────────────────────────────────────────────────────────────────



def _clean_mermaid(code: str) -> str:
    """Clean up and sanitize LLM-generated Mermaid code."""
    code = code.strip()

    # Remove markdown code fences if present
    if code.startswith("```"):
        lines = code.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines).strip()

    # Strip emoji/unicode symbols that break Mermaid parser
    # Matches most emoji ranges
    emoji_pattern = re.compile(
        "["
        "\U0001F300-\U0001F9FF"   # Misc Symbols, Emoticons, etc.
        "\U00002702-\U000027B0"   # Dingbats
        "\U0000FE00-\U0000FE0F"   # Variation Selectors
        "\U0000200D"              # Zero Width Joiner
        "\U000020E3"              # Combining Enclosing Keycap
        "\U00002600-\U000026FF"   # Misc Symbols
        "\U00002700-\U000027BF"   # Dingbats
        "\U0000231A-\U0000231B"   # Watch, Hourglass
        "\U000023E9-\U000023F3"   # Media controls
        "\U000023F8-\U000023FA"   # Media controls
        "\U000025AA-\U000025AB"   # Squares
        "\U000025B6"              # Play button
        "\U000025C0"              # Reverse button
        "\U000025FB-\U000025FE"   # Squares
        "\U00002614-\U00002615"   # Umbrella, Hot Beverage
        "\U00002648-\U00002653"   # Zodiac
        "\U0000267F"              # Wheelchair
        "\U00002934-\U00002935"   # Arrows
        "\U00003030"              # Wavy Dash
        "\U0000303D"              # Part Alternation Mark
        "\U00003297"              # Circled Ideograph Congratulation
        "\U00003299"              # Circled Ideograph Secret
        "]+",
        flags=re.UNICODE,
    )
    code = emoji_pattern.sub("", code)

    # Deduplicate subgraph names by appending a counter
    seen_subgraphs: dict[str, int] = {}
    lines = code.split("\n")
    fixed_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        # Match `subgraph SomeName` pattern
        match = re.match(r"^(\s*subgraph\s+)(\S.*)$", line)
        if match:
            prefix = match.group(1)
            name = match.group(2).strip()
            if name in seen_subgraphs:
                seen_subgraphs[name] += 1
                name = f"{name} {seen_subgraphs[name]}"
            else:
                seen_subgraphs[name] = 1
            fixed_lines.append(f"{prefix}{name}")
        else:
            fixed_lines.append(line)
    code = "\n".join(fixed_lines)

    # Clean up any double spaces left by emoji removal
    code = re.sub(r"  +", " ", code)

    return code


def _fallback_diagram(diagram_type: DiagramType) -> str:
    """Provide a minimal valid Mermaid diagram as fallback."""
    fallbacks = {
        DiagramType.CLASS: "classDiagram\n    class Repository {\n        +String name\n        +analyze()\n    }",
        DiagramType.DEPENDENCY: "flowchart TD\n    A[Module A] --> B[Module B]\n    B --> C[Module C]",
        DiagramType.FLOW: "sequenceDiagram\n    participant User\n    participant System\n    User->>System: Request\n    System-->>User: Response",
        DiagramType.ARCHITECTURE: "flowchart TB\n    subgraph Frontend\n        UI[User Interface]\n    end\n    subgraph Backend\n        API[API Layer]\n        DB[(Database)]\n    end\n    UI --> API\n    API --> DB",
    }
    return fallbacks.get(diagram_type, "flowchart TD\n    A[Start] --> B[End]")
