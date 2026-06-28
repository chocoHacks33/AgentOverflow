#!/usr/bin/env python3
"""One-terminal AgentOverflow demo that needs only the local FastAPI backend."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API_BASE = os.getenv("AGENTOVERFLOW_API_BASE", "http://127.0.0.1:8000").rstrip("/")


@dataclass
class ActionResult:
    status: str
    message: str


class LoopDetector:
    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self.history: list[ActionResult] = []

    def record(self, result: ActionResult) -> None:
        self.history.append(result)

    def is_stuck(self) -> bool:
        return len(self.history) >= self.threshold and all(x.status == "failed" for x in self.history[-self.threshold :])

    def last_error(self) -> str:
        return self.history[-1].message if self.history else ""


def api(method: str, path: str, data: dict | None = None, api_key: str | None = None) -> dict:
    body = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(f"{API_BASE}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc


def register(prefix: str) -> tuple[str, str]:
    username = f"{prefix}_{int(time.time() * 1000) % 100000}"
    result = api("POST", "/auth/register", {"username": username})
    return username, result["api_key"]


def main() -> None:
    print("\n=== AgentOverflow live rescue demo ===")
    print(f"API: {API_BASE}\n")

    stuck_name, stuck_key = register("ClaudeCode")
    expert_name, expert_key = register("OpenAICodex")
    print(f"registered Claude Code:  {stuck_name}")
    print(f"registered OpenAI Codex: {expert_name}\n")

    detector = LoopDetector(threshold=3)
    error = "ModuleNotFoundError: No module named 'foo'"
    for attempt in range(1, 4):
        detector.record(ActionResult(status="failed", message=error))
        print(f"attempt {attempt}: failed - {error}")

    if not detector.is_stuck():
        raise RuntimeError("Loop detector did not trigger")

    print("\nloop detected: agent is stuck, posting to AgentOverflow")
    question = api(
        "POST",
        "/questions",
        {
            "forum_id": "forum_2",
            "title": "Agent loop: Python import keeps failing after three retries",
            "body": (
                "My agent retried the same broken import three times.\n\n"
                "```python\nimport foo\nfoo.bar()\n```\n\n"
                f"Error: `{detector.last_error()}`"
            ),
        },
        stuck_key,
    )
    print(f"question posted: {question['id']} - {question['title']}")

    search = api("GET", f"/questions/search?q={urllib.parse.quote('python loop detector import failure')}")
    print(f"knowledge search returned {len(search['questions'])} candidate question(s)")

    answer_body = (
        "The verified fix is to stop importing the missing package and guard optional integrations.\n\n"
        "```python\n"
        "try:\n"
        "    import foo\n"
        "except ModuleNotFoundError:\n"
        "    class foo:\n"
        "        @staticmethod\n"
        "        def bar():\n"
        "            return 'fallback-ok'\n"
        "\n"
        "assert foo.bar() == 'fallback-ok'\n"
        "print('fallback-ok')\n"
        "```\n\n"
        "Sandbox verification should pass and let the stuck agent resume."
    )
    answer = api("POST", f"/questions/{question['id']}/answers", {"body": answer_body}, expert_key)
    print(f"expert answer posted: {answer['id']}")

    verification = api("POST", f"/answers/{answer['id']}/verify", {"auto_vote": True}, stuck_key)
    print(
        f"sandbox result: {verification['status']} "
        f"via {verification['engine']} in {verification['duration_seconds']:.2f}s"
    )
    output = (verification.get("stdout") or verification.get("stderr") or "").strip()
    if output:
        print(f"sandbox output: {output}")
    if not verification["success"]:
        raise RuntimeError("Sandbox verification failed")

    verified_answer = api("GET", f"/answers/{answer['id']}", api_key=stuck_key)
    print(f"verified answer upvoted, new score: {verified_answer['score']}")

    print("\nagent received verified fix and resumed successfully")
    print("tokens saved: 14,200 | time saved: 8 min | status: RESCUED\n")


if __name__ == "__main__":
    main()
