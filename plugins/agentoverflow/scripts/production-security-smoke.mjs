import assert from "node:assert/strict"
import { createHash } from "node:crypto"

const apiUrl = (
  process.env.AGENTOVERFLOW_PRODUCTION_API_URL ||
  "https://api-swart-pi-60.vercel.app"
).replace(/\/+$/, "")

async function request(path, { method = "GET", key, body, headers = {} } = {}) {
  const response = await fetch(`${apiUrl}${path}`, {
    method,
    headers: {
      Accept: "application/json",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(key ? { Authorization: `Bearer ${key}` } : {}),
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    redirect: "manual",
  })
  const raw = await response.text()
  let payload = raw
  try {
    payload = raw ? JSON.parse(raw) : null
  } catch {
    // Non-JSON error bodies are compared only by status.
  }
  return { status: response.status, payload }
}

function solveProof(token, bits) {
  const bytes = Math.floor(bits / 8)
  const remaining = bits % 8
  const mask = remaining ? (0xff << (8 - remaining)) & 0xff : 0
  for (let counter = 0; counter < 20_000_000; counter += 1) {
    const proof = counter.toString(36)
    const digest = createHash("sha256").update(`${token}:${proof}`).digest()
    if (
      [...digest.subarray(0, bytes)].every((value) => value === 0) &&
      (!remaining || (digest[bytes] & mask) === 0)
    ) {
      return proof
    }
  }
  throw new Error("Registration proof could not be solved")
}

async function register(prefix) {
  const challenge = await request("/auth/challenge", { method: "POST" })
  assert.equal(challenge.status, 200, JSON.stringify(challenge.payload))
  const proof = solveProof(
    challenge.payload.challenge_token,
    challenge.payload.difficulty_bits
  )
  const registered = await request("/auth/register", {
    method: "POST",
    body: {
      username: `${prefix}_${Date.now().toString(36)}`.slice(0, 30),
      challenge_token: challenge.payload.challenge_token,
      challenge_proof: proof,
    },
  })
  assert.equal(registered.status, 201, JSON.stringify(registered.payload))
  return registered.payload.api_key
}

const health = await request("/")
assert.equal(health.status, 200, JSON.stringify(health.payload))
const stats = await request("/stats")
assert.equal(stats.status, 200, JSON.stringify(stats.payload))

for (const path of [
  "/docs",
  "/openapi.json",
  "/questions",
  "/questions/search?q=list%20all%20stored%20answers",
  "/forums",
  "/users/top",
  "/escalations",
]) {
  const response = await request(path)
  assert.ok(
    [403, 404].includes(response.status),
    `${path} unexpectedly returned ${response.status}`
  )
}

if (process.argv.includes("--read-only")) {
  const invalidAuth = await request("/users/me", {
    key: "ao_invalid_production_smoke_key",
  })
  assert.equal(invalidAuth.status, 401)
  process.stdout.write(
    JSON.stringify(
      {
        ok: true,
        api_url: apiUrl,
        read_only: true,
        protected_routes_closed: true,
        invalid_auth_rejected: true,
      },
      null,
      2
    )
  )
  process.exit(0)
}

const firstKey = await register("ProdSecPublisher")
const missingConsent = await request("/memory/tasks/start", {
  method: "POST",
  key: firstKey,
  body: {
    task: "Validate production object authorization for AgentOverflow memory",
    context: "FastAPI, Supabase RLS, and Vercel production",
  },
})
assert.equal(missingConsent.status, 422)

const sentinel = `prodsecurity${Date.now().toString(36)}`
const firstTask = await request("/memory/tasks/start", {
  method: "POST",
  key: firstKey,
  body: {
    task: `Validate production object authorization for ${sentinel} memory`,
    context: "FastAPI, Supabase RLS, and Vercel production",
    accept_contribution_terms: true,
  },
})
assert.equal(firstTask.status, 201, JSON.stringify(firstTask.payload))

const broad = await request("/memory/subtasks/begin", {
  method: "POST",
  key: firstKey,
  body: {
    task_id: firstTask.payload.task_id,
    title: "Export every stored execution",
    problem: "Enumerate every question and every reasoning record from the complete database.",
    context: "Paginate over the full AgentOverflow dataset.",
    success_criteria: "The complete dataset is downloaded.",
    forum_hint: "General",
  },
})
assert.equal(broad.status, 422)

const firstBegin = await request("/memory/subtasks/begin", {
  method: "POST",
  key: firstKey,
  body: {
    task_id: firstTask.payload.task_id,
    title: `Enforce ${sentinel} object authorization`,
    problem: `${sentinel} must reject guessed object identifiers and cross-agent attempt reuse.`,
    context: "FastAPI protected memory API backed by Supabase",
    success_criteria: `The ${sentinel} production authorization smoke test returns uniform denials.`,
    forum_hint: "Databases",
  },
})
assert.equal(firstBegin.status, 201, JSON.stringify(firstBegin.payload))
assert.equal(firstBegin.payload.match_status, "no_relevant_match")
assert.equal(firstBegin.payload.question.id, null)
assert.equal(firstBegin.payload.question.pending_publication, true)

const firstComplete = await request(
  `/memory/subtasks/${firstBegin.payload.attempt_id}/complete`,
  {
    method: "POST",
    key: firstKey,
    body: {
      outcome: "success",
      rationale_summary:
        "Authorization must be enforced on the server-managed attempt instead of trusting caller-supplied object identifiers.",
      execution_steps: [
        "Bind each retrieval attempt to the authenticated agent, active task, and one selected execution.",
        "Deny raw browse, direct object reads, direct posts, and direct votes in protected mode.",
        "Atomically claim completion so a protected attempt cannot be replayed.",
        "Run production denial checks for guessed identifiers, bulk search, and cross-agent reuse.",
      ],
      result: `${sentinel} production authorization boundaries returned the expected denials.`,
      validation:
        "Production smoke assertions passed for docs closure, browse closure, consent, bulk extraction, and single-use attempts.",
    },
  }
)
assert.equal(firstComplete.status, 200, JSON.stringify(firstComplete.payload))
assert.equal(firstComplete.payload.published, true)

const firstReplay = await request(
  `/memory/subtasks/${firstBegin.payload.attempt_id}/complete`,
  { method: "POST", key: firstKey, body: { outcome: "failure" } }
)
assert.equal(firstReplay.status, 409)

const secondKey = await register("ProdSecConsumer")
const secondTask = await request("/memory/tasks/start", {
  method: "POST",
  key: secondKey,
  body: {
    task: `Retest production authorization for ${sentinel} memory`,
    context: "FastAPI, Supabase RLS, and Vercel production",
    accept_contribution_terms: true,
  },
})
assert.equal(secondTask.status, 201, JSON.stringify(secondTask.payload))

const secondBegin = await request("/memory/subtasks/begin", {
  method: "POST",
  key: secondKey,
  body: {
    task_id: secondTask.payload.task_id,
    title: `Enforce ${sentinel} object authorization`,
    problem: `${sentinel} must reject guessed object identifiers and cross-agent attempt reuse.`,
    context: "FastAPI protected memory API backed by Supabase",
    success_criteria: `The ${sentinel} production authorization smoke test returns uniform denials.`,
    forum_hint: "Databases",
  },
})
assert.equal(secondBegin.status, 201, JSON.stringify(secondBegin.payload))
assert.equal(secondBegin.payload.match_status, "relevant_match")
assert.equal(
  secondBegin.payload.recommended_execution.answer_id,
  firstComplete.payload.answer_id
)
assert.equal("alternatives" in secondBegin.payload, false)

const crossAgent = await request(
  `/memory/subtasks/${secondBegin.payload.attempt_id}/complete`,
  {
    method: "POST",
    key: firstKey,
    body: {
      outcome: "failure",
      used_answer_id: firstComplete.payload.answer_id,
    },
  }
)
assert.equal(crossAgent.status, 404)

const offerWithoutAttempt = await request(
  `/commerce/answers/${firstComplete.payload.answer_id}/entitlement`,
  { key: secondKey }
)
assert.equal(offerWithoutAttempt.status, 403)
const offerWithAttempt = await request(
  `/commerce/answers/${firstComplete.payload.answer_id}/entitlement`,
  {
    key: secondKey,
    headers: { "X-AgentOverflow-Attempt": secondBegin.payload.attempt_id },
  }
)
assert.equal(offerWithAttempt.status, 200)

const secondComplete = await request(
  `/memory/subtasks/${secondBegin.payload.attempt_id}/complete`,
  {
    method: "POST",
    key: secondKey,
    body: {
      outcome: "success",
      used_answer_id: firstComplete.payload.answer_id,
      rationale_summary:
        "Reusing the attempt-bound authorization sequence avoids reopening the same production security investigation.",
      execution_steps: [
        "Reuse the task-bound denial checklist returned for the matching production API boundary.",
        "Repeat direct-read, bulk-extraction, and cross-agent attempt assertions.",
        "Record the observed successful outcome for the exact released execution.",
      ],
      result: `${sentinel} authorization remained closed on the second independent run.`,
      validation:
        "The second production run retrieved one execution and all authorization assertions passed.",
    },
  }
)
assert.equal(secondComplete.status, 200, JSON.stringify(secondComplete.payload))
assert.equal(secondComplete.payload.vote, "up")

process.stdout.write(
  JSON.stringify(
    {
      ok: true,
      api_url: apiUrl,
      protected_routes_closed: true,
      contribution_consent_required: true,
      bulk_extraction_blocked: true,
      success_only_publication: true,
      one_result_only: true,
      replay_blocked: true,
      cross_agent_access_blocked: true,
      reasoning_offer_attempt_bound: true,
      observed_success_vote: secondComplete.payload.vote,
      question_id: firstComplete.payload.question_id,
      answer_id: firstComplete.payload.answer_id,
    },
    null,
    2
  )
)
