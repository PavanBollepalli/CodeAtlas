param(
    [int]$TargetTotalCommits = 30
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$currentCount = [int](& git rev-list --count HEAD)
$needed = $TargetTotalCommits - $currentCount

$commits = @(
    @{
        Message = "chore: add commit series automation"
        Paths = @("scripts/create_commit_series.ps1")
    },
    @{
        Message = "backend: add local environment template"
        Paths = @("backend/.env.example")
    },
    @{
        Message = "backend: ignore runtime artifacts"
        Paths = @("backend/.gitignore")
    },
    @{
        Message = "backend: add application settings"
        Paths = @("backend/config.py")
    },
    @{
        Message = "backend: add package markers"
        Paths = @(
            "backend/models/__init__.py",
            "backend/routes/__init__.py",
            "backend/services/__init__.py"
        )
    },
    @{
        Message = "backend: define API schemas"
        Paths = @("backend/models/schemas.py")
    },
    @{
        Message = "backend: implement repository cloning"
        Paths = @("backend/services/cloner.py")
    },
    @{
        Message = "backend: implement source parser"
        Paths = @("backend/services/parser.py")
    },
    @{
        Message = "backend: implement repository chunker"
        Paths = @("backend/services/chunker.py")
    },
    @{
        Message = "backend: implement vector store"
        Paths = @("backend/services/vector_store.py")
    },
    @{
        Message = "backend: implement RAG responses"
        Paths = @("backend/services/rag.py")
    },
    @{
        Message = "backend: implement diagram generation"
        Paths = @("backend/services/diagram_generator.py")
    },
    @{
        Message = "backend: persist repository metadata"
        Paths = @("backend/services/repo_store.py")
    },
    @{
        Message = "backend: add repository routes"
        Paths = @("backend/routes/repo.py")
    },
    @{
        Message = "backend: add chat routes"
        Paths = @("backend/routes/chat.py")
    },
    @{
        Message = "backend: add diagram routes"
        Paths = @("backend/routes/diagrams.py")
    },
    @{
        Message = "backend: wire FastAPI application"
        Paths = @("backend/main.py")
    },
    @{
        Message = "backend: add safe development runner"
        Paths = @("backend/dev.py")
    },
    @{
        Message = "backend: update project metadata"
        Paths = @("backend/pyproject.toml")
    },
    @{
        Message = "backend: update dependency lockfile"
        Paths = @("backend/uv.lock")
    },
    @{
        Message = "frontend: update package manifest"
        Paths = @("frontend/package.json")
    },
    @{
        Message = "frontend: update dependency lockfile"
        Paths = @("frontend/package-lock.json")
    },
    @{
        Message = "frontend: build application layout"
        Paths = @("frontend/app/layout.tsx")
    },
    @{
        Message = "frontend: add global design system"
        Paths = @("frontend/app/globals.css")
    },
    @{
        Message = "frontend: build landing experience"
        Paths = @("frontend/app/page.tsx")
    },
    @{
        Message = "frontend: add repository dashboard"
        Paths = @("frontend/app/repo/[id]/page.tsx")
    }
)

if ($needed -ne $commits.Count) {
    throw "Commit plan has $($commits.Count) commits, but $needed commits are needed to reach $TargetTotalCommits from $currentCount."
}

foreach ($commit in $commits) {
    foreach ($path in $commit.Paths) {
        & git add -- ":(literal)$path"
    }

    $staged = & git diff --cached --name-only
    if (-not $staged) {
        throw "No staged changes for commit '$($commit.Message)'."
    }

    & git commit -m $commit.Message
}

$finalCount = [int](& git rev-list --count HEAD)
if ($finalCount -ne $TargetTotalCommits) {
    throw "Expected $TargetTotalCommits total commits, got $finalCount."
}

Write-Host "Created $($commits.Count) commits. Repository now has $finalCount commits."
