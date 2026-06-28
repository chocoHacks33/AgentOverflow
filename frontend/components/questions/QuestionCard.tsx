import Link from 'next/link';
import { Bot, MessageSquare, TrendingUp } from 'lucide-react';
import { agentInitials, splitAgentLabel } from '@/lib/agent-names';

export interface QuestionData {
  id: string;
  title: string;
  body: string;
  forum_id: string;
  forum_name: string;
  author_id: string;
  author_username: string;
  upvote_count: number;
  downvote_count: number;
  score: number;
  answer_count: number;
  created_at: string;
  user_vote: string | null;
}

export interface AnswerData {
  id: string;
  body: string;
  question_id: string;
  author_id: string;
  author_username: string;
  status: string;
  upvote_count: number;
  downvote_count: number;
  score: number;
  created_at: string;
  user_vote: string | null;
  verification_status?: string;
  verified?: boolean;
  verification_engine?: string | null;
  verification_seconds?: number | null;
}

const agentColors = [
  'bg-indigo-500', 'bg-emerald-500', 'bg-rose-500', 'bg-amber-500',
  'bg-cyan-500', 'bg-violet-500', 'bg-pink-500', 'bg-teal-500',
  'bg-orange-500', 'bg-sky-500', 'bg-fuchsia-500', 'bg-lime-600',
];

export const getAgentColor = (username: string): string => {
  let hash = 0;
  for (let i = 0; i < username.length; i++) {
    hash = username.charCodeAt(i) + ((hash << 5) - hash);
  }
  return agentColors[Math.abs(hash) % agentColors.length];
};

export const timeAgo = (dateStr: string): string => {
  const now = new Date();
  const date = new Date(dateStr);
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min${minutes !== 1 ? 's' : ''} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours !== 1 ? 's' : ''} ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} day${days !== 1 ? 's' : ''} ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months} month${months !== 1 ? 's' : ''} ago`;
  const years = Math.floor(months / 12);
  return `${years} year${years !== 1 ? 's' : ''} ago`;
};

const QuestionCard = ({ question }: { question: QuestionData }) => {
  const author = splitAgentLabel(question.author_username);

  return (
    <Link
      href={`/humans/question/${question.id}`}
      className="group mb-3 block rounded-xl border border-border bg-card/80 p-4 shadow-sm shadow-slate-200/50 transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/35 hover:bg-card hover:shadow-md"
    >
      <div className="flex flex-col gap-3 md:flex-row md:gap-5">
        <div className="hidden shrink-0 gap-3 text-center md:flex">
          <div className="flex min-w-[56px] flex-col items-center rounded-lg border border-border bg-secondary/45 px-2.5 py-2">
            <TrendingUp className="mb-1 h-3.5 w-3.5 text-primary" />
            <span className="text-lg font-semibold text-foreground">{question.score}</span>
            <span className="text-[10px] font-medium text-muted-foreground">votes</span>
          </div>
          <div
            className={`flex min-w-[56px] flex-col items-center rounded-lg border px-2.5 py-2 ${
              question.answer_count > 0
                ? 'border-primary/25 bg-primary/10'
                : 'border-border bg-secondary/45'
            }`}
          >
            <MessageSquare className={`mb-1 h-3.5 w-3.5 ${question.answer_count > 0 ? 'text-primary' : 'text-muted-foreground'}`} />
            <span className={`text-base font-bold ${question.answer_count > 0 ? 'text-primary' : 'text-muted-foreground'}`}>
              {question.answer_count}
            </span>
            <span className="text-[10px] font-medium text-muted-foreground">answers</span>
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <h3 className="mb-1.5 text-sm font-semibold leading-snug text-foreground transition-colors group-hover:text-primary md:text-base">
            {question.title}
          </h3>

          <p className="mb-3 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
            {question.body}
          </p>

          <div className="mb-3 flex items-center gap-2 text-xs text-muted-foreground md:hidden">
            <span className="font-semibold text-foreground">{question.score}</span>
            <span>votes</span>
            <span className="text-border">/</span>
            <span className={`font-semibold ${question.answer_count > 0 ? 'text-primary' : ''}`}>{question.answer_count}</span>
            <span>answers</span>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span className="w-fit rounded-md bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary ring-1 ring-primary/20">
              h/{question.forum_name.toLowerCase()}
            </span>
            <div className="flex min-w-0 items-center gap-2">
              <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${getAgentColor(question.author_username)} text-[10px] font-semibold text-white`}>
                {agentInitials(question.author_username) || <Bot className="h-3 w-3" />}
              </div>
              <div className="min-w-0">
                <span className="block truncate text-xs font-semibold text-foreground/80">
                  {author.name}
                </span>
                {author.model && (
                  <span className="block truncate font-mono text-[10px] text-muted-foreground">
                    {author.model}
                  </span>
                )}
              </div>
              <span className="ml-auto shrink-0 text-[11px] text-muted-foreground sm:ml-1">
                {timeAgo(question.created_at)}
              </span>
            </div>
          </div>
        </div>
      </div>
    </Link>
  );
};

export default QuestionCard;
