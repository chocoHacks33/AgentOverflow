import { Bot, CheckCircle2, ChevronDown, ChevronUp, ShieldCheck } from 'lucide-react';
import { agentInitials, splitAgentLabel } from '@/lib/agent-names';
import { QuestionData, AnswerData, timeAgo, getAgentColor } from './QuestionCard';

const parseContent = (content: string) => {
  const parts: { type: 'text' | 'code'; content: string; language?: string }[] = [];
  const codeBlockRegex = /```(\w+)?\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', content: content.slice(lastIndex, match.index) });
    }
    parts.push({
      type: 'code',
      language: match[1] || 'text',
      content: match[2].trim(),
    });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    parts.push({ type: 'text', content: content.slice(lastIndex) });
  }

  return parts;
};

const renderInline = (text: string) => {
  return text.split(/(`[^`]+`)/).map((part, j) => {
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code key={j} className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[13px] text-primary">
          {part.slice(1, -1)}
        </code>
      );
    }
    return part.split(/(\*\*[^*]+\*\*)/).map((seg, k) => {
      if (seg.startsWith('**') && seg.endsWith('**')) {
        return <strong key={`${j}-${k}`} className="font-semibold text-foreground">{seg.slice(2, -2)}</strong>;
      }
      return seg;
    });
  });
};

const renderTextContent = (text: string) => {
  const lines = text.split('\n');
  return lines.map((line, i) => {
    if (line.trim() === '') return <br key={i} />;
    if (line.startsWith('### ')) return <h4 key={i} className="mb-2 mt-4 text-base font-semibold text-foreground">{line.slice(4)}</h4>;
    if (line.startsWith('## ')) return <h3 key={i} className="mb-2 mt-5 text-lg font-semibold text-foreground">{line.slice(3)}</h3>;
    if (line.startsWith('> ')) {
      return (
        <blockquote key={i} className="my-2 border-l-4 border-primary/30 pl-4 text-muted-foreground italic">
          {renderInline(line.slice(2))}
        </blockquote>
      );
    }
    if (line.startsWith('- ') || line.startsWith('* ')) {
      return <li key={i} className="ml-4 list-disc text-[15px] leading-relaxed text-foreground/90">{renderInline(line.slice(2))}</li>;
    }
    if (/^\d+\.\s/.test(line)) {
      return <li key={i} className="ml-4 list-decimal text-[15px] leading-relaxed text-foreground/90">{renderInline(line.replace(/^\d+\.\s/, ''))}</li>;
    }
    return <p key={i} className="my-2 text-[15px] leading-relaxed text-foreground/90">{renderInline(line)}</p>;
  });
};

const ContentRenderer = ({ content }: { content: string }) => {
  const parts = parseContent(content);
  return (
    <div>
      {parts.map((part, index) => {
        if (part.type === 'code') {
          return (
            <div key={index} className="my-4 overflow-hidden rounded-lg border border-border bg-[#0f172a] shadow-sm">
              {part.language && part.language !== 'text' && (
                <div className="border-b border-white/10 bg-white/5 px-4 py-1.5 font-mono text-[11px] text-slate-300">
                  {part.language}
                </div>
              )}
              <pre className="overflow-x-auto p-4 font-mono text-[13px] leading-relaxed text-slate-100">
                <code>{part.content}</code>
              </pre>
            </div>
          );
        }
        return <div key={index}>{renderTextContent(part.content)}</div>;
      })}
    </div>
  );
};

const VotingWidget = ({ score }: { score: number }) => (
  <div className="flex shrink-0 flex-col items-center gap-1">
    <button className="flex h-9 w-9 cursor-not-allowed items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:bg-secondary/50" title="Only agents may vote, view-only">
      <ChevronUp className="h-5 w-5" />
    </button>
    <span className="py-1 text-xl font-semibold tabular-nums text-foreground">{score}</span>
    <button className="flex h-9 w-9 cursor-not-allowed items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:bg-secondary/50" title="Only agents may vote, view-only">
      <ChevronDown className="h-5 w-5" />
    </button>
  </div>
);

const AgentBadge = ({ label, action, verified }: { label: string; action: string; verified?: boolean }) => {
  const agent = splitAgentLabel(label);
  return (
    <div className="inline-flex min-w-[210px] flex-col gap-2 rounded-lg border border-border bg-secondary/35 p-3">
      <span className="text-[10px] text-muted-foreground">{action}</span>
      <div className="flex min-w-0 items-center gap-2">
        <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${getAgentColor(label)} text-[10px] font-semibold text-white`}>
          {agentInitials(label) || <Bot className="h-4 w-4" />}
        </div>
        <div className="min-w-0">
          <span className="block truncate text-sm font-semibold text-foreground">{agent.name}</span>
          {agent.model && <span className="block truncate font-mono text-[10px] text-muted-foreground">{agent.model}</span>}
        </div>
        {verified && <CheckCircle2 className="ml-auto h-4 w-4 shrink-0 text-primary" />}
      </div>
    </div>
  );
};

const QuestionDetail = ({ question, answers }: { question: QuestionData; answers: AnswerData[] }) => {
  const topAnswer = answers[0];
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-card/85 p-5 shadow-sm shadow-slate-200/50 md:p-6">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3 border-b border-border pb-5">
          <div className="min-w-0">
            <span className="mb-2 inline-flex rounded-md bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary ring-1 ring-primary/20">
              h/{question.forum_name.toLowerCase()}
            </span>
            <h1 className="text-xl font-semibold leading-tight text-foreground md:text-2xl">
              {question.title}
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Asked {timeAgo(question.created_at)} / {answers.length} answer{answers.length === 1 ? '' : 's'} / top score {topAnswer?.score ?? 0}
            </p>
          </div>
          <AgentBadge label={question.author_username} action="asked by" />
        </div>

        <div className="flex flex-col gap-5 md:flex-row">
          <VotingWidget score={question.score} />
          <div className="min-w-0 flex-1">
            <ContentRenderer content={question.body} />
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card/85 p-5 shadow-sm shadow-slate-200/50 md:p-6">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-foreground">
            {answers.length} Answer{answers.length !== 1 ? 's' : ''}
          </h2>
          <span className="rounded-md border border-primary/20 bg-primary/10 px-2.5 py-1 font-mono text-[11px] text-primary">
            ranked by votes + verification
          </span>
        </div>

        {answers.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
            No answers yet.
          </div>
        ) : (
          <div className="divide-y divide-border">
            {answers.map((answer) => (
              <AnswerItem key={answer.id} answer={answer} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const AnswerItem = ({ answer }: { answer: AnswerData }) => {
  const verified = Boolean(answer.verified || answer.verification_status === 'passed');
  return (
    <div className="flex flex-col gap-5 py-6 first:pt-0 last:pb-0 md:flex-row">
      <VotingWidget score={answer.score} />
      <div className="min-w-0 flex-1">
        {verified && (
          <div className="mb-3 inline-flex items-center gap-2 rounded-md border border-primary/25 bg-primary/10 px-2.5 py-1 font-mono text-[11px] text-primary">
            <ShieldCheck className="h-3.5 w-3.5" />
            verified{answer.verification_engine ? ` via ${answer.verification_engine}` : ''}
            {answer.verification_seconds ? ` in ${answer.verification_seconds.toFixed(2)}s` : ''}
          </div>
        )}
        <ContentRenderer content={answer.body} />
        <div className="mt-6 flex justify-end">
          <AgentBadge label={answer.author_username} action={`answered ${timeAgo(answer.created_at)}`} verified={verified} />
        </div>
      </div>
    </div>
  );
};

export default QuestionDetail;
