#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# Test the AgentOverflow Agent
# ─────────────────────────────────────────────────────────────

KIBANA_URL="${KIBANA_URL:?Set KIBANA_URL}"
ES_API_KEY="${ES_API_KEY:?Set ES_API_KEY}"
AGENT_ID="${AGENT_ID:?Set AGENT_ID (from setup.sh output)}"

HEADERS=(
  -H "Authorization: ApiKey ${ES_API_KEY}"
  -H "kbn-xsrf: true"
  -H "Content-Type: application/json"
)

echo "=== Testing AgentOverflow Agent ==="
echo "Agent: ${AGENT_ID}"
echo ""

# Test 1: General search
echo "--- Test 1: Search for Elasticsearch topics ---"
RESULT=$(curl -s -X POST "${KIBANA_URL}/api/agent_builder/converse" \
  "${HEADERS[@]}" \
  -d "{\"input\": \"What questions do people have about Elasticsearch?\", \"agent_id\": \"${AGENT_ID}\"}")

echo "$RESULT" | python3 -c "
import sys, json
r = json.load(sys.stdin)
if 'output' in r:
    print(r['output'][:500])
elif 'message' in r:
    print(r['message'][:500])
else:
    print(json.dumps(r, indent=2)[:500])
" 2>/dev/null || echo "$RESULT" | head -c 500

echo ""
echo ""

# Test 2: Unanswered questions
echo "--- Test 2: Find unanswered questions ---"
RESULT=$(curl -s -X POST "${KIBANA_URL}/api/agent_builder/converse" \
  "${HEADERS[@]}" \
  -d "{\"input\": \"What questions need answers right now?\", \"agent_id\": \"${AGENT_ID}\"}")

echo "$RESULT" | python3 -c "
import sys, json
r = json.load(sys.stdin)
if 'output' in r:
    print(r['output'][:500])
elif 'message' in r:
    print(r['message'][:500])
else:
    print(json.dumps(r, indent=2)[:500])
" 2>/dev/null || echo "$RESULT" | head -c 500

echo ""
echo ""

# Test 3: Forum exploration
echo "--- Test 3: What forums are available? ---"
RESULT=$(curl -s -X POST "${KIBANA_URL}/api/agent_builder/converse" \
  "${HEADERS[@]}" \
  -d "{\"input\": \"What forums are available and what topics do they cover?\", \"agent_id\": \"${AGENT_ID}\"}")

echo "$RESULT" | python3 -c "
import sys, json
r = json.load(sys.stdin)
if 'output' in r:
    print(r['output'][:500])
elif 'message' in r:
    print(r['message'][:500])
else:
    print(json.dumps(r, indent=2)[:500])
" 2>/dev/null || echo "$RESULT" | head -c 500

echo ""
echo ""
echo "=== Tests complete ==="
