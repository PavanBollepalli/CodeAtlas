"""
Code Parser Service.

Multi-language AST/regex parser that extracts structured code chunks
(classes, functions, methods, imports) from source files.

Strategy:
  - Python  → built-in `ast` module (gold standard)
  - JS/TS   → regex pattern matching
  - Java    → regex pattern matching
  - Go      → regex pattern matching
  - Rust    → regex pattern matching
  - C/C++   → regex pattern matching
  - Other   → smart text-based chunking
"""

import ast
import logging
import re
from pathlib import Path

from models.schemas import ChunkType, CodeChunk

logger = logging.getLogger(__name__)

# ── Language Extension Mapping ─────────────────────────────────────────────────

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".r": "r",
    ".R": "r",
    ".lua": "lua",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".sql": "sql",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
}

# Files/dirs to always skip
SKIP_DIRS = {
    ".git", ".svn", ".hg",
    "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", ".next", ".nuxt",
    "vendor", "target", "bin", "obj",
    ".idea", ".vscode", ".vs",
    "coverage", ".coverage",
}

SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Pipfile.lock", "uv.lock", "poetry.lock",
    ".DS_Store", "Thumbs.db",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".avi", ".mov", ".webm",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".exe", ".dll", ".so", ".dylib", ".o", ".a",
    ".pyc", ".pyo", ".class", ".wasm",
    ".db", ".sqlite", ".sqlite3",
}


def detect_language(file_path: str) -> str | None:
    """Detect programming language from file extension. Returns None for unsupported files."""
    ext = Path(file_path).suffix.lower()
    if ext in BINARY_EXTENSIONS:
        return None
    return EXTENSION_TO_LANGUAGE.get(ext)


def should_skip(path: Path) -> bool:
    """Check if a file or directory should be skipped during analysis."""
    if path.name in SKIP_FILES:
        return True
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    # Skip very large files (> 500KB — likely generated or data files)
    if path.is_file():
        try:
            if path.stat().st_size > 500_000:
                return True
        except OSError:
            return True
    return False


def should_skip_dir(dir_name: str) -> bool:
    """Check if a directory should be skipped."""
    return dir_name in SKIP_DIRS or dir_name.startswith(".")


# ══════════════════════════════════════════════════════════════════════════════
#  Python Parser (AST-based)
# ══════════════════════════════════════════════════════════════════════════════


class PythonParser:
    """Parse Python source files using the built-in `ast` module."""

    def parse(self, source: str, file_path: str) -> list[CodeChunk]:
        """Parse Python source code into structured chunks."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            logger.debug("SyntaxError in %s — falling back to text chunking", file_path)
            return _text_chunk(source, file_path, "python")

        chunks: list[CodeChunk] = []
        lines = source.splitlines()

        # Extract module-level docstring
        docstring = ast.get_docstring(tree)
        if docstring:
            chunks.append(CodeChunk(
                chunk_type=ChunkType.MODULE,
                name=Path(file_path).stem,
                qualified_name=Path(file_path).stem,
                source_code=f'"""{docstring}"""',
                file_path=file_path,
                start_line=1,
                end_line=min(3, len(lines)),
                language="python",
                metadata={"type": "module_docstring"},
            ))

        # Extract import block
        imports = self._extract_imports(tree, lines, file_path)
        if imports:
            chunks.append(imports)

        # Walk top-level nodes
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                chunks.extend(self._extract_class(node, source, lines, file_path))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunks.append(self._extract_function(node, lines, file_path))

        return chunks

    def _extract_imports(
        self, tree: ast.Module, lines: list[str], file_path: str
    ) -> CodeChunk | None:
        """Extract all import statements into a single chunk."""
        import_lines: list[int] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for ln in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                    import_lines.append(ln)

        if not import_lines:
            return None

        start = min(import_lines)
        end = max(import_lines)
        source_code = "\n".join(lines[start - 1 : end])

        return CodeChunk(
            chunk_type=ChunkType.IMPORT,
            name="imports",
            qualified_name=f"{Path(file_path).stem}.imports",
            source_code=source_code,
            file_path=file_path,
            start_line=start,
            end_line=end,
            language="python",
        )

    def _extract_class(
        self, node: ast.ClassDef, source: str, lines: list[str], file_path: str,
    ) -> list[CodeChunk]:
        """Extract a class definition and its individual methods."""
        chunks: list[CodeChunk] = []

        # Full class chunk
        class_source = "\n".join(lines[node.lineno - 1 : node.end_lineno or node.lineno])

        bases = [_get_name(b) for b in node.bases]
        decorators = [_get_name(d) for d in node.decorator_list]
        docstring = ast.get_docstring(node) or ""

        chunks.append(CodeChunk(
            chunk_type=ChunkType.CLASS,
            name=node.name,
            qualified_name=f"{Path(file_path).stem}.{node.name}",
            source_code=class_source,
            file_path=file_path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            language="python",
            metadata={
                "bases": bases,
                "decorators": decorators,
                "docstring": docstring,
            },
        ))

        # Individual methods
        for item in ast.iter_child_nodes(node):
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_source = "\n".join(
                    lines[item.lineno - 1 : item.end_lineno or item.lineno]
                )
                params = [
                    a.arg for a in item.args.args if a.arg != "self"
                ]
                method_doc = ast.get_docstring(item) or ""

                chunks.append(CodeChunk(
                    chunk_type=ChunkType.METHOD,
                    name=item.name,
                    qualified_name=f"{Path(file_path).stem}.{node.name}.{item.name}",
                    source_code=method_source,
                    file_path=file_path,
                    start_line=item.lineno,
                    end_line=item.end_lineno or item.lineno,
                    language="python",
                    metadata={
                        "parent_class": node.name,
                        "params": params,
                        "is_async": isinstance(item, ast.AsyncFunctionDef),
                        "docstring": method_doc,
                    },
                ))

        return chunks

    def _extract_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, lines: list[str], file_path: str,
    ) -> CodeChunk:
        """Extract a top-level function definition."""
        func_source = "\n".join(lines[node.lineno - 1 : node.end_lineno or node.lineno])
        params = [a.arg for a in node.args.args]
        decorators = [_get_name(d) for d in node.decorator_list]
        docstring = ast.get_docstring(node) or ""

        return CodeChunk(
            chunk_type=ChunkType.FUNCTION,
            name=node.name,
            qualified_name=f"{Path(file_path).stem}.{node.name}",
            source_code=func_source,
            file_path=file_path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            language="python",
            metadata={
                "params": params,
                "decorators": decorators,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "docstring": docstring,
            },
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Regex-based Parser (JS/TS, Java, Go, Rust, C/C++)
# ══════════════════════════════════════════════════════════════════════════════

# Regex patterns keyed by language
_PATTERNS: dict[str, dict[str, re.Pattern]] = {
    "javascript": {
        "class": re.compile(
            r"^(?:export\s+)?(?:default\s+)?class\s+(\w+)",
            re.MULTILINE,
        ),
        "function": re.compile(
            r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s+(\w+)\s*\(",
            re.MULTILINE,
        ),
        "arrow": re.compile(
            r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(?",
            re.MULTILINE,
        ),
    },
    "typescript": {
        "class": re.compile(
            r"^(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)",
            re.MULTILINE,
        ),
        "interface": re.compile(
            r"^(?:export\s+)?interface\s+(\w+)",
            re.MULTILINE,
        ),
        "function": re.compile(
            r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s+(\w+)\s*[<(]",
            re.MULTILINE,
        ),
        "arrow": re.compile(
            r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::\s*[\w<>\[\]|,\s]+)?\s*=\s*(?:async\s+)?\(?",
            re.MULTILINE,
        ),
    },
    "java": {
        "class": re.compile(
            r"^(?:public|private|protected)?\s*(?:static\s+)?(?:abstract\s+)?(?:final\s+)?(?:class|interface|enum)\s+(\w+)",
            re.MULTILINE,
        ),
        "function": re.compile(
            r"^\s+(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?\w[\w<>\[\],\s]*\s+(\w+)\s*\(",
            re.MULTILINE,
        ),
    },
    "go": {
        "struct": re.compile(r"^type\s+(\w+)\s+struct\s*\{", re.MULTILINE),
        "interface": re.compile(r"^type\s+(\w+)\s+interface\s*\{", re.MULTILINE),
        "function": re.compile(r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(", re.MULTILINE),
    },
    "rust": {
        "struct": re.compile(r"^(?:pub\s+)?struct\s+(\w+)", re.MULTILINE),
        "enum": re.compile(r"^(?:pub\s+)?enum\s+(\w+)", re.MULTILINE),
        "trait": re.compile(r"^(?:pub\s+)?trait\s+(\w+)", re.MULTILINE),
        "impl": re.compile(r"^impl(?:<[^>]+>)?\s+(\w+)", re.MULTILINE),
        "function": re.compile(
            r"^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)",
            re.MULTILINE,
        ),
    },
    "c": {
        "struct": re.compile(r"^(?:typedef\s+)?struct\s+(\w+)", re.MULTILINE),
        "function": re.compile(
            r"^(?:static\s+)?(?:inline\s+)?(?:const\s+)?\w[\w\s*]+\s+(\w+)\s*\([^)]*\)\s*\{",
            re.MULTILINE,
        ),
    },
    "cpp": {
        "class": re.compile(r"^(?:template\s*<[^>]*>\s*)?class\s+(\w+)", re.MULTILINE),
        "struct": re.compile(r"^(?:template\s*<[^>]*>\s*)?struct\s+(\w+)", re.MULTILINE),
        "function": re.compile(
            r"^(?:static\s+)?(?:inline\s+)?(?:virtual\s+)?(?:const\s+)?\w[\w\s*:&<>]+\s+(\w+)\s*\([^)]*\)\s*(?:const\s*)?(?:override\s*)?(?:noexcept\s*)?\{",
            re.MULTILINE,
        ),
    },
}

# Also cover these by aliasing
_PATTERNS["jsx"] = _PATTERNS["javascript"]
_PATTERNS["tsx"] = _PATTERNS["typescript"]


class RegexParser:
    """Parse source files using regex patterns to extract code structure."""

    def __init__(self, language: str):
        self.language = language
        self.patterns = _PATTERNS.get(language, {})

    def parse(self, source: str, file_path: str) -> list[CodeChunk]:
        """Parse source code using regex patterns to identify code blocks."""
        if not self.patterns:
            return _text_chunk(source, file_path, self.language)

        chunks: list[CodeChunk] = []
        lines = source.splitlines()

        for kind, pattern in self.patterns.items():
            for match in pattern.finditer(source):
                name = match.group(1)
                start_pos = match.start()
                start_line = source[:start_pos].count("\n") + 1

                # Find the closing brace for this block
                end_line = self._find_block_end(lines, start_line - 1)
                block_source = "\n".join(lines[start_line - 1 : end_line])

                chunk_type = self._classify(kind)

                chunks.append(CodeChunk(
                    chunk_type=chunk_type,
                    name=name,
                    qualified_name=f"{Path(file_path).stem}.{name}",
                    source_code=block_source,
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    language=self.language,
                    metadata={"kind": kind},
                ))

        # If no patterns matched, fall back to text chunking
        if not chunks:
            return _text_chunk(source, file_path, self.language)

        return chunks

    def _find_block_end(self, lines: list[str], start_idx: int) -> int:
        """
        Find the end of a code block by tracking brace depth.
        Falls back to a fixed window if braces don't balance.
        """
        depth = 0
        found_open = False

        for i in range(start_idx, min(start_idx + 500, len(lines))):
            line = lines[i]
            for ch in line:
                if ch == "{":
                    depth += 1
                    found_open = True
                elif ch == "}":
                    depth -= 1

            if found_open and depth <= 0:
                return i + 1  # 1-indexed

        # Fallback: return up to 50 lines
        return min(start_idx + 50, len(lines))

    def _classify(self, kind: str) -> ChunkType:
        """Map a regex pattern kind to a ChunkType."""
        if kind in ("class", "struct", "interface", "enum", "trait", "impl"):
            return ChunkType.CLASS
        if kind in ("function", "arrow"):
            return ChunkType.FUNCTION
        return ChunkType.TEXT


# ══════════════════════════════════════════════════════════════════════════════
#  Text Chunking Fallback
# ══════════════════════════════════════════════════════════════════════════════


def _text_chunk(
    source: str, file_path: str, language: str, chunk_size: int = 1500, overlap: int = 200,
) -> list[CodeChunk]:
    """
    Split source code into overlapping text chunks.
    Used as fallback when AST/regex parsing isn't possible.
    """
    if not source.strip():
        return []

    lines = source.splitlines()
    chunks: list[CodeChunk] = []

    i = 0
    chunk_idx = 0
    while i < len(lines):
        end = min(i + chunk_size // 40, len(lines))  # ~40 chars per line avg
        chunk_lines = lines[i:end]
        chunk_source = "\n".join(chunk_lines)

        if chunk_source.strip():
            chunks.append(CodeChunk(
                chunk_type=ChunkType.TEXT,
                name=f"chunk_{chunk_idx}",
                qualified_name=f"{Path(file_path).stem}.chunk_{chunk_idx}",
                source_code=chunk_source,
                file_path=file_path,
                start_line=i + 1,
                end_line=end,
                language=language,
            ))
            chunk_idx += 1

        # Advance with overlap
        i = end - (overlap // 40) if end < len(lines) else len(lines)

    return chunks


# ══════════════════════════════════════════════════════════════════════════════
#  Factory / Public API
# ══════════════════════════════════════════════════════════════════════════════


def parse_file(file_path: str, source: str | None = None) -> list[CodeChunk]:
    """
    Parse a source file into structured code chunks.

    Automatically selects the best parser based on file extension.

    Args:
        file_path: Path to the source file.
        source: Optional pre-read source code. If None, reads from disk.

    Returns:
        List of CodeChunk objects extracted from the file.
    """
    if source is None:
        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            logger.debug("Cannot read file: %s", file_path)
            return []

    if not source.strip():
        return []

    language = detect_language(file_path)
    if language is None:
        return []

    # Select parser
    if language == "python":
        parser = PythonParser()
        return parser.parse(source, file_path)
    elif language in _PATTERNS:
        parser = RegexParser(language)
        return parser.parse(source, file_path)
    elif language in ("markdown", "yaml", "json", "toml", "xml", "html", "css", "scss", "sql"):
        # Config/doc files → single text chunk
        return _text_chunk(source, file_path, language)
    else:
        return _text_chunk(source, file_path, language or "unknown")


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_name(node) -> str:
    """Get the string name of an AST node (handles ast.Name, ast.Attribute, etc.)."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_get_name(node.value)}.{node.attr}"
    elif isinstance(node, ast.Call):
        return _get_name(node.func)
    elif isinstance(node, ast.Constant):
        return str(node.value)
    return ""
