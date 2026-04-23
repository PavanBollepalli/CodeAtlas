"""Development server entrypoint with safe reload exclusions."""

import uvicorn


def main() -> None:
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_excludes=[
            "cloned_repos/*",
            "chroma_data/*",
            "repo_metadata/*",
            ".venv/*",
        ],
    )


if __name__ == "__main__":
    main()
