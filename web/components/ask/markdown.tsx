"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** The model's answer as Markdown (GFM tables, lists, code). No raw HTML: react-markdown escapes it by default. */
export function Markdown({ text }: { text: string }) {
  return (
    <div className="space-y-2 text-sm leading-relaxed break-words [&_strong]:font-semibold [&_strong]:text-paper">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer noopener" className="text-signal underline-offset-2 hover:underline">
              {children}
            </a>
          ),
          ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
          h1: ({ children }) => <p className="font-semibold text-paper">{children}</p>,
          h2: ({ children }) => <p className="font-semibold text-paper">{children}</p>,
          h3: ({ children }) => <p className="font-semibold text-paper">{children}</p>,
          code: ({ children, className }) =>
            className ? (
              <code className={className}>{children}</code>
            ) : (
              <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em] text-paper">{children}</code>
            ),
          pre: ({ children }) => <pre className="overflow-x-auto rounded-lg border border-border bg-background p-3 font-mono text-xs">{children}</pre>,
          table: ({ children }) => (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-xs">{children}</table>
            </div>
          ),
          th: ({ children }) => <th className="border-b border-border bg-card/60 px-2 py-1.5 text-left font-medium">{children}</th>,
          td: ({ children }) => <td className="border-b border-border/60 px-2 py-1.5">{children}</td>,
          blockquote: ({ children }) => <blockquote className="border-l-2 border-gold/50 pl-3 text-muted-foreground">{children}</blockquote>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
