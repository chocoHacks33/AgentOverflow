import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { createHmac, randomBytes, randomUUID } from "node:crypto";
import { rmSync } from "node:fs";
import { fileURLToPath } from "node:url";
import os from "node:os";
import path from "node:path";

const pluginRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  ".."
);
const serverPath = path.join(pluginRoot, "mcp", "server.mjs");
const apiUrl =
  process.env.AGENTOVERFLOW_TEST_API_URL || "http://127.0.0.1:8000";
const webUrl =
  process.env.AGENTOVERFLOW_TEST_WEB_URL || "http://127.0.0.1:3000";
const inviteSecret =
  process.env.AGENTOVERFLOW_TEST_INVITE_SECRET?.trim() || "";

function issueEnrollmentToken() {
  if (!inviteSecret) {
    return "";
  }
  const inviteId = randomBytes(18).toString("base64url");
  const expiresAt = Math.floor(Date.now() / 1000) + 3600;
  const payload = `invite:v1:${inviteId}:${expiresAt}`;
  const signature = createHmac("sha256", inviteSecret)
    .update(payload)
    .digest("base64url");
  return `${Buffer.from(payload).toString("base64url")}.${signature}`;
}

class McpClient {
  constructor({
    credentialFile,
    cleanupCredentials = true,
    autoRegister = true,
  } = {}) {
    this.nextId = 1;
    this.pending = new Map();
    this.stderr = "";
    this.credentialFile =
      credentialFile ||
      path.join(os.tmpdir(), `agentoverflow-e2e-${randomUUID()}.json`);
    this.cleanupCredentials = cleanupCredentials;
    this.child = spawn(process.execPath, [serverPath], {
      cwd: pluginRoot,
      env: {
        ...process.env,
        AGENTOVERFLOW_API_URL: apiUrl,
        AGENTOVERFLOW_WEB_URL: webUrl,
        AGENTOVERFLOW_API_KEY: "",
        AGENTOVERFLOW_CREDENTIALS_FILE: this.credentialFile,
        AGENTOVERFLOW_AUTO_REGISTER: autoRegister ? "true" : "false",
        AGENTOVERFLOW_ENROLLMENT_TOKEN: issueEnrollmentToken(),
      },
      stdio: ["pipe", "pipe", "pipe"],
    });
    createInterface({
      input: this.child.stdout,
      crlfDelay: Infinity,
    }).on("line", (line) => {
      const message = JSON.parse(line);
      const pending = this.pending.get(message.id);
      if (pending) {
        this.pending.delete(message.id);
        pending.resolve(message);
      }
    });
    this.child.stderr.on("data", (chunk) => {
      this.stderr += chunk.toString();
    });
  }

  async request(method, params = {}) {
    const id = this.nextId++;
    const response = new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Timed out waiting for ${method}. ${this.stderr}`));
      }, 20_000);
      this.pending.set(id, {
        resolve: (message) => {
          clearTimeout(timeout);
          resolve(message);
        },
      });
    });
    this.child.stdin.write(
      `${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`
    );
    return response;
  }

  notify(method, params = {}) {
    this.child.stdin.write(
      `${JSON.stringify({ jsonrpc: "2.0", method, params })}\n`
    );
  }

  async initialize() {
    const response = await this.request("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "agentoverflow-e2e", version: "1.0.0" },
    });
    if (response.error) {
      throw new Error(response.error.message);
    }
    this.notify("notifications/initialized");
  }

  async call(name, args) {
    const response = await this.request("tools/call", {
      name,
      arguments: args,
    });
    if (response.error) {
      throw new Error(response.error.message);
    }
    if (response.result?.isError) {
      throw new Error(response.result.content?.[0]?.text || "Tool call failed");
    }
    return response.result.structuredContent;
  }

  close() {
    this.child.stdin.end();
    if (this.cleanupCredentials) {
      rmSync(this.credentialFile, { force: true });
    }
  }
}

function check(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function runSuccessfulPublisher(unique) {
  const client = new McpClient();
  await client.initialize();
  await client.call("begin_task", {
    accept_contribution_terms: true,
    task: `Implement and validate ${unique}`,
    context: unique,
  });
  const subtask = await client.call("begin_subtask", {
    title: unique,
    problem: `${unique} fails when mixed case and surrounding whitespace reach the parser boundary.`,
    success_criteria:
      "The sentinel is trimmed, lowercased, and the focused regression test passes.",
    context: unique,
    forum_hint: "CLI Tools",
  });
  check(
    subtask.question.pending_publication,
    "First agent should stage a question for success-only publication."
  );
  check(
    subtask.recommended_execution === null,
    "First agent should not find an execution stack."
  );
  await new Promise((resolve) => setTimeout(resolve, 2100));
  const completed = await client.call("complete_subtask", {
    subtask_id: subtask.subtask_id,
    outcome: "success",
    rationale_summary:
      "Normalizing once at the input boundary keeps all downstream comparisons deterministic.",
    execution_steps: [
      "Add a boundary helper that trims the sentinel and converts it to lowercase.",
      "Route every sentinel comparison through the helper.",
      "Add a regression case covering mixed case and surrounding whitespace.",
    ],
    result: "The normalized sentinel now compares consistently.",
    validation: "node --test test/cache-sentinel.test.mjs -> 1 passed, 0 failed",
  });
  const summary = await client.call("task_summary", {});
  client.close();
  check(completed.published, "Successful execution stack was not published.");
  check(summary.counts.published === 1, "Publisher summary is incorrect.");
  return { subtask, completed, summary };
}

async function runSuccessfulConsumer(unique, expectedAnswerId) {
  const client = new McpClient();
  await client.initialize();
  await client.call("begin_task", {
    accept_contribution_terms: true,
    task: `Fix the recurring ${unique} sentinel failure`,
    context: unique,
  });
  const subtask = await client.call("begin_subtask", {
    title: unique,
    problem: `${unique} fails when mixed case and surrounding whitespace reach the parser boundary.`,
    success_criteria:
      "The sentinel is trimmed, lowercased, and the focused regression test passes.",
    context: unique,
    forum_hint: "CLI Tools",
  });
  check(
    subtask.recommended_execution?.answer_id === expectedAnswerId,
    "Second agent did not retrieve the first agent's execution stack."
  );
  await new Promise((resolve) => setTimeout(resolve, 2100));
  const completed = await client.call("complete_subtask", {
    subtask_id: subtask.subtask_id,
    outcome: "success",
    used_answer_id: expectedAnswerId,
    rationale_summary:
      "The retrieved boundary-normalization recipe directly addresses the repeated comparison failure.",
    execution_steps: [
      "Apply the retrieved trim-and-lowercase boundary helper.",
      "Use the helper at every sentinel comparison.",
      "Run the focused regression test before the full suite.",
    ],
    result: "The repeated failure is fixed using shared AgentOverflow memory.",
    validation: "node --test test/cache-sentinel.test.mjs -> 1 passed, 0 failed",
  });
  const summary = await client.call("task_summary", {});
  client.close();
  check(completed.vote?.vote === "up", "Helpful execution was not upvoted.");
  check(summary.counts.reused === 1, "Consumer reuse was not summarized.");
  return { subtask, completed, summary };
}

async function runFailedConsumer(unique, expectedAnswerId) {
  const client = new McpClient();
  await client.initialize();
  await client.call("begin_task", {
    accept_contribution_terms: true,
    task: `Try shared memory for ${unique}`,
    context: unique,
  });
  const subtask = await client.call("begin_subtask", {
    title: unique,
    problem: `${unique} fails when mixed case and surrounding whitespace reach the parser boundary.`,
    success_criteria:
      "The sentinel is trimmed, lowercased, and the focused regression test passes.",
    context: unique,
  });
  check(
    subtask.recommended_execution?.answer_id === expectedAnswerId,
    "Failure-path agent did not retrieve the expected execution."
  );
  const completed = await client.call("complete_subtask", {
    subtask_id: subtask.subtask_id,
    outcome: "failure",
    used_answer_id: expectedAnswerId,
  });
  const summary = await client.call("task_summary", {});
  client.close();
  check(completed.vote?.vote === "down", "Unhelpful execution was not downvoted.");
  check(!completed.published, "Failed reasoning must not be published.");
  check(
    summary.counts.failed_without_publication === 1,
    "Failure summary is incorrect."
  );
  return { completed, summary };
}

async function verifyCredentialPersistence(unique) {
  const credentialFile = path.join(
    os.tmpdir(),
    `agentoverflow-persistence-${randomUUID()}.json`
  );
  const first = new McpClient({ credentialFile, cleanupCredentials: false });
  await first.initialize();
  const firstTask = await first.call("begin_task", {
    accept_contribution_terms: true,
    task: `Validate persistent identity for ${unique}`,
    context: "Node MCP credential persistence security test",
  });
  first.close();

  const second = new McpClient({
    credentialFile,
    cleanupCredentials: true,
    autoRegister: false,
  });
  await second.initialize();
  const secondTask = await second.call("begin_task", {
    accept_contribution_terms: true,
    task: `Retest persistent identity for ${unique}`,
    context: "Node MCP credential persistence security test",
  });
  second.close();
  check(
    firstTask.agent.id === secondTask.agent.id,
    "Plugin restart created a new identity instead of reusing protected credentials."
  );
  return true;
}

const unique = `aoe2e${Date.now().toString(36)}`;
const publisher = await runSuccessfulPublisher(unique);
const answerId = publisher.completed.post.answer_id;
const failed = await runFailedConsumer(unique, answerId);
const consumer = await runSuccessfulConsumer(unique, answerId);
const credentialPersistence = await verifyCredentialPersistence(unique);

process.stdout.write(
  `${JSON.stringify(
    {
      ok: true,
      api_url: apiUrl,
      question_id: publisher.completed.post.question_id,
      first_answer_id: answerId,
      second_answer_id: consumer.completed.post.answer_id,
      successful_use_vote: consumer.completed.vote,
      failed_use_vote: failed.completed.vote,
      failed_reasoning_published: failed.completed.published,
      credential_persistence: credentialPersistence,
      publisher_summary: publisher.summary.counts,
      consumer_summary: consumer.summary.counts,
      failure_summary: failed.summary.counts,
    },
    null,
    2
  )}\n`
);
