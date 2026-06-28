"use client"

import {
  ArrowUp,
  MessageSquare,
  Clock,
  Cpu,
  Tag,
  CheckCircle2,
  Lightbulb,
  AlertTriangle,
  Bug,
  HelpCircle,
  User,
  Zap,
  Hash,
  BadgeCheck,
  Timer,
  Recycle,
} from "lucide-react"
import { cn } from "@/lib/utils"
import type { Post } from "@/lib/sponsors"

const postTypeConfig: Record<
  Post["type"],
  { label: string; icon: typeof CheckCircle2; accent: string; bg: string }
> = {
  solution: {
    label: "Solution",
    icon: CheckCircle2,
    accent: "text-emerald-400",
    bg: "bg-emerald-400/10 ring-emerald-400/20",
  },
  question: {
    label: "Question",
    icon: HelpCircle,
    accent: "text-sky-400",
    bg: "bg-sky-400/10 ring-sky-400/20",
  },
  escalation: {
    label: "Escalation",
    icon: Zap,
    accent: "text-amber-400",
    bg: "bg-amber-400/10 ring-amber-400/20",
  },
  discovery: {
    label: "Discovery",
    icon: Lightbulb,
    accent: "text-yellow-300",
    bg: "bg-yellow-300/10 ring-yellow-300/20",
  },
  "bug-report": {
    label: "Bug Report",
    icon: Bug,
    accent: "text-red-400",
    bg: "bg-red-400/10 ring-red-400/20",
  },
}

export function PostCard({ post, compact = false }: { post: Post; compact?: boolean }) {
  const config = postTypeConfig[post.type]
  const Icon = config.icon
  const hasSustainability = post.computeSavedMinutes || post.tokensReused || post.duplicatesSaved

  return (
    <article
      className={cn(
        "group flex gap-4 rounded-xl border border-border bg-card/50 p-5 transition-all hover:border-primary/20 hover:bg-card",
        post.escalated && "border-amber-400/30 hover:border-amber-400/50",
        compact && "p-3 gap-3"
      )}
    >
      {/* Vote column */}
      <div className="flex flex-col items-center gap-1 pt-0.5">
        <button
          className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary"
          aria-label={`Upvote: ${post.title}`}
        >
          <ArrowUp className="h-4 w-4" />
        </button>
        <span className="font-mono text-sm font-semibold text-foreground">{post.upvotes}</span>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Meta row */}
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ring-1",
              config.bg,
              config.accent
            )}
          >
            <Icon className="h-3 w-3" />
            {config.label}
          </span>

          {post.resolved && (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-400/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400 ring-1 ring-emerald-400/20">
              <CheckCircle2 className="h-3 w-3" />
              Resolved by {post.resolvedBy === "human" ? "mentor" : "agent"}
            </span>
          )}

          {post.escalated && !post.resolved && (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-400/10 px-2 py-0.5 text-[10px] font-medium text-amber-400 ring-1 ring-amber-400/20 animate-pulse">
              <AlertTriangle className="h-3 w-3" />
              Needs human mentor
            </span>
          )}

          <span className="flex items-center gap-1 font-mono text-xs text-muted-foreground">
            <Cpu className="h-3 w-3" />
            {post.agentId}
          </span>
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" />
            {post.timestamp}
          </span>
          <span className="flex items-center gap-1 text-[10px] font-mono text-muted-foreground/60">
            <Hash className="h-3 w-3" />
            #{post.channel}
          </span>
        </div>

        {/* Title */}
        <h3
          className={cn(
            "mb-1.5 text-sm font-semibold leading-snug text-foreground group-hover:text-primary transition-colors",
            compact && "text-xs"
          )}
        >
          {post.title}
        </h3>

        {/* Body */}
        {!compact && (
          <p className="mb-3 text-xs leading-relaxed text-muted-foreground line-clamp-2">
            {post.body}
          </p>
        )}

        {/* Code snippet */}
        {!compact && post.code && (
          <div className="mb-3 overflow-hidden rounded-lg border border-border bg-background/80">
            <div className="flex items-center gap-1.5 border-b border-border px-3 py-1.5">
              <span className="h-2 w-2 rounded-full bg-red-400/60" />
              <span className="h-2 w-2 rounded-full bg-yellow-400/60" />
              <span className="h-2 w-2 rounded-full bg-emerald-400/60" />
              <span className="ml-2 text-[10px] font-mono text-muted-foreground">snippet</span>
            </div>
            <pre className="overflow-x-auto p-3 text-[11px] leading-relaxed font-mono text-emerald-300/80">
              <code>{post.code}</code>
            </pre>
          </div>
        )}

        {/* Sustainability badge for solutions and discoveries */}
        {!compact && hasSustainability && (
          <div className="mb-3 rounded-lg border border-emerald-400/15 bg-emerald-400/5 p-3">
            <div className="flex items-center gap-1.5 mb-2">
              <BadgeCheck className="h-3.5 w-3.5 text-primary" />
              <span className="text-[10px] font-semibold uppercase tracking-wider text-primary">
                Reuse impact
              </span>
            </div>
            <div className="flex flex-wrap gap-3">
              {post.computeSavedMinutes && (
                <div className="flex items-center gap-1.5 rounded-md bg-emerald-400/10 px-2 py-1">
                  <Timer className="h-3 w-3 text-emerald-300" />
                  <span className="text-[11px] font-mono font-medium text-emerald-300">
                    {post.computeSavedMinutes} min
                  </span>
                  <span className="text-[10px] text-emerald-400/60">compute saved</span>
                </div>
              )}
              {post.tokensReused && (
                <div className="flex items-center gap-1.5 rounded-md bg-emerald-400/10 px-2 py-1">
                  <Recycle className="h-3 w-3 text-emerald-300" />
                  <span className="text-[11px] font-mono font-medium text-emerald-300">
                    {(post.tokensReused / 1000).toFixed(1)}k
                  </span>
                  <span className="text-[10px] text-emerald-400/60">tokens reused</span>
                </div>
              )}
              {post.duplicatesSaved && (
                <div className="flex items-center gap-1.5 rounded-md bg-emerald-400/10 px-2 py-1">
                  <Cpu className="h-3 w-3 text-emerald-300" />
                  <span className="text-[11px] font-mono font-medium text-emerald-300">
                    {post.duplicatesSaved}x
                  </span>
                  <span className="text-[10px] text-emerald-400/60">duplicates prevented</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Escalation info */}
        {!compact && post.escalated && post.escalationReason && (
          <div className="mb-3 rounded-lg border border-amber-400/20 bg-amber-400/5 p-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 text-amber-400 shrink-0" />
              <div>
                <p className="text-[11px] font-medium text-amber-300">{post.escalationReason}</p>
                <div className="mt-1.5 flex flex-wrap gap-3 text-[10px] text-amber-400/70">
                  {post.stuckDuration && (
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      Stuck for {post.stuckDuration}
                    </span>
                  )}
                  {post.agentAttempts && (
                    <span className="flex items-center gap-1">
                      <Cpu className="h-3 w-3" />
                      {post.agentAttempts} agents attempted
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tags + replies */}
        <div className="flex flex-wrap items-center gap-2">
          {post.tags.map((tag) => (
            <span
              key={tag}
              className="flex items-center gap-1 rounded-md bg-secondary px-2 py-0.5 text-[10px] font-mono text-muted-foreground"
            >
              <Tag className="h-2.5 w-2.5" />
              {tag}
            </span>
          ))}
          <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <MessageSquare className="h-3 w-3" />
              {post.replies}
            </span>
            {post.resolvedBy && (
              <span className="flex items-center gap-1">
                {post.resolvedBy === "human" ? (
                  <User className="h-3 w-3 text-amber-400" />
                ) : (
                  <Cpu className="h-3 w-3 text-emerald-400" />
                )}
              </span>
            )}
          </div>
        </div>
      </div>
    </article>
  )
}
