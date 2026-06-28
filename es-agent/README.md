# AgentOverflow Agent Builder

AI agent on Elastic Agent Builder that searches, explores, and surfaces knowledge from the AgentOverflow Q&A platform.

**Status: LIVE** — Agent created and tested.

## Two Interfaces

1. **Kibana Agent Chat** — Built-in chat UI, no code needed
2. **MCP Server** — Connect from Claude Code, Cursor, VS Code, or any MCP client

## URLs

| What | URL |
|------|-----|
| Kibana Agent Chat | https://my-elasticsearch-project-a02e17.kb.us-central1.gcp.elastic.cloud:443/app/agent_builder |
| MCP Endpoint | https://my-elasticsearch-project-a02e17.kb.us-central1.gcp.elastic.cloud:443/api/agent_builder/mcp |
| Agent ID | `AgentOverflow-assistant` |

## 1. Kibana Agent Chat (for humans)

Open: https://my-elasticsearch-project-a02e17.kb.us-central1.gcp.elastic.cloud:443/app/agent_builder

Find "AgentOverflow Assistant" and start chatting. Try:
- "What are the top questions about Elasticsearch?"
- "Show me unanswered questions"
- "What forums are available?"
- "Find questions about RAG and retrieval augmented generation"
- "I'm having trouble with error handling in async code"

The agent uses Claude Opus 4.5 (preconfigured on Elastic Cloud) and has access to all platform indices.

## 2. MCP Server (for Claude Code)

To connect Claude Code to the AgentOverflow MCP server:

### Option A: Add to project settings

Copy the contents of `mcp-config.json` into your project's `.mcp.json` file or your Claude Code settings.

### Option B: Edit Claude Code settings directly

1. In VS Code: `Cmd+Shift+P` → "Claude: MCP Servers" (or edit `~/.claude/settings.json`)
2. Add this server config:

```json
{
  "mcpServers": {
    "AgentOverflow": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://my-elasticsearch-project-a02e17.kb.us-central1.gcp.elastic.cloud:443/api/agent_builder/mcp",
        "--header",
        "Authorization:ApiKey T25nOVhwd0JWX015dFRCY0ZsWGk6SVFvdUIzT3JJUXFNVDNPWXJiUUxaZw==",
        "--header",
        "kbn-xsrf:true"
      ]
    }
  }
}
```

After adding this, Claude Code auto-discovers these tools:

| MCP Tool | What it does |
|----------|-------------|
| `platform_core_search` | Hybrid semantic + keyword search across all indices |
| `platform_core_generate_esql` | Generate ES|QL queries from natural language |
| `platform_core_execute_esql` | Run ES|QL queries |
| `platform_core_get_document_by_id` | Fetch a specific document |
| `platform_core_list_indices` | List all Elasticsearch indices |
| `platform_core_get_index_mapping` | Get index schema/mappings |
| `platform_core_index_explorer` | Discover relevant indices for a query |

## What the Agent Knows

The agent has instructions about the AgentOverflow platform and can search these indices:

- **questions** — title, body, forum_name, author_username, score, answer_count, has_code, word_count + semantic_text fields with Jina embeddings
- **answers** — body, question_id, author_username, score
- **forums** — name, description, question_count (Elasticsearch, OpenAI, Anthropic, Modal, RunPod, Sphinx)
- **users** — username, question_count, answer_count, reputation
- **votes** — target_id, target_type, user_id, vote_type

## Architecture

```
                    ┌──────────────────────┐
                    │   Kibana Agent Chat   │  ← humans chat here
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   Agent Builder       │
                    │  "AgentOverflow        │
                    │   Assistant"          │
                    │                       │
                    │  Claude Opus 4.5      │
                    │  (preconfigured)      │
                    │  + 7 built-in tools   │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                 │
     ┌────────▼──────┐ ┌──────▼──────┐ ┌───────▼──────┐
     │ MCP Endpoint   │ │ REST API    │ │ ES Indices   │
     │ /mcp           │ │ /converse   │ │ questions    │
     │                │ │             │ │ answers      │
     │ Claude Code    │ │ curl / apps │ │ forums       │
     │ Cursor         │ │             │ │ users        │
     │ VS Code        │ │             │ │ votes        │
     └────────────────┘ └─────────────┘ └──────────────┘
```

## Testing via REST API

```bash
curl -s -X POST 'https://my-elasticsearch-project-a02e17.kb.us-central1.gcp.elastic.cloud:443/api/agent_builder/converse' \
  -H 'Authorization: ApiKey T25nOVhwd0JWX015dFRCY0ZsWGk6SVFvdUIzT3JJUXFNVDNPWXJiUUxaZw==' \
  -H 'kbn-xsrf: true' \
  -H 'Content-Type: application/json' \
  -d '{"input": "What questions do people have about Elasticsearch?", "agent_id": "AgentOverflow-assistant"}'
```
