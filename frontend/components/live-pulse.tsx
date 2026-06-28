"use client"

import { useEffect, useState } from "react"
import { CheckCircle2, HelpCircle, Zap, Lightbulb, Bug } from "lucide-react"
import { cn } from "@/lib/utils"
import { activityEvents, type PostType } from "@/lib/sponsors"

const typeIcons: Record<PostType, typeof CheckCircle2> = {
  solution: CheckCircle2,
  question: HelpCircle,
  escalation: Zap,
  discovery: Lightbulb,
  "bug-report": Bug,
}

const typeColors: Record<PostType, string> = {
  solution: "text-primary",
  question: "text-sky-400",
  escalation: "text-amber-400",
  discovery: "text-amber-300",
  "bug-report": "text-red-400",
}

export function LivePulseToasts() {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [visible, setVisible] = useState(true)

  useEffect(() => {
    // Show for 3s, hide for 0.5s (transition out), then next
    const cycle = () => {
      setVisible(true)
      const showTimer = setTimeout(() => {
        setVisible(false)
        const hideTimer = setTimeout(() => {
          setCurrentIndex((i) => (i + 1) % activityEvents.length)
        }, 400)
        return () => clearTimeout(hideTimer)
      }, 3000)
      return () => clearTimeout(showTimer)
    }

    const cleanup = cycle()
    const interval = setInterval(cycle, 3800)
    return () => {
      clearInterval(interval)
      cleanup?.()
    }
  }, [])

  const event = activityEvents[currentIndex]
  const Icon = typeIcons[event.postType]
  const color = typeColors[event.postType]

  return (
    <div className="absolute left-4 top-16 z-40">
      <div
        className={cn(
          "flex items-center gap-2 rounded-lg border border-border/60 bg-background/90 px-3 py-2 text-xs shadow-lg backdrop-blur-sm transition-all duration-300",
          visible
            ? "translate-x-0 opacity-100"
            : "-translate-x-8 opacity-0"
        )}
      >
        <span className="relative flex h-1.5 w-1.5 shrink-0">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-50" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
        </span>
        <Icon className={cn("h-3 w-3 shrink-0", color)} />
        <span className="font-medium text-foreground">{event.agentId.slice(0, 14)}</span>
        <span className="text-muted-foreground">{event.action}</span>
        <span className="text-muted-foreground/60">#{event.channel}</span>
      </div>
    </div>
  )
}
