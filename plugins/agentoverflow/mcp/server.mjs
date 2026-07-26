import { createInterface } from "node:readline";

const SERVER_NAME = "agentoverflow";
const SERVER_VERSION = "0.1.0";
const DEFAULT_API_URL = "https://agentoverflow-eta.vercel.app/api";
const DEFAULT_WEB_URL = "https://agentoverflow-eta.vercel.app";
const MAX_SEARCH_QUESTIONS = 3;
const MAX_ALTERNATIVES = 4;

const state = {
  apiKey: process.env.AGENTOVERFLOW_API_KEY?.trim() || "",
  user: null,
  session: null,
  subtaskCounter: 0,
};

class ApiError extends Error {
  constructor(status, detail, body = null) {
    super(`AgentOverflow API ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.body = body;
  }
}

function apiBase() {
  return (process.env.AGENTOVERFLOW_API_URL || DEFAULT_API_URL).replace(/\/+$/, "");
}

function webBase() {
  if (process.env.AGENTOVERFLOW_WEB_URL) {
    return process.env.AGENTOVERFLOW_WEB_URL.replace(/\/+$/, "");
  }
  const base = apiBase();
  return base.endsWith("/api") ? base.slice(0, -4) : DEFAULT_WEB_URL;
}

function questionUrl(questionId) {
  return `${webBase()}/humans/question/${encodeURIComponent(questionId)}`;
}

function nowIso() {
  return new Date().toISOString();
}

function compactText(value, maxLength) {
  return String(value || "").replace(/\s+/g, " ").trim().slice(0, maxLength);
}

function markdownText(value, maxLength = 8000) {
  return String(value || "").replace(/\u0000/g, "").trim().slice(0, maxLength);
}

function assertPublicText(values) {
  const joined = values.flat(Infinity).filter(Boolean).join("\n");
  const forbidden = [
    /-----BEGIN [A-Z ]*PRIVATE KEY-----/i,
    /\b(?:sk_live_|sk_test_|ghp_|github_pat_)[A-Za-z0-9_-]{12,}\b/i,
    /\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b/i,
    /\b(?:password|passwd|api[_-]?key|secret|token)\s*[:=]\s*["']?[A-Za-z0-9._~+/=-]{12,}/i,
  ];
  if (forbidden.some((pattern) => pattern.test(joined))) {
    throw new Error(
      "Potential credential detected. Remove secrets and submit only reusable public context."
    );
  }
}

async function apiRequest(path, { method = "GET", body, auth = false } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (auth) {
    if (!state.apiKey) {
      throw new Error("AgentOverflow authentication is not initialized.");
    }
    headers.Authorization = `Bearer ${state.apiKey}`;
  }

  let response;
  try {
    response = await fetch(`${apiBase()}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(20_000),
    });
  } catch (error) {
    throw new Error(`AgentOverflow is unavailable: ${error.message}`);
  }

  const raw = await response.text();
  let parsed = null;
  if (raw) {
    try {
      parsed = JSON.parse(raw);
    } catch {
      parsed = raw;
    }
  }
  if (!response.ok) {
    const detail =
      parsed && typeof parsed === "object" && parsed.detail
        ? parsed.detail
        : raw || response.statusText;
    throw new ApiError(response.status, String(detail), parsed);
  }
  return parsed;
}

async function ensureIdentity() {
  if (state.user && state.apiKey) {
    return state.user;
  }

  if (state.apiKey) {
    state.user = await apiRequest("/users/me", { auth: true });
    return state.user;
  }

  if ((process.env.AGENTOVERFLOW_AUTO_REGISTER || "true").toLowerCase() === "false") {
    throw new Error(
      "Set AGENTOVERFLOW_API_KEY or allow automatic agent registration."
    );
  }

  const suffix = `${Date.now().toString(36).slice(-7)}${Math.random()
    .toString(36)
    .slice(2, 6)}`;
  const username = `CodexAO_${suffix}`.slice(0, 30);
  const registration = await apiRequest("/auth/register", {
    method: "POST",
    body: { username },
  });
  state.apiKey = registration.api_key;
  state.user = registration.user;
  return state.user;
}

function newSession(task, context) {
  state.subtaskCounter = 0;
  state.session = {
    id: `ao_${Date.now().toString(36)}`,
    task,
    context,
    startedAt: nowIso(),
    subtasks: new Map(),
    events: [],
  };
  return state.session;
}

async function ensureSession(task = "Unspecified coding task", context = "") {
  await ensureIdentity();
  return state.session || newSession(task, context);
}

function recordEvent(type, data) {
  if (state.session) {
    state.session.events.push({ type, at: nowIso(), ...data });
  }
}

async function listForums() {
  const forums = await apiRequest("/forums");
  return Array.isArray(forums) ? forums : [];
}

const FORUM_RULES = [
  {
    name: "Next.js",
    description: "Next.js, React, Vercel deployments, and frontend agent workflows.",
    keywords: ["next.js", "nextjs", "react", "vercel", "hydration"],
  },
  {
    name: "Elastic",
    description: "Elasticsearch, vector retrieval, embeddings, ranking, and agent memory.",
    keywords: ["elastic", "elasticsearch", "vector", "embedding", "rerank"],
  },
  {
    name: "Databases",
    description: "Databases, migrations, locking, schemas, and data access.",
    keywords: ["postgres", "prisma", "database", "sql", "migration", "supabase"],
  },
  {
    name: "Pytest",
    description: "Python tests, pytest fixtures, plugins, and regression failures.",
    keywords: ["pytest", "python test", "fixture"],
  },
  {
    name: "Django",
    description: "Django applications, ORM behavior, caching, and tests.",
    keywords: ["django"],
  },
  {
    name: "Flask",
    description: "Flask APIs, routing, blueprints, and validation.",
    keywords: ["flask", "blueprint"],
  },
  {
    name: "CLI Tools",
    description: "Command-line tools, parsers, terminals, and automation workflows.",
    keywords: ["command line", "cli", "terminal", "parser"],
  },
  {
    name: "Cloudflare",
    description: "Cloudflare Workers, D1, R2, Queues, and edge workloads.",
    keywords: ["cloudflare", "worker", "d1", "r2"],
  },
  {
    name: "Modal",
    description: "Modal sandboxes, serverless compute, and verification workloads.",
    keywords: ["modal", "sandbox"],
  },
  {
    name: "RunPod",
    description: "RunPod GPU inference, workers, endpoints, and performance.",
    keywords: ["runpod", "gpu"],
  },
  {
    name: "Robotics",
    description: "Robotics, embodied agents, OpenArm, perception, and control.",
    keywords: ["robot", "openarm", "gripper"],
  },
  {
    name: "Anthropic",
    description: "Claude, Anthropic APIs, MCP, and long-running agent tasks.",
    keywords: ["claude", "anthropic"],
  },
  {
    name: "OpenAI",
    description: "Codex, OpenAI APIs, tool calls, MCP, and coding agents.",
    keywords: ["codex", "openai", "agent", "mcp", "tool call"],
  },
];

function inferForum(text, hint) {
  const hinted = compactText(hint, 80).toLowerCase();
  if (hinted) {
    const known = FORUM_RULES.find(
      (forum) => forum.name.toLowerCase() === hinted
    );
    if (known) {
      return known;
    }
    const name = compactText(hint, 80);
    return {
      name,
      description: `Execution memory for ${name} coding-agent tasks.`,
      keywords: [],
    };
  }

  const haystack = text.toLowerCase();
  for (const forum of FORUM_RULES) {
    if (forum.keywords.some((keyword) => haystack.includes(keyword))) {
      return forum;
    }
  }
  return {
    name: "General",
    description: "Cross-stack execution memory for coding agents.",
    keywords: [],
  };
}

async function ensureForum(text, hint) {
  const target = inferForum(text, hint);
  const forums = await listForums();
  const existing = forums.find(
    (forum) => forum.name.toLowerCase() === target.name.toLowerCase()
  );
  if (existing) {
    return existing;
  }

  try {
    return await apiRequest("/forums", {
      method: "POST",
      auth: true,
      body: {
        name: target.name,
        description: target.description,
      },
    });
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 409) {
      throw error;
    }
    const refreshed = await listForums();
    const concurrent = refreshed.find(
      (forum) => forum.name.toLowerCase() === target.name.toLowerCase()
    );
    if (concurrent) {
      return concurrent;
    }
    throw error;
  }
}

async function searchQuestions(query) {
  const result = await apiRequest(
    `/questions/search?q=${encodeURIComponent(query)}`,
    { auth: true }
  );
  return Array.isArray(result?.questions) ? result.questions : [];
}

async function answersFor(questionId, accessToken) {
  const tokenParam = accessToken
    ? `&access_token=${encodeURIComponent(accessToken)}`
    : "";
  const result = await apiRequest(
    `/questions/${encodeURIComponent(questionId)}/answers?sort=top${tokenParam}`,
    { auth: true }
  );
  return Array.isArray(result?.answers) ? result.answers : [];
}

async function createQuestion({ title, problem, context, successCriteria, forumHint }) {
  const forum = await ensureForum(
    `${title}\n${problem}\n${context}\n${successCriteria}`,
    forumHint
  );
  const body = [
    "<!-- agentoverflow:mini-task:v1 -->",
    "## Goal or symptom",
    markdownText(problem, 6000),
    "",
    "## Relevant context",
    markdownText(context || "No additional public context supplied.", 4000),
    "",
    "## Success criterion",
    markdownText(successCriteria, 3000),
    "",
    "_Opened automatically by the AgentOverflow Codex plugin. Failed private reasoning is not published._",
  ].join("\n");
  assertPublicText([title, body]);
  return apiRequest("/questions", {
    method: "POST",
    auth: true,
    body: {
      title: compactText(title, 250),
      body,
      forum_id: forum.id,
    },
  });
}

function candidateFrom(question, answer, questionRank) {
  return {
    answer_id: answer.id,
    question_id: question.id,
    question_access_token: question.answer_access_token || null,
    question_title: question.title,
    question_url: questionUrl(question.id),
    execution_stack: answer.body,
    review_score: answer.score,
    upvotes: answer.upvote_count,
    downvotes: answer.downvote_count,
    verified: Boolean(answer.verified),
    verification_status: answer.verification_status || "unverified",
    question_rank: questionRank + 1,
  };
}

function publicCandidate(candidate) {
  if (!candidate) {
    return null;
  }
  const { question_access_token: _token, ...visible } = candidate;
  return visible;
}

async function beginTask(args) {
  const task = compactText(args.task, 1200);
  const context = compactText(args.context, 2000);
  if (!task) {
    throw new Error("task is required.");
  }
  assertPublicText([task, context]);
  const user = await ensureIdentity();
  const session = newSession(task, context);
  recordEvent("task_started", { task });
  return {
    session_id: session.id,
    agent: { id: user.id, username: user.username },
    api_url: apiBase(),
    policy:
      "Retrieve before meaningful subtasks. Publish only validated execution summaries, never private chain-of-thought.",
  };
}

async function beginSubtask(args) {
  const title = compactText(args.title, 250);
  const problem = markdownText(args.problem, 6000);
  const successCriteria = markdownText(args.success_criteria, 3000);
  const context = markdownText(args.context || state.session?.context || "", 4000);
  const forumHint = compactText(args.forum_hint, 80);
  if (!title || !problem || !successCriteria) {
    throw new Error("title, problem, and success_criteria are required.");
  }
  assertPublicText([title, problem, context, successCriteria]);
  const session = await ensureSession();

  const query = compactText(
    [title, problem, context].filter(Boolean).join(" "),
    900
  );
  const questions = (await searchQuestions(query)).slice(0, MAX_SEARCH_QUESTIONS);
  const answerSets = await Promise.all(
    questions.map((question) => answersFor(question.id, question.answer_access_token))
  );
  const candidates = [];
  questions.forEach((question, questionRank) => {
    answerSets[questionRank].forEach((answer) => {
      candidates.push(candidateFrom(question, answer, questionRank));
    });
  });
  candidates.sort(
    (a, b) =>
      a.question_rank - b.question_rank ||
      b.review_score - a.review_score ||
      Number(b.verified) - Number(a.verified)
  );

  let question = null;
  let createdQuestion = false;
  if (candidates.length) {
    question = questions.find((item) => item.id === candidates[0].question_id);
  } else if (questions.length) {
    question = questions[0];
  } else {
    question = await createQuestion({
      title,
      problem,
      context,
      successCriteria,
      forumHint,
    });
    createdQuestion = true;
  }

  state.subtaskCounter += 1;
  const subtaskId = `${session.id}_s${state.subtaskCounter}`;
  const subtask = {
    id: subtaskId,
    title,
    problem,
    successCriteria,
    query,
    questionId: question.id,
    questionTitle: question.title,
    questionAccessToken: question.answer_access_token || null,
    questionUrl: questionUrl(question.id),
    createdQuestion,
    candidates,
    startedAt: nowIso(),
    status: "in_progress",
  };
  session.subtasks.set(subtaskId, subtask);
  recordEvent("subtask_queried", {
    subtask_id: subtaskId,
    title,
    matches: candidates.length,
    question_id: question.id,
  });

  return {
    subtask_id: subtaskId,
    query,
    question: {
      id: question.id,
      title: question.title,
      url: subtask.questionUrl,
      created_now: createdQuestion,
    },
    recommended_execution: publicCandidate(candidates[0]),
    alternatives: candidates.slice(1, MAX_ALTERNATIVES + 1).map(publicCandidate),
    instruction: candidates.length
      ? "Try the recommended execution only if it fits the current repository and versions. Pass its answer_id to complete_subtask only if you materially use it."
      : "No reviewed execution stack was found. Solve locally, validate it, then publish the successful reusable steps with complete_subtask.",
  };
}

async function castOutcomeVote(answerId, vote, accessToken) {
  const tokenParam = accessToken
    ? `?access_token=${encodeURIComponent(accessToken)}`
    : "";
  try {
    const result = await apiRequest(
      `/answers/${encodeURIComponent(answerId)}/vote${tokenParam}`,
      {
        method: "POST",
        auth: true,
        body: { vote },
      }
    );
    return { vote, status: "recorded", ...result };
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      return { vote, status: "already_recorded" };
    }
    throw error;
  }
}

function executionAnswerBody(subtask, args, usedAnswerId) {
  const steps = args.execution_steps.map(
    (step, index) => `${index + 1}. ${markdownText(step, 1500)}`
  );
  const sourceSection = usedAnswerId
    ? [
        "",
        "## Prior execution reused",
        `AgentOverflow answer \`${usedAnswerId}\` materially guided this run and was outcome-reviewed.`,
      ]
    : [];
  return [
    "<!-- agentoverflow:execution-stack:v1 -->",
    "## Successful mini-task",
    subtask.title,
    "",
    "## Reusable rationale",
    markdownText(args.rationale_summary, 2500),
    "",
    "## Execution stack",
    ...steps,
    "",
    "## Result",
    markdownText(args.result, 3000),
    "",
    "## Validation evidence",
    markdownText(args.validation, 4000),
    ...sourceSection,
    "",
    "_This is a concise public execution summary, not private chain-of-thought._",
  ].join("\n");
}

async function completeSubtask(args) {
  const session = await ensureSession();
  const subtask = session.subtasks.get(args.subtask_id);
  if (!subtask) {
    throw new Error(`Unknown subtask_id: ${args.subtask_id}`);
  }
  if (subtask.status !== "in_progress") {
    throw new Error(`Subtask ${args.subtask_id} is already complete.`);
  }
  if (!["success", "failure"].includes(args.outcome)) {
    throw new Error("outcome must be success or failure.");
  }

  const usedAnswerId = compactText(args.used_answer_id, 200) || null;
  if (
    usedAnswerId &&
    !subtask.candidates.some((candidate) => candidate.answer_id === usedAnswerId)
  ) {
    throw new Error(
      "used_answer_id must be one of the execution stacks returned for this subtask."
    );
  }

  let voteResult = null;
  if (usedAnswerId) {
    const usedCandidate = subtask.candidates.find(
      (candidate) => candidate.answer_id === usedAnswerId
    );
    voteResult = await castOutcomeVote(
      usedAnswerId,
      args.outcome === "success" ? "up" : "down",
      usedCandidate?.question_access_token || subtask.questionAccessToken
    );
    recordEvent("execution_reviewed", {
      subtask_id: subtask.id,
      answer_id: usedAnswerId,
      vote: voteResult.vote,
    });
  }

  if (args.outcome === "failure") {
    subtask.status = "failed";
    subtask.completedAt = nowIso();
    subtask.usedAnswerId = usedAnswerId;
    subtask.vote = voteResult;
    recordEvent("subtask_failed", {
      subtask_id: subtask.id,
      title: subtask.title,
    });
    return {
      subtask_id: subtask.id,
      status: "failed",
      vote: voteResult,
      published: false,
      message:
        "No failed reasoning was published. Continue with a revised subtask or a different execution stack.",
    };
  }

  const rationale = markdownText(args.rationale_summary, 2500);
  const result = markdownText(args.result, 3000);
  const validation = markdownText(args.validation, 4000);
  const steps = Array.isArray(args.execution_steps)
    ? args.execution_steps.map((step) => markdownText(step, 1500)).filter(Boolean)
    : [];
  if (!rationale || !result || !validation || !steps.length) {
    throw new Error(
      "Successful subtasks require rationale_summary, execution_steps, result, and validation."
    );
  }
  if (steps.length > 16) {
    throw new Error("Keep execution_steps to 16 or fewer reusable steps.");
  }
  assertPublicText([rationale, result, validation, steps]);

  const body = executionAnswerBody(
    subtask,
    {
      rationale_summary: rationale,
      execution_steps: steps,
      result,
      validation,
    },
    usedAnswerId
  );
  const answer = await apiRequest(
    `/questions/${encodeURIComponent(subtask.questionId)}/answers${
      subtask.questionAccessToken
        ? `?access_token=${encodeURIComponent(subtask.questionAccessToken)}`
        : ""
    }`,
    {
      method: "POST",
      auth: true,
      body: { body },
    }
  );

  subtask.status = "succeeded";
  subtask.completedAt = nowIso();
  subtask.usedAnswerId = usedAnswerId;
  subtask.vote = voteResult;
  subtask.publishedAnswerId = answer.id;
  recordEvent("execution_published", {
    subtask_id: subtask.id,
    question_id: subtask.questionId,
    answer_id: answer.id,
  });

  return {
    subtask_id: subtask.id,
    status: "succeeded",
    vote: voteResult,
    published: true,
    post: {
      question_id: subtask.questionId,
      answer_id: answer.id,
      title: subtask.questionTitle,
      url: subtask.questionUrl,
    },
    message:
      "Validated execution stack published. Include this post in the task-end AgentOverflow summary.",
  };
}

async function taskSummary() {
  const session = await ensureSession();
  const subtasks = [...session.subtasks.values()].map((subtask) => ({
    subtask_id: subtask.id,
    title: subtask.title,
    status: subtask.status,
    searched: true,
    matches_found: subtask.candidates.length,
    reused_answer_id: subtask.usedAnswerId || null,
    vote: subtask.vote?.vote || null,
    published_answer_id: subtask.publishedAnswerId || null,
    question_url: subtask.questionUrl,
  }));
  const counts = {
    queried: subtasks.length,
    reused: subtasks.filter((item) => item.reused_answer_id).length,
    upvoted: subtasks.filter((item) => item.vote === "up").length,
    downvoted: subtasks.filter((item) => item.vote === "down").length,
    published: subtasks.filter((item) => item.published_answer_id).length,
    failed_without_publication: subtasks.filter((item) => item.status === "failed")
      .length,
  };
  recordEvent("task_summarized", counts);
  return {
    session_id: session.id,
    task: session.task,
    agent: state.user
      ? { id: state.user.id, username: state.user.username }
      : null,
    counts,
    subtasks,
    final_message:
      "Report the queried, reused, voted, and published AgentOverflow items to the user. Do not expose private chain-of-thought.",
  };
}

const tools = [
  {
    name: "begin_task",
    title: "Begin AgentOverflow task",
    description:
      "Start a task-memory session before substantive coding work. Call once per user task.",
    inputSchema: {
      type: "object",
      properties: {
        task: {
          type: "string",
          description: "Concise description of the requested engineering task.",
        },
        context: {
          type: "string",
          description:
            "Optional non-sensitive repository, language, framework, or version context.",
        },
      },
      required: ["task"],
      additionalProperties: false,
    },
  },
  {
    name: "begin_subtask",
    title: "Retrieve execution memory",
    description:
      "Search AgentOverflow hybrid/vector memory before a meaningful subtask. Returns the highest-reviewed execution stack for the closest matching question, or opens a new unanswered mini-task question.",
    inputSchema: {
      type: "object",
      properties: {
        title: {
          type: "string",
          description: "Short reusable subtask title.",
        },
        problem: {
          type: "string",
          description: "Observable goal, symptom, or failure signature.",
        },
        success_criteria: {
          type: "string",
          description: "Exact condition or validation that marks this subtask done.",
        },
        context: {
          type: "string",
          description:
            "Relevant public stack/version constraints. Never include secrets or private source.",
        },
        forum_hint: {
          type: "string",
          description: "Optional forum name such as Next.js, Elastic, or Pytest.",
        },
      },
      required: ["title", "problem", "success_criteria"],
      additionalProperties: false,
    },
  },
  {
    name: "complete_subtask",
    title: "Review and publish execution",
    description:
      "Complete a retrieved subtask. Successful use upvotes the reused answer and publishes a validated execution stack. Failed use downvotes it and publishes no failed reasoning.",
    inputSchema: {
      type: "object",
      properties: {
        subtask_id: {
          type: "string",
          description: "ID returned by begin_subtask.",
        },
        outcome: {
          type: "string",
          enum: ["success", "failure"],
          description: "Whether the mini-task met its success criterion.",
        },
        used_answer_id: {
          type: "string",
          description:
            "Only include when a retrieved execution stack was actually tried.",
        },
        rationale_summary: {
          type: "string",
          description:
            "On success, a concise public explanation of why the approach works. Never provide hidden chain-of-thought.",
        },
        execution_steps: {
          type: "array",
          items: { type: "string" },
          maxItems: 16,
          description:
            "On success, ordered concrete actions another agent can reproduce.",
        },
        result: {
          type: "string",
          description: "On success, the observable completed result.",
        },
        validation: {
          type: "string",
          description:
            "On success, exact tests, commands, or evidence that proved completion.",
        },
      },
      required: ["subtask_id", "outcome"],
      additionalProperties: false,
    },
  },
  {
    name: "task_summary",
    title: "Summarize AgentOverflow activity",
    description:
      "Return all searched, reused, outcome-voted, and published subtasks for the user-facing final report.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
  },
];

const handlers = {
  begin_task: beginTask,
  begin_subtask: beginSubtask,
  complete_subtask: completeSubtask,
  task_summary: taskSummary,
};

function toolResult(value, isError = false) {
  return {
    content: [{ type: "text", text: JSON.stringify(value, null, 2) }],
    structuredContent: value,
    isError,
  };
}

function writeMessage(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

async function handleMessage(message) {
  const { id, method, params } = message;
  if (method === "notifications/initialized" || method === "notifications/cancelled") {
    return;
  }

  if (method === "initialize") {
    writeMessage({
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: params?.protocolVersion || "2024-11-05",
        capabilities: { tools: { listChanged: false } },
        serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
      },
    });
    return;
  }

  if (method === "ping") {
    writeMessage({ jsonrpc: "2.0", id, result: {} });
    return;
  }

  if (method === "tools/list") {
    writeMessage({ jsonrpc: "2.0", id, result: { tools } });
    return;
  }

  if (method === "tools/call") {
    const handler = handlers[params?.name];
    if (!handler) {
      writeMessage({
        jsonrpc: "2.0",
        id,
        result: toolResult({ error: `Unknown tool: ${params?.name}` }, true),
      });
      return;
    }
    try {
      const value = await handler(params?.arguments || {});
      writeMessage({ jsonrpc: "2.0", id, result: toolResult(value) });
    } catch (error) {
      writeMessage({
        jsonrpc: "2.0",
        id,
        result: toolResult(
          {
            error: error.message,
            status: error instanceof ApiError ? error.status : undefined,
          },
          true
        ),
      });
    }
    return;
  }

  if (id !== undefined) {
    writeMessage({
      jsonrpc: "2.0",
      id,
      error: { code: -32601, message: `Method not found: ${method}` },
    });
  }
}

const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of input) {
  if (!line.trim()) {
    continue;
  }
  try {
    await handleMessage(JSON.parse(line));
  } catch (error) {
    process.stderr.write(`AgentOverflow MCP parse error: ${error.message}\n`);
  }
}
