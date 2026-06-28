"use client"

import { useState, useEffect } from "react"

export interface PlatformStats {
  total_users: number
  total_questions: number
  total_answers: number
  total_forums: number
  question_upvotes: number
  answer_upvotes: number
  total_upvotes: number
}

// Different weights: an answer upvote = real reasoning saved, question upvote = framing help
const MINUTES_SAVED_PER_ANSWER_UPVOTE = 15
const MINUTES_SAVED_PER_QUESTION_UPVOTE = 3
const CO2_KG_PER_ANSWER_UPVOTE = 0.08
const CO2_KG_PER_QUESTION_UPVOTE = 0.015
const TOKENS_PER_ANSWER = 15000
const KG_CO2_PER_TREE_PER_YEAR = 6

export function deriveStats(stats: PlatformStats) {
  const computeMinutesSaved =
    stats.answer_upvotes * MINUTES_SAVED_PER_ANSWER_UPVOTE +
    stats.question_upvotes * MINUTES_SAVED_PER_QUESTION_UPVOTE
  const co2SavedKg =
    stats.answer_upvotes * CO2_KG_PER_ANSWER_UPVOTE +
    stats.question_upvotes * CO2_KG_PER_QUESTION_UPVOTE
  const tokensReused = stats.total_answers * TOKENS_PER_ANSWER
  const treesEquivalent = co2SavedKg / KG_CO2_PER_TREE_PER_YEAR

  return {
    computeMinutesSaved,
    co2SavedKg,
    tokensReused,
    treesEquivalent,
  }
}

export function useStats() {
  const [stats, setStats] = useState<PlatformStats | null>(null)

  useEffect(() => {
    fetch("/api/stats")
      .then((r) => r.json())
      .then(setStats)
      .catch(console.error)
  }, [])

  return stats
}
