"""
Git Cloner Service.

Handles cloning public GitHub repositories, validating URLs,
checking repo size via GitHub API, and cleaning up temp directories.
"""

import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from config import settings

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

GITHUB_URL_PATTERN = re.compile(
    r"^https?://github\.com/(?P<owner>[a-zA-Z0-9\-_.]+)/(?P<repo>[a-zA-Z0-9\-_.]+?)(?:\.git)?/?$"
)

GITHUB_API_BASE = "https://api.github.com"


# ── Data Classes ───────────────────────────────────────────────────────────────


@dataclass
class RepoMetadata:
    """Metadata extracted from the GitHub API about a repository."""

    owner: str = ""
    name: str = ""
    full_name: str = ""
    description: str = ""
    default_branch: str = "main"
    size_kb: int = 0
    stars: int = 0
    language: str = ""


@dataclass
class CloneResult:
    """Result of a successful clone operation."""

    repo_id: str = ""
    clone_path: str = ""
    metadata: RepoMetadata = field(default_factory=RepoMetadata)


# ── Exceptions ─────────────────────────────────────────────────────────────────


class CloneError(Exception):
    """Raised when cloning fails."""


class InvalidRepoURLError(CloneError):
    """Raised when the repository URL is invalid."""


class RepoTooLargeError(CloneError):
    """Raised when the repository exceeds size limits."""


class RepoNotFoundError(CloneError):
    """Raised when the repository does not exist or is private."""


# ── Public API ─────────────────────────────────────────────────────────────────


def validate_github_url(url: str) -> tuple[str, str]:
    """
    Validate and extract owner/repo from a GitHub URL.

    Returns:
        Tuple of (owner, repo_name).

    Raises:
        InvalidRepoURLError: If the URL doesn't match the expected pattern.
    """
    match = GITHUB_URL_PATTERN.match(url.strip())
    if not match:
        raise InvalidRepoURLError(
            f"Invalid GitHub URL: '{url}'. "
            "Expected format: https://github.com/owner/repo"
        )
    return match.group("owner"), match.group("repo")


async def fetch_repo_metadata(owner: str, repo: str) -> RepoMetadata:
    """
    Fetch repository metadata from GitHub API.

    Raises:
        RepoNotFoundError: If the repo is not found or is private.
        RepoTooLargeError: If the repo exceeds size limits.
    """
    api_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(
                api_url,
                headers={"Accept": "application/vnd.github.v3+json"},
            )
        except httpx.RequestError as exc:
            logger.warning("GitHub API request failed: %s", exc)
            # Return basic metadata if API is unreachable (rate limiting, etc.)
            return RepoMetadata(owner=owner, name=repo, full_name=f"{owner}/{repo}")

    if response.status_code == 404:
        raise RepoNotFoundError(
            f"Repository '{owner}/{repo}' not found. "
            "Make sure the repository exists and is public."
        )
    if response.status_code == 403:
        logger.warning("GitHub API rate limited, proceeding without size check")
        return RepoMetadata(owner=owner, name=repo, full_name=f"{owner}/{repo}")

    if response.status_code != 200:
        logger.warning("GitHub API returned %d, proceeding anyway", response.status_code)
        return RepoMetadata(owner=owner, name=repo, full_name=f"{owner}/{repo}")

    data = response.json()
    size_kb = data.get("size", 0)
    size_mb = size_kb / 1024

    if size_mb > settings.max_repo_size_mb:
        raise RepoTooLargeError(
            f"Repository '{owner}/{repo}' is {size_mb:.1f} MB, "
            f"which exceeds the {settings.max_repo_size_mb} MB limit."
        )

    return RepoMetadata(
        owner=owner,
        name=data.get("name", repo),
        full_name=data.get("full_name", f"{owner}/{repo}"),
        description=data.get("description", "") or "",
        default_branch=data.get("default_branch", "main"),
        size_kb=size_kb,
        stars=data.get("stargazers_count", 0),
        language=data.get("language", "") or "",
    )


def clone_repository(url: str, repo_id: str | None = None) -> CloneResult:
    """
    Clone a public GitHub repository to a temporary directory.

    Performs a shallow clone (depth=1) for speed.

    Args:
        url: GitHub repository URL.
        repo_id: Optional pre-generated repo ID.

    Returns:
        CloneResult with path and metadata.

    Raises:
        CloneError: If git clone fails.
    """
    if repo_id is None:
        repo_id = uuid.uuid4().hex[:12]

    clone_base = Path(settings.clone_dir)
    clone_base.mkdir(parents=True, exist_ok=True)
    clone_path = clone_base / repo_id

    if clone_path.exists():
        shutil.rmtree(clone_path, ignore_errors=True)

    logger.info("Cloning %s → %s", url, clone_path)

    try:
        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--single-branch",
                url.strip(),
                str(clone_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError:
        raise CloneError(
            "Git is not installed or not in PATH. Please install git."
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(clone_path, ignore_errors=True)
        raise CloneError("Clone timed out after 120 seconds. The repository may be too large.")

    if result.returncode != 0:
        shutil.rmtree(clone_path, ignore_errors=True)
        stderr = result.stderr.strip()
        if "not found" in stderr.lower() or "does not exist" in stderr.lower():
            raise RepoNotFoundError(f"Repository not found: {url}")
        raise CloneError(f"Git clone failed: {stderr}")

    logger.info("Clone complete: %s", clone_path)
    return CloneResult(repo_id=repo_id, clone_path=str(clone_path))


def cleanup_repository(repo_id: str) -> None:
    """Remove cloned repository files from disk."""
    clone_path = Path(settings.clone_dir) / repo_id
    if clone_path.exists():
        shutil.rmtree(clone_path, ignore_errors=True)
        logger.info("Cleaned up repo: %s", repo_id)
