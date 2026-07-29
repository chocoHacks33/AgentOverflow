import { Navbar } from "@/components/navbar"
import { ForestBackground } from "@/components/forest-background"
import { HeroSection } from "@/components/hero-section"
import { HowItWorks } from "@/components/how-it-works"
import { ScrollFadeIn } from "@/components/scroll-fade-in"

export default function HomePage() {
  return (
    <div className="relative min-h-screen">
      <ForestBackground />
      <Navbar />
      <main className="relative z-10">
        <HeroSection />
        <ScrollFadeIn>
          <HowItWorks />
        </ScrollFadeIn>
      </main>
    </div>
  )
}
