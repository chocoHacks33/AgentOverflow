"use client"

import Link from "next/link"
import { ArrowRight } from "lucide-react"
import { sponsors } from "@/lib/sponsors"

export function SponsorChannelsPreview() {
  return (
    <section className="px-4 py-12 lg:py-14">
      <div className="mx-auto max-w-4xl">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <h2 className="font-display text-lg font-semibold text-foreground">
            {sponsors.length} channels
          </h2>
          <Link
            href="/channels"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
          >
            View feed <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        <div className="flex flex-wrap gap-2">
          {sponsors.map((sponsor) => (
            <Link
              key={sponsor.slug}
              href={`/channels?active=${sponsor.slug}`}
              className="rounded-md border border-border/50 bg-card/30 px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-border hover:bg-card/50"
            >
              {sponsor.name.toLowerCase()}
            </Link>
          ))}
        </div>
      </div>
    </section>
  )
}
