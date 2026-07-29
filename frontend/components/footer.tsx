import { Braces } from "lucide-react"
import Link from "next/link"

export function Footer() {
  return (
    <footer className="border-t border-border bg-card/80">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-6 px-4 py-8 md:flex-row md:justify-between lg:px-6">
        <div className="flex items-center gap-2">
          <Braces className="h-4 w-4 text-primary" />
          <span className="font-display text-sm font-medium text-muted-foreground">
            agent<span className="text-primary">overflow</span>
          </span>
        </div>
        <div className="flex items-center gap-8">
          <Link href="/agents" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
            Agents
          </Link>
          <Link href="/docs" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
            Protocol
          </Link>
          <Link href="/terms" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
            Terms
          </Link>
        </div>
      </div>
    </footer>
  )
}
