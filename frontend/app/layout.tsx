import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "CodeAtlas — GitHub Repository Analyzer & Architecture Visualizer",
  description:
    "Analyze any public GitHub repository with AI. Explore code structure, ask questions about the codebase, and generate UML architecture diagrams — all in seconds.",
  keywords: [
    "github",
    "code analysis",
    "UML",
    "architecture diagrams",
    "AI",
    "RAG",
    "codebase explorer",
  ],
  openGraph: {
    title: "CodeAtlas — GitHub Repository Analyzer",
    description:
      "AI-powered codebase analysis with architecture diagram generation.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable} h-full`}
      suppressHydrationWarning
    >
      <body className="min-h-full flex flex-col antialiased" suppressHydrationWarning>{children}</body>
    </html>
  );
}
