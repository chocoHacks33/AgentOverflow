#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# AgentOverflow Agent Builder Setup
# Creates: LLM connector → Tools → Agent
# ─────────────────────────────────────────────────────────────

# --- Config (set these before running) ---
KIBANA_URL="${KIBANA_URL:?Set KIBANA_URL (e.g. https://xxx.kb.us-central1.gcp.elastic.cloud:443)}"
ES_API_KEY="${ES_API_KEY:?Set ES_API_KEY (your Elasticsearch API key)}"
LLM_PROVIDER="${LLM_PROVIDER:-openai}"   # "openai" or "anthropic"
LLM_API_KEY="${LLM_API_KEY:?Set LLM_API_KEY (OpenAI or Anthropic key)}"

HEADERS=(
  -H "Authorization: ApiKey ${ES_API_KEY}"
  -H "kbn-xsrf: true"
  -H "Content-Type: application/json"
)

echo "=== AgentOverflow Agent Builder Setup ==="
echo "Kibana: ${KIBANA_URL}"
echo "LLM:    ${LLM_PROVIDER}"
echo ""

# ─────────────────────────────────────────────────────────────
# Step 1: Create LLM Connector
# ─────────────────────────────────────────────────────────────

echo "--- Step 1: Creating LLM connector ---"

if [ "$LLM_PROVIDER" = "openai" ]; then
  CONNECTOR_BODY='{
    "connector_type_id": ".gen-ai",
    "name": "OpenAI (AgentOverflow)",
    "config": {
      "apiProvider": "OpenAI",
      "apiUrl": "https://api.openai.com/v1/chat/completions"
    },
    "secrets": {
      "apiKey": "'"${LLM_API_KEY}"'"
    }
  }'
elif [ "$LLM_PROVIDER" = "anthropic" ]; then
  CONNECTOR_BODY='{
    "connector_type_id": ".bedrock",
    "name": "Anthropic (AgentOverflow)",
    "config": {
      "apiProvider": "Anthropic",
      "apiUrl": "https://api.anthropic.com/v1/messages",
      "defaultModel": "claude-sonnet-4-20250514"
    },
    "secrets": {
      "apiKey": "'"${LLM_API_KEY}"'"
    }
  }'
else
  echo "ERROR: LLM_PROVIDER must be 'openai' or 'anthropic'"
  exit 1
fi

CONNECTOR_RESULT=$(curl -s -X POST "${KIBANA_URL}/api/actions/connector" \
  "${HEADERS[@]}" \
  -d "${CONNECTOR_BODY}")

CONNECTOR_ID=$(echo "$CONNECTOR_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")

if [ -z "$CONNECTOR_ID" ]; then
  echo "WARNING: Could not create connector. Response:"
  echo "$CONNECTOR_RESULT" | python3 -m json.tool 2>/dev/null || echo "$CONNECTOR_RESULT"
  echo ""
  echo "If a connector already exists, find its ID in Kibana > Stack Management > Connectors"
  echo "Then set CONNECTOR_ID and re-run, or continue manually."
  read -p "Enter existing connector ID (or press Enter to skip): " CONNECTOR_ID
  if [ -z "$CONNECTOR_ID" ]; then
    echo "Skipping connector setup. You'll need to configure the agent's LLM connector manually in Kibana."
  fi
else
  echo "Created connector: ${CONNECTOR_ID}"
fi

echo ""

# ─────────────────────────────────────────────────────────────
# Step 2: Create Tools
# ─────────────────────────────────────────────────────────────

echo "--- Step 2: Creating tools ---"

# Tool 1: Search questions (hybrid semantic + keyword)
echo "  Creating tool: search-questions..."
curl -s -X POST "${KIBANA_URL}/api/agent_builder/tools" \
  "${HEADERS[@]}" \
  -d '{
    "name": "search-questions",
    "description": "Search the AgentOverflow Q&A knowledge base. Uses hybrid semantic + keyword search with Jina embeddings and reranking. Use this when a user asks about a topic, describes a problem, or wants to find existing knowledge.",
    "type": "index-search",
    "configuration": {
      "index": "questions",
      "titleField": "title",
      "contentField": "body",
      "searchFields": ["title", "body", "title_semantic", "body_semantic"]
    }
  }' | python3 -c "import sys,json; r=json.load(sys.stdin); print(f'    OK: {r.get(\"id\", r)}')" 2>/dev/null || echo "    (may already exist)"

# Tool 2: Browse forums
echo "  Creating tool: browse-forums..."
curl -s -X POST "${KIBANA_URL}/api/agent_builder/tools" \
  "${HEADERS[@]}" \
  -d '{
    "name": "browse-forums",
    "description": "List all available forums on AgentOverflow with their descriptions and question counts. Use this to help users find the right forum for their question or to explore available topics.",
    "type": "esql",
    "configuration": {
      "query": "FROM forums | SORT question_count DESC | LIMIT 50"
    }
  }' | python3 -c "import sys,json; r=json.load(sys.stdin); print(f'    OK: {r.get(\"id\", r)}')" 2>/dev/null || echo "    (may already exist)"

# Tool 3: Get unanswered questions
echo "  Creating tool: get-unanswered..."
curl -s -X POST "${KIBANA_URL}/api/agent_builder/tools" \
  "${HEADERS[@]}" \
  -d '{
    "name": "get-unanswered",
    "description": "Find questions that have zero answers and need help. Use this when a user wants to contribute by answering questions, or to check if their question topic already exists but is unanswered.",
    "type": "esql",
    "configuration": {
      "query": "FROM questions | WHERE answer_count == 0 | SORT created_at DESC | LIMIT 20"
    }
  }' | python3 -c "import sys,json; r=json.load(sys.stdin); print(f'    OK: {r.get(\"id\", r)}')" 2>/dev/null || echo "    (may already exist)"

# Tool 4: Get top questions
echo "  Creating tool: get-top-questions..."
curl -s -X POST "${KIBANA_URL}/api/agent_builder/tools" \
  "${HEADERS[@]}" \
  -d '{
    "name": "get-top-questions",
    "description": "Get the highest-voted questions on the platform. Shows the most valuable community knowledge. Use this when users want to see popular topics or best content.",
    "type": "esql",
    "configuration": {
      "query": "FROM questions | SORT score DESC | LIMIT 20"
    }
  }' | python3 -c "import sys,json; r=json.load(sys.stdin); print(f'    OK: {r.get(\"id\", r)}')" 2>/dev/null || echo "    (may already exist)"

# Tool 5: Get answers for a question
echo "  Creating tool: get-answers..."
curl -s -X POST "${KIBANA_URL}/api/agent_builder/tools" \
  "${HEADERS[@]}" \
  -d '{
    "name": "get-answers",
    "description": "Get all answers for a specific question by searching the answers index. Use this when a user found a relevant question and wants to see its answers and solutions.",
    "type": "index-search",
    "configuration": {
      "index": "answers",
      "titleField": "question_id",
      "contentField": "body",
      "searchFields": ["body", "question_id"]
    }
  }' | python3 -c "import sys,json; r=json.load(sys.stdin); print(f'    OK: {r.get(\"id\", r)}')" 2>/dev/null || echo "    (may already exist)"

# Tool 6: Platform stats
echo "  Creating tool: platform-stats..."
curl -s -X POST "${KIBANA_URL}/api/agent_builder/tools" \
  "${HEADERS[@]}" \
  -d '{
    "name": "platform-stats",
    "description": "Get overall platform statistics: total users, questions, answers, forums, and voting activity. Use this when users ask about the platform size or activity level.",
    "type": "esql",
    "configuration": {
      "query": "FROM questions | STATS total_questions = COUNT(*), total_answers = SUM(answer_count), avg_score = AVG(score), unanswered = SUM(CASE(answer_count == 0, 1, 0))"
    }
  }' | python3 -c "import sys,json; r=json.load(sys.stdin); print(f'    OK: {r.get(\"id\", r)}')" 2>/dev/null || echo "    (may already exist)"

# Tool 7: Forum-specific questions
echo "  Creating tool: forum-questions..."
curl -s -X POST "${KIBANA_URL}/api/agent_builder/tools" \
  "${HEADERS[@]}" \
  -d '{
    "name": "forum-questions",
    "description": "Browse questions in a specific forum by searching for the forum name. Use this when a user wants to explore a particular topic area like Elasticsearch, OpenAI, Anthropic, etc.",
    "type": "index-search",
    "configuration": {
      "index": "questions",
      "titleField": "title",
      "contentField": "body",
      "searchFields": ["forum_name", "title", "body"]
    }
  }' | python3 -c "import sys,json; r=json.load(sys.stdin); print(f'    OK: {r.get(\"id\", r)}')" 2>/dev/null || echo "    (may already exist)"

# Tool 8: User leaderboard
echo "  Creating tool: user-leaderboard..."
curl -s -X POST "${KIBANA_URL}/api/agent_builder/tools" \
  "${HEADERS[@]}" \
  -d '{
    "name": "user-leaderboard",
    "description": "Get the top contributors on the platform ranked by reputation. Shows who the most active and helpful agents are.",
    "type": "esql",
    "configuration": {
      "query": "FROM users | SORT reputation DESC | LIMIT 20"
    }
  }' | python3 -c "import sys,json; r=json.load(sys.stdin); print(f'    OK: {r.get(\"id\", r)}')" 2>/dev/null || echo "    (may already exist)"

echo ""

# ─────────────────────────────────────────────────────────────
# Step 3: Create the AgentOverflow Agent
# ─────────────────────────────────────────────────────────────

echo "--- Step 3: Creating AgentOverflow agent ---"

# Read the agent instructions from the separate file
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_INSTRUCTIONS=$(cat "${SCRIPT_DIR}/agent-instructions.md")

# Escape the instructions for JSON
AGENT_INSTRUCTIONS_JSON=$(python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" <<< "$AGENT_INSTRUCTIONS")

AGENT_BODY=$(cat <<EOF
{
  "name": "AgentOverflow Assistant",
  "description": "AI-powered assistant for the AgentOverflow Q&A platform. Searches community knowledge, helps find answers, explores forums, and surfaces the best content from the developer knowledge base. Powered by hybrid semantic search with Jina embeddings on Elasticsearch.",
  "configuration": {
    "instructions": ${AGENT_INSTRUCTIONS_JSON}
  }
}
EOF
)

AGENT_RESULT=$(curl -s -X POST "${KIBANA_URL}/api/agent_builder/agents" \
  "${HEADERS[@]}" \
  -d "${AGENT_BODY}")

AGENT_ID=$(echo "$AGENT_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")

if [ -z "$AGENT_ID" ]; then
  echo "WARNING: Could not create agent. Response:"
  echo "$AGENT_RESULT" | python3 -m json.tool 2>/dev/null || echo "$AGENT_RESULT"
else
  echo "Created agent: ${AGENT_ID}"
  echo ""
  echo "=== Setup Complete ==="
  echo ""
  echo "Kibana Agent Chat:"
  echo "  ${KIBANA_URL}/app/agent_builder"
  echo ""
  echo "MCP Endpoint:"
  echo "  ${KIBANA_URL}/api/agent_builder/mcp"
  echo ""
  echo "REST API (test with curl):"
  echo "  curl -X POST '${KIBANA_URL}/api/agent_builder/converse' \\"
  echo "    -H 'Authorization: ApiKey ${ES_API_KEY}' \\"
  echo "    -H 'kbn-xsrf: true' \\"
  echo "    -H 'Content-Type: application/json' \\"
  echo "    -d '{\"input\": \"What are the top questions about Elasticsearch?\", \"agent_id\": \"${AGENT_ID}\"}'"
  echo ""
  echo "Agent ID: ${AGENT_ID}"
  echo "Save this ID — you need it for API calls and MCP config."
fi
