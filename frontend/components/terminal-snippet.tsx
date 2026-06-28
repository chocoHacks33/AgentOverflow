"use client"

import { useState } from "react"
import { Check, Copy } from "lucide-react"

export function TerminalSnippet({ command, label }: { command: string; label?: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(command)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="w-full">
      {label && (
        <span className="mb-2 block text-xs font-medium text-muted-foreground">{label}</span>
      )}
      <div className="flex items-center gap-3 rounded-lg border border-border bg-card/80 px-4 py-3 shadow-sm">
        <span className="shrink-0 text-muted-foreground/60">$</span>
        <code className="min-w-0 flex-1 break-all font-mono text-sm leading-6 text-foreground">
          {command}
          <span className="animate-blink-cursor text-primary">|</span>
        </code>
        <button
          onClick={handleCopy}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          aria-label="Copy"
        >
          {copied ? <Check className="h-4 w-4 text-primary" /> : <Copy className="h-4 w-4" />}
        </button>
      </div>
    </div>
  )
}
