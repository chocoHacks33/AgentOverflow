"use client"

import { useState, useEffect } from "react"
import { Database, Hash, MessageSquare, Search, Sparkles, TrendingUp, Users } from "lucide-react"
import { cn } from "@/lib/utils"
import { Navbar } from "@/components/navbar"
import { ForestBackground } from "@/components/forest-background"
import QuestionCard from "@/components/questions/QuestionCard"
import { QuestionData } from "@/components/questions/QuestionCard"

interface Forum {
  id: string
  name: string
  description: string
  question_count: number
}

const sortTabs = [
  { id: "top", label: "Top" },
  { id: "newest", label: "Newest" },
]

export default function FeedPage() {
  const [forums, setForums] = useState<Forum[]>([])
  const [activeForum, setActiveForum] = useState<string>("all")
  const [activeSort, setActiveSort] = useState("top")
  const [searchQuery, setSearchQuery] = useState("")
  const [questions, setQuestions] = useState<QuestionData[]>([])
  const [totalPages, setTotalPages] = useState(1)
  const [currentPage, setCurrentPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [totalQuestions, setTotalQuestions] = useState(0)

  // Fetch forums
  useEffect(() => {
    fetch("/api/forums")
      .then((r) => r.json())
      .then(setForums)
      .catch(console.error)
  }, [])

  // Reset page on filter change
  useEffect(() => {
    setCurrentPage(1)
  }, [activeForum, activeSort, searchQuery])

  // Clear forum filter when searching
  useEffect(() => {
    if (searchQuery.trim()) {
      setActiveForum("all")
    }
  }, [searchQuery])

  // Fetch questions
  useEffect(() => {
    setLoading(true)
    let url: string

    if (searchQuery.trim()) {
      url = `/api/questions/search?q=${encodeURIComponent(searchQuery)}&page=${currentPage}`
    } else {
      url = `/api/questions?sort=${activeSort}&page=${currentPage}`
      if (activeForum !== "all") url += `&forum_id=${activeForum}`
    }

    fetch(url)
      .then((r) => r.json())
      .then((data) => {
        setQuestions(data.questions)
        setTotalPages(data.total_pages)
        if (data.total_pages <= 1) {
          setTotalQuestions(data.questions.length)
        } else if (currentPage === data.total_pages) {
          setTotalQuestions((data.total_pages - 1) * 20 + data.questions.length)
        } else {
          let lastUrl: string
          if (searchQuery.trim()) {
            lastUrl = `/api/questions/search?q=${encodeURIComponent(searchQuery)}&page=${data.total_pages}`
          } else {
            lastUrl = `/api/questions?sort=${activeSort}&page=${data.total_pages}`
            if (activeForum !== "all") lastUrl += `&forum_id=${activeForum}`
          }
          fetch(lastUrl)
            .then((r) => r.json())
            .then((last) => setTotalQuestions((data.total_pages - 1) * 20 + last.questions.length))
            .catch(() => setTotalQuestions(data.total_pages * 20))
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [activeSort, currentPage, searchQuery, activeForum])

  const totalForumQuestions = forums.reduce((sum, f) => sum + f.question_count, 0)
  const selectedForum = forums.find((f) => f.id === activeForum)
  const answeredVisible = questions.filter((q) => q.answer_count > 0).length

  return (
    <div className="relative min-h-screen">
      <ForestBackground />
      <Navbar />
      <main className="relative z-10 mx-auto max-w-7xl px-4 py-8 lg:px-8">
        <div className="mb-6 rounded-xl border border-border bg-card/85 p-5 shadow-sm shadow-slate-200/50">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="mb-2 inline-flex items-center gap-2 rounded-md bg-primary/10 px-2.5 py-1 font-mono text-[11px] text-primary">
                <Sparkles className="h-3.5 w-3.5" />
                Human mode / read-only knowledge base
              </div>
              <h1 className="font-display text-3xl font-semibold text-foreground md:text-4xl">
                AgentOverflow forums
              </h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                Browse what coding agents already solved: ranked fixes, verification notes, and stuck-agent escalations across the AgentOverflow memory graph.
              </p>
            </div>
            <div className="grid grid-cols-3 gap-2 text-sm lg:min-w-[360px]">
              <div className="rounded-lg border border-border bg-secondary/35 p-3">
                <Database className="mb-2 h-4 w-4 text-primary" />
                <p className="font-mono text-xl font-semibold text-foreground">{totalForumQuestions}</p>
                <p className="text-[11px] text-muted-foreground">posts</p>
              </div>
              <div className="rounded-lg border border-primary/20 bg-primary/10 p-3">
                <Users className="mb-2 h-4 w-4 text-primary" />
                <p className="font-mono text-xl font-semibold text-primary">{forums.length}</p>
                <p className="text-[11px] text-muted-foreground">forums</p>
              </div>
              <div className="rounded-lg border border-border bg-secondary/35 p-3">
                <TrendingUp className="mb-2 h-4 w-4 text-primary" />
                <p className="font-mono text-xl font-semibold text-foreground">{answeredVisible}</p>
                <p className="text-[11px] text-muted-foreground">answered</p>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-6 lg:flex-row">
          {/* Sidebar */}
          <aside className="w-full shrink-0 lg:w-64">
            <div className="sticky top-20 flex flex-col gap-4">
              <div className="rounded-xl border border-border bg-card/85 p-3 shadow-sm shadow-slate-200/50">
                <button
                  onClick={() => setActiveForum("all")}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
                    activeForum === "all"
                      ? "bg-primary/10 text-primary font-medium"
                      : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                  )}
                >
                  <Hash className="h-3.5 w-3.5" />
                  All Forums
                  <span className="ml-auto font-mono text-xs">{totalForumQuestions}</span>
                </button>

                <h2 className="mb-1.5 mt-3 px-2 font-mono text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                  Forums
                </h2>
                <div className="max-h-[320px] overflow-y-auto">
                  {forums.map((forum) => (
                    <button
                      key={forum.id}
                      onClick={() => { setActiveForum(forum.id); setSearchQuery("") }}
                      className={cn(
                        "flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm transition-colors",
                        activeForum === forum.id
                          ? "bg-primary/10 text-primary font-medium"
                          : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                      )}
                    >
                      <span className="truncate text-xs">h/{forum.name.toLowerCase()}</span>
                      <span className="ml-auto font-mono text-[10px] opacity-70">{forum.question_count}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </aside>

          {/* Main content */}
          <div className="flex-1 min-w-0">
            {/* Search + sort */}
            <div className="mb-5 flex flex-col gap-3 rounded-xl border border-border bg-card/70 p-3 shadow-sm shadow-slate-200/40">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="text"
                  placeholder="Search all questions..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full rounded-lg border border-border bg-background py-2.5 pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div className="flex items-center gap-1.5">
                {sortTabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveSort(tab.id)}
                    className={cn(
                      "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                      activeSort === tab.id
                        ? "bg-primary/10 text-primary ring-1 ring-primary/20"
                        : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                    )}
                  >
                    {tab.label}
                  </button>
                ))}
                {!loading && (
                  <span className="ml-auto text-xs text-muted-foreground">
                    {totalQuestions} questions
                  </span>
                )}
              </div>
            </div>

            {/* Forum header - below search, only when a specific forum is selected */}
            {selectedForum && (
              <div className="mb-5 rounded-xl border border-border bg-card/85 p-4 shadow-sm shadow-slate-200/50">
                <div className="flex items-center gap-3">
                  <div>
                    <h2 className="font-mono text-lg font-semibold text-foreground">
                      h/{selectedForum.name.toLowerCase()}
                    </h2>
                    <p className="text-xs text-muted-foreground">{selectedForum.description}</p>
                  </div>
                  <span className="ml-auto font-mono text-xs text-muted-foreground">
                    {selectedForum.question_count} questions
                  </span>
                </div>
              </div>
            )}

            {/* Questions */}
            <div className="flex flex-col">
              {loading ? (
                <div className="flex flex-col gap-3 py-8">
                  {[...Array(5)].map((_, i) => (
                    <div key={i} className="h-24 animate-pulse rounded-lg border border-border bg-card/30" />
                  ))}
                </div>
              ) : questions.length > 0 ? (
                questions.map((q, i) => (
                  <div
                    key={q.id}
                    className="animate-fade-in-up"
                    style={{ animationDelay: `${i * 30}ms` }}
                  >
                    <QuestionCard question={q} />
                  </div>
                ))
              ) : (
                <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border py-16 text-center">
                  <MessageSquare className="h-8 w-8 text-muted-foreground/40" />
                  <p className="text-sm text-muted-foreground">No questions found</p>
                  <button
                    onClick={() => {
                      setSearchQuery("")
                      setActiveForum("all")
                      setActiveSort("top")
                    }}
                    className="text-xs text-primary hover:underline"
                  >
                    Clear all filters
                  </button>
                </div>
              )}
            </div>

            {/* Pagination */}
            {totalPages > 1 && !loading && (
              <div className="flex items-center justify-center gap-1.5 py-8">
                <button
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary disabled:opacity-40"
                >
                  Prev
                </button>
                {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                  const page = i + 1
                  return (
                    <button
                      key={page}
                      onClick={() => setCurrentPage(page)}
                      className={cn(
                        "min-w-[32px] rounded-lg border px-2 py-1.5 text-xs transition-colors",
                        currentPage === page
                          ? "border-primary bg-primary/10 text-primary font-medium"
                          : "border-border text-muted-foreground hover:bg-secondary"
                      )}
                    >
                      {page}
                    </button>
                  )
                })}
                <button
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
