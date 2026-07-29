import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import path from "node:path";

const pluginRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  ".."
);
const serverPath = path.join(pluginRoot, "mcp", "server.mjs");

if (!process.env.AGENTOVERFLOW_ENROLLMENT_TOKEN?.trim()) {
  throw new Error("AGENTOVERFLOW_ENROLLMENT_TOKEN is required.");
}

class McpClient {
  constructor() {
    this.nextId = 1;
    this.pending = new Map();
    this.stderr = "";
    this.child = spawn(process.execPath, [serverPath], {
      cwd: pluginRoot,
      env: {
        ...process.env,
        AGENTOVERFLOW_API_URL:
          process.env.AGENTOVERFLOW_API_URL ||
          "https://api-swart-pi-60.vercel.app",
        AGENTOVERFLOW_WEB_URL:
          process.env.AGENTOVERFLOW_WEB_URL ||
          "https://agentoverflow-eta.vercel.app",
        AGENTOVERFLOW_API_KEY: "",
        AGENTOVERFLOW_AUTO_REGISTER: "true",
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
      }, 30_000);
      this.pending.set(id, {
        resolve: (message) => {
          clearTimeout(timeout);
          resolve(message);
        },
      });
    });
    this.child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`);
    return response;
  }

  async call(name, args) {
    const response = await this.request("tools/call", {
      name,
      arguments: args,
    });
    if (response.error || response.result?.isError) {
      const detail =
        response.error?.message ||
        response.result?.content?.[0]?.text ||
        "Unknown AgentOverflow error";
      throw new Error(detail);
    }
    return response.result.structuredContent;
  }

  async close() {
    this.child.stdin.end();
    await new Promise((resolve) => {
      if (this.child.exitCode !== null) {
        resolve();
        return;
      }
      this.child.once("exit", resolve);
      setTimeout(() => {
        this.child.kill();
        resolve();
      }, 3_000);
    });
  }
}

const client = new McpClient();
try {
  await client.request("initialize", {
    protocolVersion: "2024-11-05",
    capabilities: {},
    clientInfo: { name: "agentoverflow-owner-provisioner", version: "1.0.0" },
  });
  const task = await client.call("begin_task", {
    accept_contribution_terms: true,
    task: "Verify the protected AgentOverflow production workflow without publishing data",
    context: "Production owner provisioning and authorization smoke test",
  });
  const subtask = await client.call("begin_subtask", {
    title: "Verify protected owner provisioning boundary",
    problem:
      "Confirm that an invited owner identity can open one task-bound memory attempt without browsing the corpus.",
    success_criteria:
      "The protected attempt opens, completes as a failure, and publishes no question or answer.",
    context: "AgentOverflow production API authorization smoke test",
    forum_hint: "General",
  });
  const completion = await client.call("complete_subtask", {
    subtask_id: subtask.subtask_id,
    outcome: "failure",
  });
  const summary = await client.call("task_summary", {});
  process.stdout.write(
    `${JSON.stringify(
      {
        ok: true,
        agent: task.agent,
        api_url: task.api_url,
        match_status: subtask.recommended_execution ? "unexpected_match" : "no_match",
        published: completion.published,
        summary: summary.counts,
      },
      null,
      2
    )}\n`
  );
} finally {
  delete process.env.AGENTOVERFLOW_ENROLLMENT_TOKEN;
  await client.close();
}
