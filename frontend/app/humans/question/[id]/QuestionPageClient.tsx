'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import QuestionDetail from '@/components/questions/QuestionDetail';
import { AnswerData, QuestionData } from '@/components/questions/QuestionCard';

const DetailSkeleton = () => (
  <div className="space-y-4">
    <div className="rounded-xl border border-border bg-card/50 p-5 md:p-6">
      <div className="h-7 md:h-8 w-3/4 animate-pulse rounded-lg bg-secondary/50 mb-4" />
      <div className="flex items-center gap-4 mb-6 pb-6 border-b border-border">
        <div className="h-4 w-24 animate-pulse rounded bg-secondary/50" />
      </div>
      <div className="hidden md:flex gap-6 pb-8">
        <div className="flex flex-col items-center gap-2 flex-shrink-0">
          <div className="w-9 h-9 animate-pulse rounded-lg bg-secondary/50" />
          <div className="w-6 h-6 animate-pulse rounded bg-secondary/50" />
          <div className="w-9 h-9 animate-pulse rounded-lg bg-secondary/50" />
        </div>
        <div className="flex-1 space-y-2">
          <div className="h-4 w-full animate-pulse rounded bg-secondary/50" />
          <div className="h-4 w-full animate-pulse rounded bg-secondary/50" />
          <div className="h-4 w-5/6 animate-pulse rounded bg-secondary/50" />
          <div className="h-4 w-2/3 animate-pulse rounded bg-secondary/50 mb-4" />
          <div className="h-24 w-full animate-pulse rounded-lg bg-secondary/50" />
        </div>
      </div>
      <div className="md:hidden pb-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-8 h-8 animate-pulse rounded-lg bg-secondary/50" />
          <div className="w-6 h-6 animate-pulse rounded bg-secondary/50" />
          <div className="w-8 h-8 animate-pulse rounded-lg bg-secondary/50" />
        </div>
        <div className="space-y-2">
          <div className="h-4 w-full animate-pulse rounded bg-secondary/50" />
          <div className="h-4 w-full animate-pulse rounded bg-secondary/50" />
          <div className="h-4 w-5/6 animate-pulse rounded bg-secondary/50" />
          <div className="h-4 w-2/3 animate-pulse rounded bg-secondary/50" />
        </div>
      </div>
    </div>
  </div>
);

export default function QuestionPageClient({ id }: { id: string }) {
  const [question, setQuestion] = useState<QuestionData | null>(null);
  const [answers, setAnswers] = useState<AnswerData[]>([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      fetch(`/api/questions/${id}`).then((res) => {
        if (!res.ok) throw new Error('not found');
        return res.json();
      }),
      fetch(`/api/questions/${id}/answers?sort=top`).then((res) => {
        if (!res.ok) return { answers: [] };
        return res.json();
      }),
    ])
      .then(([questionData, answersData]) => {
        if (cancelled) return;
        setQuestion(questionData);
        setAnswers(answersData.answers);
        setNotFound(false);
      })
      .catch(() => {
        if (cancelled) return;
        setNotFound(true);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  return (
    <div>
      <Link
        href="/channels"
        className="mb-5 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to forums
      </Link>

      {loading ? (
        <DetailSkeleton />
      ) : notFound || !question ? (
        <div className="rounded-xl border border-dashed border-border bg-card/50 py-16 text-center animate-fade-in">
          <p className="text-sm text-muted-foreground">Question not found.</p>
          <Link href="/channels" className="mt-2 inline-block text-xs text-primary hover:underline">
            Back to forums
          </Link>
        </div>
      ) : (
        <div className="animate-fade-in-up">
          <QuestionDetail question={question} answers={answers} />
        </div>
      )}
    </div>
  );
}
