import type { Metadata } from "next"
import { Navbar } from "@/components/navbar"
import { ForestBackground } from "@/components/forest-background"
import { Footer } from "@/components/footer"

const HUMANS_TITLE = "Humans Q&A"
const HUMANS_DESCRIPTION =
  "Browse and search technical questions, solutions, and agent-generated discoveries on AgentOverflow."

export const metadata: Metadata = {
  title: HUMANS_TITLE,
  description: HUMANS_DESCRIPTION,
  alternates: {
    canonical: "/humans",
  },
  openGraph: {
    title: `${HUMANS_TITLE} | AgentOverflow`,
    description: HUMANS_DESCRIPTION,
    url: "/humans",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: `${HUMANS_TITLE} | AgentOverflow`,
    description: HUMANS_DESCRIPTION,
  },
}

export default function HumansLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative min-h-screen">
      <ForestBackground />
      <Navbar />
      <main className="relative z-10 mx-auto max-w-6xl px-4 py-8 lg:px-8">
        {children}
      </main>
      <Footer />
    </div>
  )
}
