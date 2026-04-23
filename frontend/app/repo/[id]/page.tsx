"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

/* ── Types ──────────────────────────────────────────────────── */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface LanguageStat {
  language: string;
  file_count: number;
  chunk_count: number;
  percentage: number;
}

interface FileTreeNode {
  name: string;
  path: string;
  is_dir: boolean;
  children: FileTreeNode[];
  language?: string | null;
  size?: number | null;
}

interface RepoInfo {
  repo_id: string;
  name: string;
  url: string;
  total_files: number;
  total_chunks: number;
  languages: LanguageStat[];
  file_tree: FileTreeNode | null;
  analyzed_at: string;
}

interface Citation {
  file_path: string;
  start_line: number;
  end_line: number;
  chunk_type: string;
  name: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

interface Diagram {
  type: string;
  title: string;
  description: string;
  mermaid_code: string;
}

/* ── Language Colors ────────────────────────────────────────── */

const LANG_COLORS: Record<string, string> = {
  python: "#3572A5",
  javascript: "#f1e05a",
  typescript: "#3178c6",
  java: "#b07219",
  go: "#00ADD8",
  rust: "#dea584",
  c: "#555555",
  cpp: "#f34b7d",
  ruby: "#701516",
  php: "#4F5D95",
  csharp: "#178600",
  swift: "#F05138",
  kotlin: "#A97BFF",
  html: "#e34c26",
  css: "#563d7c",
  scss: "#c6538c",
  shell: "#89e051",
  markdown: "#083fa1",
  yaml: "#cb171e",
  json: "#292929",
  sql: "#e38c00",
};

const LANG_ICONS: Record<string, string> = {
  python: "🐍",
  javascript: "⚡",
  typescript: "📘",
  java: "☕",
  go: "🐹",
  rust: "🦀",
  c: "⚙️",
  cpp: "⚙️",
  markdown: "📝",
  html: "🌐",
  css: "🎨",
  json: "📋",
  yaml: "⚙️",
  shell: "🐚",
};

/* ── File Icon Helper ───────────────────────────────────────── */

function getFileIcon(node: FileTreeNode): string {
  if (node.is_dir) return "📁";
  if (node.language && LANG_ICONS[node.language]) return LANG_ICONS[node.language];
  return "📄";
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Renders an emoji using dangerouslySetInnerHTML so React never manages
 * the text node inside. This prevents browser extensions (Jetski, Grammarly,
 * etc.) from breaking React's DOM reconciliation when they wrap emoji text
 * in their own `<span>` elements.
 */
function Icon({ emoji, className }: { emoji: string; className?: string }) {
  return (
    <span
      className={className}
      dangerouslySetInnerHTML={{ __html: emoji }}
    />
  );
}

/* ── Markdown Renderer ─────────────────────────────────────── */

function MarkdownRenderer({ content }: { content: string }) {
  const components = useMemo(
    () => ({
      // Code blocks with syntax highlighting
      code({
        className,
        children,
        ...props
      }: React.ComponentPropsWithoutRef<"code"> & { className?: string }) {
        const match = /language-(\w+)/.exec(className || "");
        const codeString = String(children).replace(/\n$/, "");

        if (match) {
          return (
            <div className="relative group my-3 rounded-xl overflow-hidden border border-[var(--color-border-primary)]">
              <div className="flex items-center justify-between px-4 py-2 bg-[var(--color-bg-tertiary)] border-b border-[var(--color-border-primary)]">
                <span className="text-xs font-mono text-[var(--color-text-tertiary)] uppercase tracking-wider">
                  {match[1]}
                </span>
                <button
                  onClick={() => navigator.clipboard.writeText(codeString)}
                  className="text-xs text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  Copy
                </button>
              </div>
              <SyntaxHighlighter
                style={oneDark}
                language={match[1]}
                PreTag="div"
                customStyle={{
                  margin: 0,
                  borderRadius: 0,
                  background: "var(--color-bg-tertiary)",
                  fontSize: "13px",
                  lineHeight: "1.6",
                }}
              >
                {codeString}
              </SyntaxHighlighter>
            </div>
          );
        }

        // Inline code
        return (
          <code
            className="px-1.5 py-0.5 rounded-md bg-[var(--color-bg-tertiary)] border border-[var(--color-border-subtle)] text-[var(--color-brand-glow)] font-mono text-[0.85em]"
            {...props}
          >
            {children}
          </code>
        );
      },

      // Headings
      h1: ({ children, ...props }: React.ComponentPropsWithoutRef<"h1">) => (
        <h3 className="text-lg font-bold mt-5 mb-2 text-[var(--color-text-primary)] border-b border-[var(--color-border-subtle)] pb-2" {...props}>
          {children}
        </h3>
      ),
      h2: ({ children, ...props }: React.ComponentPropsWithoutRef<"h2">) => (
        <h4 className="text-base font-bold mt-4 mb-2 text-[var(--color-text-primary)]" {...props}>
          {children}
        </h4>
      ),
      h3: ({ children, ...props }: React.ComponentPropsWithoutRef<"h3">) => (
        <h5 className="text-sm font-bold mt-3 mb-1.5 text-[var(--color-text-primary)]" {...props}>
          {children}
        </h5>
      ),

      // Paragraphs
      p: ({ children, ...props }: React.ComponentPropsWithoutRef<"p">) => (
        <p className="text-sm leading-relaxed mb-3 text-[var(--color-text-secondary)] last:mb-0" {...props}>
          {children}
        </p>
      ),

      // Lists
      ul: ({ children, ...props }: React.ComponentPropsWithoutRef<"ul">) => (
        <ul className="text-sm space-y-1.5 mb-3 ml-1" {...props}>
          {children}
        </ul>
      ),
      ol: ({ children, ...props }: React.ComponentPropsWithoutRef<"ol">) => (
        <ol className="text-sm space-y-1.5 mb-3 ml-1 list-decimal list-inside" {...props}>
          {children}
        </ol>
      ),
      li: ({ children, ...props }: React.ComponentPropsWithoutRef<"li">) => (
        <li className="text-[var(--color-text-secondary)] leading-relaxed flex items-start gap-2" {...props}>
          <span className="text-indigo-400 mt-1.5 flex-shrink-0 text-[8px]">●</span>
          <span className="flex-1">{children}</span>
        </li>
      ),

      // Links
      a: ({ children, href, ...props }: React.ComponentPropsWithoutRef<"a">) => (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--color-brand-glow)] hover:text-indigo-300 underline underline-offset-2 decoration-indigo-500/40 hover:decoration-indigo-400 transition-colors"
          {...props}
        >
          {children}
        </a>
      ),

      // Blockquotes
      blockquote: ({ children, ...props }: React.ComponentPropsWithoutRef<"blockquote">) => (
        <blockquote
          className="border-l-2 border-indigo-500/50 pl-4 my-3 text-[var(--color-text-tertiary)] italic"
          {...props}
        >
          {children}
        </blockquote>
      ),

      // Tables
      table: ({ children, ...props }: React.ComponentPropsWithoutRef<"table">) => (
        <div className="overflow-x-auto my-3 rounded-lg border border-[var(--color-border-primary)]">
          <table className="w-full text-sm" {...props}>
            {children}
          </table>
        </div>
      ),
      thead: ({ children, ...props }: React.ComponentPropsWithoutRef<"thead">) => (
        <thead className="bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]" {...props}>
          {children}
        </thead>
      ),
      th: ({ children, ...props }: React.ComponentPropsWithoutRef<"th">) => (
        <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider" {...props}>
          {children}
        </th>
      ),
      td: ({ children, ...props }: React.ComponentPropsWithoutRef<"td">) => (
        <td className="px-3 py-2 border-t border-[var(--color-border-subtle)] text-[var(--color-text-secondary)]" {...props}>
          {children}
        </td>
      ),

      // Horizontal rule
      hr: (props: React.ComponentPropsWithoutRef<"hr">) => (
        <hr className="my-4 border-[var(--color-border-subtle)]" {...props} />
      ),

      // Strong / emphasis
      strong: ({ children, ...props }: React.ComponentPropsWithoutRef<"strong">) => (
        <strong className="font-semibold text-[var(--color-text-primary)]" {...props}>
          {children}
        </strong>
      ),
      em: ({ children, ...props }: React.ComponentPropsWithoutRef<"em">) => (
        <em className="italic text-[var(--color-text-secondary)]" {...props}>
          {children}
        </em>
      ),
    }),
    []
  );

  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════
   Dashboard Page
   ══════════════════════════════════════════════════════════════ */

export default function RepoDashboard() {
  const params = useParams();
  const router = useRouter();
  const repoId = params.id as string;

  const [info, setInfo] = useState<RepoInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"chat" | "diagrams" | "explorer">(
    "chat"
  );

  useEffect(() => {
    let cancelled = false;

    async function loadRepoInfo() {
      try {
        const res = await fetch(`${API_BASE}/api/repo/${repoId}/info`);
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || "Failed to load repository info");
        }
        const data = await res.json();
        if (!cancelled) {
          setInfo(data);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadRepoInfo();

    return () => {
      cancelled = true;
    };
  }, [repoId]);

  if (loading) {
    return <LoadingScreen />;
  }

  if (error || !info) {
    return <ErrorScreen message={error || "Repository not found"} onBack={() => router.push("/")} />;
  }

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-bg-primary)]">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-[var(--color-border-primary)] bg-[var(--color-bg-primary)]/80 backdrop-blur-xl">
        <div className="flex items-center justify-between px-4 md:px-8 py-3">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/")}
              className="flex items-center gap-2 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
              aria-label="Back to home"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
            </button>
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-cyan-500 flex items-center justify-center text-sm">
                <Icon emoji="🗺️" />
              </div>
              <div>
                <h1 className="text-base font-bold tracking-tight">
                  {info.name}
                </h1>
                <p className="text-xs text-[var(--color-text-tertiary)] font-mono">
                  {info.total_files} files · {info.total_chunks} chunks
                </p>
              </div>
            </div>
          </div>

          {/* Tabs */}
          <nav className="flex items-center gap-1 p-1 rounded-xl bg-[var(--color-bg-secondary)] border border-[var(--color-border-subtle)]">
            {(["chat", "diagrams", "explorer"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 text-sm font-medium rounded-lg capitalize transition-all duration-200 ${
                  activeTab === tab
                    ? "bg-gradient-to-r from-indigo-500 to-cyan-500 text-white shadow-md"
                    : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-tertiary)]"
                }`}
              >
                <Icon emoji={tab === "chat" ? "💬" : tab === "diagrams" ? "📊" : "📂"} className="mr-1" />
                {tab}
              </button>
            ))}
          </nav>
        </div>

        {/* Language Bar */}
        <div className="h-1 flex">
          {info.languages.map((lang) => (
            <div
              key={lang.language}
              style={{
                width: `${lang.percentage}%`,
                backgroundColor: LANG_COLORS[lang.language] || "#6b7280",
              }}
              title={`${lang.language}: ${lang.percentage}%`}
            />
          ))}
        </div>
      </header>

      {/* Tab Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === "chat" && <ChatTab repoId={repoId} repoName={info.name} />}
        {activeTab === "diagrams" && <DiagramsTab repoId={repoId} />}
        {activeTab === "explorer" && <ExplorerTab fileTree={info.file_tree} languages={info.languages} />}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════
   Chat Tab
   ══════════════════════════════════════════════════════════════ */

function ChatTab({ repoId, repoName }: { repoId: string; repoName: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const sendMessage = async () => {
    const question = input.trim();
    if (!question || isStreaming) return;

    setInput("");
    setIsStreaming(true);

    const userMsg: ChatMessage = { role: "user", content: question };
    setMessages((prev) => [...prev, userMsg]);

    // Add placeholder assistant message
    const assistantMsg: ChatMessage = {
      role: "assistant",
      content: "",
      citations: [],
    };
    setMessages((prev) => [...prev, assistantMsg]);

    try {
      const history = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const res = await fetch(`${API_BASE}/api/chat/${repoId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question, history }),
      });

      if (!res.ok) {
        throw new Error("Failed to get response");
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) throw new Error("No response body");

      let fullContent = "";
      let citations: Citation[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value, { stream: true });
        const lines = text.split("\n");

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const jsonStr = line.slice(6).trim();
          if (!jsonStr) continue;

          try {
            const event = JSON.parse(jsonStr);

            if (event.type === "citations") {
              citations = event.content;
            } else if (event.type === "token") {
              fullContent += event.content;
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: fullContent,
                  citations,
                };
                return updated;
              });
            } else if (event.type === "error") {
              fullContent += `\n\n⚠️ Error: ${event.content}`;
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: fullContent,
                  citations,
                };
                return updated;
              });
            }
          } catch {
            // Skip invalid JSON
          }
        }
      }
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : "Something went wrong";
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          content: `⚠️ ${errMsg}`,
        };
        return updated;
      });
    } finally {
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const suggestedQuestions = [
    `What is the main purpose of ${repoName}?`,
    "What are the key classes and their relationships?",
    "Explain the project architecture and folder structure.",
    "What design patterns are used in this codebase?",
  ];

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)]">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6">
        <div className="max-w-3xl mx-auto space-y-6">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full min-h-[50vh]">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500/20 to-cyan-500/20 border border-[var(--color-border-accent)] flex items-center justify-center text-3xl mb-6 animate-float">
                <Icon emoji="💬" />
              </div>
              <h3 className="text-xl font-bold mb-2">Ask about the codebase</h3>
              <p className="text-[var(--color-text-secondary)] text-sm mb-8 text-center max-w-md">
                I&apos;ve analyzed the repository and indexed all the code. Ask me anything about the
                structure, patterns, or functionality.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
                {suggestedQuestions.map((q) => (
                  <button
                    key={q}
                    onClick={() => {
                      setInput(q);
                      inputRef.current?.focus();
                    }}
                    className="text-left p-3 rounded-xl border border-[var(--color-border-subtle)] hover:border-[var(--color-border-accent)] bg-[var(--color-bg-secondary)] hover:bg-[var(--color-bg-tertiary)] text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-all duration-200"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg, i) => (
              <div
                key={i}
                className={`animate-fade-in-up flex gap-3 ${
                  msg.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                {msg.role === "assistant" && (
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-cyan-500 flex-shrink-0 flex items-center justify-center text-sm mt-1">
                    <Icon emoji="🗺️" />
                  </div>
                )}
                <div
                  className={`max-w-[80%] rounded-2xl px-5 py-3 ${
                    msg.role === "user"
                      ? "bg-gradient-to-r from-indigo-500 to-indigo-600 text-white"
                      : "bg-[var(--color-bg-secondary)] border border-[var(--color-border-primary)] text-[var(--color-text-primary)]"
                  }`}
                >
                  {msg.content ? (
                    <MarkdownRenderer content={msg.content} />
                  ) : (
                      <span className="flex items-center gap-2 text-[var(--color-text-tertiary)]">
                        <span className="flex gap-1">
                          <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: "0ms" }} />
                          <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: "150ms" }} />
                          <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: "300ms" }} />
                        </span>
                        Thinking...
                      </span>
                  )}
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-[var(--color-border-subtle)]">
                      <p className="text-xs text-[var(--color-text-tertiary)] mb-1.5 font-medium">
                        Sources:
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {msg.citations.map((c, j) => (
                          <span
                            key={j}
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[var(--color-bg-tertiary)] text-xs font-mono text-[var(--color-brand-glow)]"
                          >
                            <Icon emoji="📄" /> {c.file_path}
                            <span className="text-[var(--color-text-tertiary)]">
                              L{c.start_line}
                            </span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                {msg.role === "user" && (
                  <div className="w-8 h-8 rounded-lg bg-[var(--color-bg-elevated)] flex-shrink-0 flex items-center justify-center text-sm mt-1">
                    <Icon emoji="👤" />
                  </div>
                )}
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      <div className="border-t border-[var(--color-border-primary)] bg-[var(--color-bg-primary)]/80 backdrop-blur-xl px-4 md:px-8 py-4">
        <div className="max-w-3xl mx-auto flex items-end gap-3">
          <div className="flex-1 relative">
            <textarea
              ref={inputRef}
              id="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isStreaming}
              placeholder="Ask about the codebase..."
              rows={1}
              className="w-full resize-none rounded-xl bg-[var(--color-bg-secondary)] border border-[var(--color-border-primary)] px-4 py-3 text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)] outline-none focus:border-[var(--color-brand-primary)] focus:shadow-[var(--shadow-glow)] transition-all text-sm disabled:opacity-50"
              style={{ minHeight: "44px", maxHeight: "120px" }}
              aria-label="Chat message input"
            />
          </div>
          <button
            id="send-button"
            onClick={sendMessage}
            disabled={!input.trim() || isStreaming}
            className="flex items-center justify-center w-11 h-11 rounded-xl bg-gradient-to-r from-indigo-500 to-cyan-500 text-white disabled:opacity-40 disabled:cursor-not-allowed hover:from-indigo-400 hover:to-cyan-400 transition-all active:scale-95"
            aria-label="Send message"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19V5m0 0l-7 7m7-7l7 7" />
            </svg>
          </button>
        </div>
        <p className="text-center text-xs text-[var(--color-text-tertiary)] mt-2">
          Press Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════
   Diagrams Tab
   ══════════════════════════════════════════════════════════════ */

function DiagramsTab({ repoId }: { repoId: string }) {
  const [diagrams, setDiagrams] = useState<Diagram[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [activeDiagram, setActiveDiagram] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadDiagrams() {
      try {
        const res = await fetch(`${API_BASE}/api/diagrams/${repoId}`);
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) {
            setDiagrams(data.diagrams || []);
          }
        }
      } catch {
        // Diagrams may not exist yet
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadDiagrams();

    return () => {
      cancelled = true;
    };
  }, [repoId]);

  const generateDiagrams = async () => {
    setGenerating(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/diagrams/${repoId}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          types: ["class", "dependency", "architecture"],
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Generation failed");
      }
      const data = await res.json();
      setDiagrams(data.diagrams || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to generate");
    } finally {
      setGenerating(false);
    }
  };

  const copyMermaid = () => {
    if (diagrams[activeDiagram]) {
      navigator.clipboard.writeText(diagrams[activeDiagram].mermaid_code);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 rounded-2xl skeleton" />
          <div className="w-48 h-4 skeleton" />
        </div>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-5rem)] flex flex-col px-4 md:px-8 py-6">
      {diagrams.length === 0 ? (
        /* Empty State */
        <div className="flex-1 flex flex-col items-center justify-center">
          <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-indigo-500/20 to-cyan-500/20 border border-[var(--color-border-accent)] flex items-center justify-center text-4xl mb-6 animate-float">
            <Icon emoji="📊" />
          </div>
          <h3 className="text-xl font-bold mb-2">Architecture Diagrams</h3>
          <p className="text-[var(--color-text-secondary)] text-sm mb-8 text-center max-w-md">
            Generate class diagrams, dependency graphs, and architecture overviews
            from the analyzed codebase using AI.
          </p>
          {error && (
            <p className="text-sm text-red-400 mb-4 animate-fade-in">⚠ {error}</p>
          )}
          <button
            id="generate-diagrams-button"
            onClick={generateDiagrams}
            disabled={generating}
            className="flex items-center gap-2.5 px-6 py-3 rounded-xl font-semibold text-white bg-gradient-to-r from-indigo-500 to-cyan-500 hover:from-indigo-400 hover:to-cyan-400 disabled:opacity-60 transition-all hover:shadow-[var(--shadow-glow-lg)] active:scale-[0.98]"
          >
            {generating ? (
              <>
                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Generating with AI...
              </>
            ) : (
              <>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Generate Diagrams
              </>
            )}
          </button>
        </div>
      ) : (
        /* Diagrams View */
        <div className="flex-1 flex flex-col gap-4 min-h-0">
          {/* Diagram Selector */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {diagrams.map((d, i) => (
                <button
                  key={d.type}
                  onClick={() => setActiveDiagram(i)}
                  className={`px-4 py-2 text-sm font-medium rounded-lg transition-all ${
                    activeDiagram === i
                      ? "bg-[var(--color-bg-elevated)] text-[var(--color-text-primary)] border border-[var(--color-border-accent)] shadow-[var(--shadow-glow)]"
                      : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-tertiary)]"
                  }`}
                >
                  {d.title}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={copyMermaid}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-[var(--color-border-primary)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:border-[var(--color-border-accent)] transition-all"
                title="Copy Mermaid code"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                </svg>
                Copy
              </button>
              <button
                onClick={generateDiagrams}
                disabled={generating}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-[var(--color-border-primary)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:border-[var(--color-border-accent)] transition-all disabled:opacity-50"
              >
                <svg className={`w-4 h-4 ${generating ? "animate-spin" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Regenerate
              </button>
            </div>
          </div>

          {/* Description */}
          {diagrams[activeDiagram] && (
            <p className="text-sm text-[var(--color-text-secondary)]">
              {diagrams[activeDiagram].description}
            </p>
          )}

          {/* Mermaid Renderer */}
          <div className="flex-1 min-h-0">
            {diagrams[activeDiagram] && (
              <MermaidRenderer code={diagrams[activeDiagram].mermaid_code} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════
   Mermaid Renderer Component
   ══════════════════════════════════════════════════════════════ */

function MermaidRenderer({ code }: { code: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [renderState, setRenderState] = useState<{
    code: string;
    error: string | null;
    rendered: boolean;
  }>({ code: "", error: null, rendered: false });

  const renderError = renderState.code === code ? renderState.error : null;
  const rendered = renderState.code === code && renderState.rendered;

  useEffect(() => {
    let cancelled = false;

    // Clear previous render
    if (containerRef.current) {
      containerRef.current.innerHTML = "";
    }

    const render = async () => {
      if (!containerRef.current || !code.trim()) return;

      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "dark",
          themeVariables: {
            primaryColor: "#6366f1",
            primaryTextColor: "#fafafa",
            primaryBorderColor: "#3f3f46",
            lineColor: "#71717a",
            secondaryColor: "#27272a",
            tertiaryColor: "#18181b",
            fontFamily: "var(--font-sans)",
            fontSize: "14px",
          },
          flowchart: { curve: "basis" },
          securityLevel: "loose",
        });

        const id = `mermaid-${Date.now()}`;
        const { svg } = await mermaid.render(id, code);

        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
          setRenderState({ code, error: null, rendered: true });
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setRenderState({
            code,
            error: err instanceof Error ? err.message : "Render failed",
            rendered: false,
          });
        }
      }
    };

    render();
    return () => { cancelled = true; };
  }, [code]);

  return (
    <div className="h-full rounded-xl border border-[var(--color-border-primary)] bg-[var(--color-bg-secondary)] overflow-auto relative">
      {renderError ? (
        <div className="p-6">
          <div className="flex items-center gap-2 text-amber-400 mb-3">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
            <span className="text-sm font-medium">Diagram render issue — showing raw Mermaid code:</span>
          </div>
          <pre className="text-sm font-mono text-[var(--color-text-secondary)] whitespace-pre-wrap">{code}</pre>
        </div>
      ) : (
        <>
          {/* Loading overlay — rendered OUTSIDE the mermaid container */}
          {!rendered && (
            <div className="absolute inset-0 flex items-center justify-center bg-[var(--color-bg-secondary)] z-10">
              <span className="text-sm text-[var(--color-text-tertiary)] animate-pulse">
                Rendering diagram...
              </span>
            </div>
          )}
          {/* Mermaid-only container — React NEVER puts children here */}
          <div
            ref={containerRef}
            className="p-6 flex items-center justify-center min-h-[300px]"
          />
        </>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════
   Explorer Tab
   ══════════════════════════════════════════════════════════════ */

function ExplorerTab({
  fileTree,
  languages,
}: {
  fileTree: FileTreeNode | null;
  languages: LanguageStat[];
}) {
  if (!fileTree) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <p className="text-[var(--color-text-secondary)]">No file tree available</p>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-5rem)] flex gap-0 overflow-hidden">
      {/* File Tree */}
      <div className="w-full md:w-80 lg:w-96 border-r border-[var(--color-border-primary)] overflow-y-auto p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider mb-4 px-2">
          File Explorer
        </h3>
        <FileTreeView node={fileTree} depth={0} />
      </div>

      {/* Language Stats */}
      <div className="hidden md:flex flex-1 flex-col p-6 overflow-y-auto">
        <h3 className="text-lg font-bold mb-6">Language Breakdown</h3>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">
          {languages.map((lang) => (
            <div
              key={lang.language}
              className="flex items-center gap-4 p-4 rounded-xl bg-[var(--color-bg-secondary)] border border-[var(--color-border-primary)] hover:border-[var(--color-border-accent)] transition-all"
            >
              <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-[var(--color-bg-tertiary)] text-lg">
                <Icon emoji={LANG_ICONS[lang.language] || "📄"} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-semibold capitalize">
                    {lang.language}
                  </span>
                  <span className="text-sm text-[var(--color-text-secondary)]">
                    {lang.percentage}%
                  </span>
                </div>
                <div className="w-full h-2 rounded-full bg-[var(--color-bg-tertiary)] overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{
                      width: `${lang.percentage}%`,
                      backgroundColor: LANG_COLORS[lang.language] || "#6b7280",
                    }}
                  />
                </div>
                <div className="flex items-center gap-3 mt-1.5">
                  <span className="text-xs text-[var(--color-text-tertiary)]">
                    {lang.file_count} files
                  </span>
                  <span className="text-xs text-[var(--color-text-tertiary)]">
                    {lang.chunk_count} chunks
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── File Tree Recursive Component ─────────────────────────── */

function FileTreeView({
  node,
  depth,
}: {
  node: FileTreeNode;
  depth: number;
}) {
  const [expanded, setExpanded] = useState(depth < 2);

  if (!node.is_dir) {
    return (
      <div
        className="flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-[var(--color-bg-tertiary)] cursor-default transition-colors group text-sm"
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
      >
        <Icon emoji={getFileIcon(node)} className="text-sm flex-shrink-0" />
        <span className="truncate text-[var(--color-text-secondary)] group-hover:text-[var(--color-text-primary)]">
          {node.name}
        </span>
        {node.size != null && node.size > 0 && (
          <span className="ml-auto text-xs text-[var(--color-text-tertiary)] flex-shrink-0">
            {formatBytes(node.size)}
          </span>
        )}
      </div>
    );
  }

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-[var(--color-bg-tertiary)] transition-colors text-sm"
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
      >
        <svg
          className={`w-3.5 h-3.5 text-[var(--color-text-tertiary)] transition-transform flex-shrink-0 ${
            expanded ? "rotate-90" : ""
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        <Icon emoji={expanded ? "📂" : "📁"} className="text-sm flex-shrink-0" />
        <span className="truncate font-medium text-[var(--color-text-primary)]">
          {node.name}
        </span>
        <span className="ml-auto text-xs text-[var(--color-text-tertiary)] flex-shrink-0">
          {node.children.length}
        </span>
      </button>
      {expanded && (
        <div className="animate-fade-in">
          {node.children.map((child) => (
            <FileTreeView key={child.path} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════
   Loading & Error Screens
   ══════════════════════════════════════════════════════════════ */

function LoadingScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg-primary)]">
      <div className="flex flex-col items-center gap-5 animate-fade-in">
        <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-indigo-500 to-cyan-500 flex items-center justify-center text-2xl animate-pulse">
          <Icon emoji="🗺️" />
        </div>
        <div className="flex flex-col items-center gap-2">
          <div className="w-48 h-4 skeleton rounded-lg" />
          <div className="w-32 h-3 skeleton rounded-lg" />
        </div>
      </div>
    </div>
  );
}

function ErrorScreen({
  message,
  onBack,
}: {
  message: string;
  onBack: () => void;
}) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg-primary)]">
      <div className="flex flex-col items-center gap-5 animate-fade-in text-center max-w-md px-6">
        <div className="w-14 h-14 rounded-2xl bg-red-500/10 border border-red-500/30 flex items-center justify-center text-2xl">
          <Icon emoji="⚠️" />
        </div>
        <h2 className="text-xl font-bold">Something went wrong</h2>
        <p className="text-[var(--color-text-secondary)] text-sm">{message}</p>
        <button
          onClick={onBack}
          className="px-6 py-2.5 rounded-xl font-semibold text-white bg-gradient-to-r from-indigo-500 to-cyan-500 hover:from-indigo-400 hover:to-cyan-400 transition-all"
        >
          Back to Home
        </button>
      </div>
    </div>
  );
}
