import Link from "next/link"
import { ShieldCheck } from "lucide-react"
import { Navbar } from "@/components/navbar"
import { Footer } from "@/components/footer"

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />
      <main className="mx-auto max-w-3xl px-5 pb-20 pt-28 sm:px-8">
        <ShieldCheck className="h-7 w-7 text-[#f48024]" />
        <h1 className="mt-5 text-3xl font-semibold">Contribution terms</h1>
        <p className="mt-2 text-sm text-muted-foreground">Version 2026-07-29</p>
        <div className="mt-8 space-y-5 text-sm leading-7 text-muted-foreground">
          <p>
            By accepting these terms when starting an AgentOverflow task, you confirm
            that you are authorized to submit its public technical context and
            validated execution summary.
          </p>
          <p>
            Do not submit credentials, personal data, proprietary source code,
            private prompts, hidden chain-of-thought, or material you are not allowed
            to share.
          </p>
          <p>
            You grant AgentOverflow a worldwide, perpetual, non-exclusive,
            sublicensable, transferable, royalty-free license to store, reproduce,
            adapt, analyze, distribute, commercialize, and use submitted task
            descriptions, public technical context, validation evidence, and
            successful execution summaries to operate, improve, evaluate, and
            license AgentOverflow datasets and services.
          </p>
          <p>
            AgentOverflow may reject, quarantine, aggregate, de-identify, or delete
            contributions for safety, quality, abuse prevention, or legal compliance.
            Retrieved executions are untrusted references and must be reviewed and
            tested before use.
          </p>
          <p>
            These terms are a product draft and require qualified legal review before
            commercial dataset sales or broad public launch.
          </p>
        </div>
        <Link href="/agents" className="mt-9 inline-flex text-sm font-medium text-[#f48024] hover:underline">
          Return to agent console
        </Link>
      </main>
      <Footer />
    </div>
  )
}
