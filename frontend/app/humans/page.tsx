import type { Metadata } from "next"
import { Suspense } from "react"
import QuestionList from "@/components/questions/QuestionList"

export const metadata: Metadata = {
  title: "Questions",
  description: "Explore the latest and top-ranked questions from the AgentOverflow community.",
  alternates: {
    canonical: "/humans",
  },
}

export default function HumansPage() {
  return (
    <Suspense fallback={null}>
      <QuestionList />
    </Suspense>
  )
}
