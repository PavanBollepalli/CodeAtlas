"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";

/* ── Constants ──────────────────────────────────────────────── */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const EXAMPLE_REPOS = [
  {
    name: "fastapi/fastapi",
    url: "https://github.com/fastapi/fastapi",
    desc: "Modern Python web framework",
    lang: "Python",
  },
  {
    name: "expressjs/express",
    url: "https://github.com/expressjs/express",
    desc: "Fast, unopinionated Node.js framework",
    lang: "JavaScript",
  },
  {
    name: "gin-gonic/gin",
    url: "https://github.com/gin-gonic/gin",
    desc: "High-performance Go HTTP framework",
    lang: "Go",
  },
];

const FEATURES = [
  {
    icon: "🌳",
    title: "AST Parsing",
    desc: "Deep code structure analysis using abstract syntax tree parsing for Python, JS, TS, Java, Go, Rust, and C/C++.",
  },
  {
    icon: "🤖",
    title: "AI-Powered Q&A",
    desc: "Ask questions about any codebase. Get precise, cited answers powered by RAG and Llama 3.3 70B.",
  },
  {
    icon: "📊",
    title: "Auto Diagrams",
    desc: "Generate class diagrams, dependency graphs, and architecture overviews rendered with Mermaid.js.",
  },
  {
    icon: "🔍",
    title: "Code Explorer",
    desc: "Browse the repository file tree, explore parsed code structures, and understand module relationships.",
  },
];

/** Render emoji via innerHTML so browser extensions can't break React's DOM. */
function Icon({ emoji, className }: { emoji: string; className?: string }) {
  return <span className={className} dangerouslySetInnerHTML={{ __html: emoji }} />;
}

/* ── Main Page Component ────────────────────────────────────── */

export default function Home() {
  const router = useRouter();
  const [repoUrl, setRepoUrl] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleAnalyze = async () => {
    if (!repoUrl.trim()) {
      setError("Please enter a GitHub repository URL");
      return;
    }

    setError(null);
    setIsAnalyzing(true);
    setStatus("Submitting...");

    try {
      const res = await fetch(`${API_BASE}/api/repo/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: repoUrl.trim() }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Analysis failed (${res.status})`);
      }

      const data = await res.json();
      const repoId = data.repo_id;

      // Poll for completion
      setStatus("Cloning repository...");
      await pollStatus(repoId);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Something went wrong";
      setError(message);
      setIsAnalyzing(false);
      setStatus(null);
    }
  };

  const pollStatus = async (repoId: string) => {
    const maxAttempts = 120;
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      await new Promise((r) => setTimeout(r, 2000));

      try {
        const res = await fetch(`${API_BASE}/api/repo/${repoId}/status`);
        const data = await res.json();

        setStatus(data.progress || data.status);

        if (data.status === "ready") {
          router.push(`/repo/${repoId}`);
          return;
        }

        if (data.status === "error") {
          throw new Error(data.error || "Analysis failed");
        }
      } catch (err: unknown) {
        if (attempt === maxAttempts - 1) {
          const message =
            err instanceof Error ? err.message : "Analysis timed out";
          setError(message);
          setIsAnalyzing(false);
          setStatus(null);
          return;
        }
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !isAnalyzing) {
      handleAnalyze();
    }
  };

  return (
    <div className="relative min-h-screen flex flex-col overflow-hidden">
      {/* Background Effects */}
      <div className="mesh-bg" />
      <div className="grid-pattern fixed inset-0 z-0 opacity-30" />

      {/* Navbar */}
      <header className="relative z-10 flex items-center justify-between px-6 py-4 md:px-10 lg:px-16">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-500 shadow-lg">
            <Icon emoji="🗺️" className="text-xl" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">
            Code<span className="gradient-text">Atlas</span>
          </h1>
        </div>
        <a
          href="https://github.com"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border border-[var(--color-border-primary)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:border-[var(--color-border-accent)] transition-all duration-[var(--transition-normal)]"
        >
          <svg
            className="w-5 h-5"
            fill="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
              clipRule="evenodd"
            />
          </svg>
          GitHub
        </a>
      </header>

      {/* Hero Section */}
      <main className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 py-12 md:py-20">
        <div className="w-full max-w-3xl mx-auto text-center">
          {/* Badge */}
          <div
            className="animate-fade-in-down inline-flex items-center gap-2 px-4 py-1.5 mb-8 text-sm font-medium rounded-full border border-[var(--color-border-accent)] bg-[var(--color-bg-glass)] text-[var(--color-brand-glow)]"
            style={{ animationDelay: "0.1s", opacity: 0 }}
          >
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            AI-Powered Codebase Analysis
          </div>

          {/* Heading */}
          <h2
            className="animate-fade-in-up text-4xl md:text-6xl lg:text-7xl font-extrabold tracking-tight leading-[1.1] mb-6"
            style={{ animationDelay: "0.2s", opacity: 0 }}
          >
            <span className="gradient-text-hero">Understand Any</span>
            <br />
            <span className="text-[var(--color-text-primary)]">
              Codebase Instantly
            </span>
          </h2>

          {/* Subtitle */}
          <p
            className="animate-fade-in-up text-lg md:text-xl text-[var(--color-text-secondary)] max-w-xl mx-auto mb-12 leading-relaxed"
            style={{ animationDelay: "0.3s", opacity: 0 }}
          >
            Paste any public GitHub repo. Get AI-powered code analysis,
            interactive Q&A, and auto-generated architecture diagrams.
          </p>

          {/* Input Section */}
          <div
            className="animate-fade-in-up"
            style={{ animationDelay: "0.4s", opacity: 0 }}
          >
            <div
              className={`relative flex items-center gap-3 p-2 rounded-2xl border transition-all duration-300 ${
                error
                  ? "border-red-500/50 bg-red-500/5"
                  : "border-[var(--color-border-primary)] bg-[var(--color-bg-secondary)] focus-within:border-[var(--color-brand-primary)] focus-within:shadow-[var(--shadow-glow)]"
              }`}
            >
              <div className="pl-4 text-[var(--color-text-tertiary)]">
                <svg
                  className="w-5 h-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
                  />
                </svg>
              </div>
              <input
                ref={inputRef}
                id="repo-url-input"
                type="url"
                placeholder="https://github.com/owner/repository"
                value={repoUrl}
                onChange={(e) => {
                  setRepoUrl(e.target.value);
                  setError(null);
                }}
                onKeyDown={handleKeyDown}
                disabled={isAnalyzing}
                className="flex-1 bg-transparent text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)] outline-none text-base md:text-lg py-3 disabled:opacity-50 font-mono"
                aria-label="GitHub repository URL"
              />
              <button
                id="analyze-button"
                onClick={handleAnalyze}
                disabled={isAnalyzing}
                className="flex items-center gap-2.5 px-6 py-3 rounded-xl font-semibold text-white bg-gradient-to-r from-indigo-500 to-cyan-500 hover:from-indigo-400 hover:to-cyan-400 disabled:opacity-60 disabled:cursor-not-allowed transition-all duration-300 hover:shadow-[var(--shadow-glow-lg)] active:scale-[0.98] whitespace-nowrap"
              >
                {isAnalyzing ? (
                  <>
                    <svg
                      className="w-5 h-5 animate-spin"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      />
                    </svg>
                    Analyzing...
                  </>
                ) : (
                  <>
                    <svg
                      className="w-5 h-5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                      />
                    </svg>
                    Analyze
                  </>
                )}
              </button>
            </div>

            {/* Error Message */}
            {error && (
              <p className="mt-3 text-sm text-red-400 animate-fade-in-down">
                ⚠ {error}
              </p>
            )}

            {/* Status Message */}
            {status && !error && (
              <div className="mt-4 flex items-center justify-center gap-3 text-sm text-[var(--color-text-secondary)] animate-fade-in">
                <div className="flex gap-1">
                  <span
                    className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce"
                    style={{ animationDelay: "0ms" }}
                  />
                  <span
                    className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce"
                    style={{ animationDelay: "150ms" }}
                  />
                  <span
                    className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce"
                    style={{ animationDelay: "300ms" }}
                  />
                </div>
                {status}
              </div>
            )}
          </div>

          {/* Example Repos */}
          <div
            className="animate-fade-in-up mt-8 flex flex-wrap items-center justify-center gap-3"
            style={{ animationDelay: "0.5s", opacity: 0 }}
          >
            <span className="text-sm text-[var(--color-text-tertiary)]">
              Try:
            </span>
            {EXAMPLE_REPOS.map((repo) => (
              <button
                key={repo.name}
                onClick={() => {
                  setRepoUrl(repo.url);
                  setError(null);
                }}
                disabled={isAnalyzing}
                className="group flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg border border-[var(--color-border-subtle)] text-[var(--color-text-secondary)] hover:border-[var(--color-border-accent)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-glass)] transition-all duration-200 disabled:opacity-50"
              >
                <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-[var(--color-bg-tertiary)] text-[var(--color-brand-glow)] group-hover:bg-indigo-500/20">
                  {repo.lang}
                </span>
                {repo.name}
              </button>
            ))}
          </div>
        </div>

        {/* Features Grid */}
        <section className="w-full max-w-5xl mx-auto mt-24 md:mt-32 px-2">
          <h3
            className="animate-fade-in-up text-center text-2xl md:text-3xl font-bold mb-12 tracking-tight"
            style={{ animationDelay: "0.6s", opacity: 0 }}
          >
            How It{" "}
            <span className="gradient-text">Works</span>
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {FEATURES.map((feature, i) => (
              <div
                key={feature.title}
                className={`animate-fade-in-up glass-card p-6 group cursor-default`}
                style={{ animationDelay: `${0.7 + i * 0.1}s`, opacity: 0 }}
              >
                <div className="flex items-center justify-center w-12 h-12 mb-5 rounded-xl bg-gradient-to-br from-indigo-500/20 to-cyan-500/20 text-2xl group-hover:scale-110 transition-transform duration-300">
                  <Icon emoji={feature.icon} />
                </div>
                <h4 className="text-base font-semibold mb-2 text-[var(--color-text-primary)]">
                  {feature.title}
                </h4>
                <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">
                  {feature.desc}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* Pipeline Visualization */}
        <section
          className="animate-fade-in-up w-full max-w-4xl mx-auto mt-20 md:mt-28 mb-12"
          style={{ animationDelay: "1.1s", opacity: 0 }}
        >
          <div className="glass-card p-6 md:p-8">
            <h3 className="text-lg font-semibold mb-6 text-center">
              Analysis Pipeline
            </h3>
            <div className="flex flex-wrap items-center justify-center gap-3 md:gap-4">
              {[
                { step: "1", label: "Paste URL", icon: "🔗" },
                { step: "2", label: "Clone Repo", icon: "📥" },
                { step: "3", label: "AST Parse", icon: "🌳" },
                { step: "4", label: "Embed Chunks", icon: "📦" },
                { step: "5", label: "Query & Chat", icon: "💬" },
              ].map((item, i) => (
                <div key={item.step} className="flex items-center gap-3 md:gap-4">
                  <div className="flex flex-col items-center gap-2">
                    <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-[var(--color-bg-tertiary)] border border-[var(--color-border-primary)] text-xl">
                      <Icon emoji={item.icon} />
                    </div>
                    <span className="text-xs text-[var(--color-text-tertiary)] font-medium">
                      {item.label}
                    </span>
                  </div>
                  {i < 4 && (
                    <svg
                      className="w-5 h-5 text-[var(--color-text-tertiary)] hidden sm:block mb-5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 5l7 7-7 7"
                      />
                    </svg>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-[var(--color-border-subtle)] py-6 text-center">
        <p className="text-sm text-[var(--color-text-tertiary)]">
          Built with FastAPI, Groq, ChromaDB & Next.js —{" "}
          <span className="gradient-text font-medium">CodeAtlas</span>
        </p>
      </footer>
    </div>
  );
}
