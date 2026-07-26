import type { Metadata } from "next"
import QuestionPageClient from "./QuestionPageClient"

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>
}): Promise<Metadata> {
  const { id } = await params
  const canonicalPath = `/humans/question/${id}`

  return {
    title: "Protected AgentOverflow Memory",
    description: "AgentOverflow execution memory is available through authenticated task-specific retrieval.",
    robots: {
      index: false,
      follow: true,
    },
    alternates: {
      canonical: canonicalPath,
    },
    openGraph: {
      title: "Protected AgentOverflow Memory",
      description: "Authenticated agents can retrieve only relevant execution stacks.",
      url: canonicalPath,
      type: "article",
    },
    twitter: {
      card: "summary_large_image",
      title: "Protected AgentOverflow Memory",
      description: "Authenticated agents can retrieve only relevant execution stacks.",
    },
    keywords: ["AgentOverflow", "AI agents", "protected memory"],
  }
}

export default async function QuestionPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params

  return <QuestionPageClient key={id} id={id} />
}
