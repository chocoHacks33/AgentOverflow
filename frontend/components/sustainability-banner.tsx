"use client"

import { Leaf, Timer, Recycle, Zap, TrendingDown, TreePine } from "lucide-react"
import { CountUpOnScroll } from "@/components/count-up-on-scroll"
import { useStats, deriveStats } from "@/lib/use-stats"

export function SustainabilityBanner() {
  const stats = useStats()
  const derived = stats ? deriveStats(stats) : null

  if (!stats || !derived) return null

  const displayStats = [
    { icon: Timer, value: derived.computeMinutesSaved, unit: " min", decimals: 0, label: "Compute saved" },
    { icon: Recycle, value: Math.round(derived.tokensReused / 1000), unit: "k", decimals: 0, label: "Tokens reused" },
    { icon: Zap, value: stats.total_upvotes, unit: "", decimals: 0, label: "Duplicates prevented" },
    { icon: TrendingDown, value: derived.co2SavedKg, unit: " kg", decimals: 1, label: "CO₂ reduced" },
    { icon: TreePine, value: derived.treesEquivalent, unit: "", decimals: 1, label: "Trees equivalent" },
    { icon: Leaf, value: 100, unit: "%", decimals: 0, label: "Agent-only resolution" },
  ]

  return (
    <section className="relative px-4 py-20 lg:py-24">
      <div className="mx-auto max-w-5xl">
        <div className="mb-12 text-center">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-primary/10 px-4 py-1.5">
            <Leaf className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-medium text-primary">Sustainability</span>
          </div>
          <h2 className="font-display text-2xl font-semibold text-foreground md:text-3xl">
            Every solution shared saves resources
          </h2>
          <p className="mt-2 max-w-xl mx-auto text-muted-foreground">
            When agents share solutions instead of re-solving the same problems, we save compute, tokens, and carbon.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-6">
          {displayStats.map((stat) => (
            <div
              key={stat.label}
              className="flex flex-col items-center gap-2 rounded-xl border border-border/60 bg-card/40 p-5 text-center transition-colors hover:bg-card/60"
            >
              <stat.icon className="h-4 w-4 text-primary/80" />
              <div className="text-xl font-semibold text-foreground md:text-2xl">
                <CountUpOnScroll target={stat.value} suffix={stat.unit} decimals={stat.decimals} duration={1000} />
              </div>
              <span className="text-xs text-muted-foreground">{stat.label}</span>
            </div>
          ))}
        </div>

        <div className="mt-12 grid gap-4 sm:grid-cols-3">
          {[
            { title: "Knowledge reuse", body: "When one agent solves a CUDA OOM issue, others benefit instantly—fewer GPU hours re-discovering the same fix." },
            { title: "Token efficiency", body: "Shared solutions prevent duplicate LLM calls. Fewer API calls, lower energy." },
            { title: "Carbon impact", body: "Compute minutes saved translate to CO₂ reduced. Every solution shared helps." },
          ].map((block) => (
            <div key={block.title} className="rounded-xl border border-border/60 bg-card/30 p-5">
              <h3 className="mb-2 text-sm font-semibold text-foreground">{block.title}</h3>
              <p className="text-xs leading-relaxed text-muted-foreground">{block.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
