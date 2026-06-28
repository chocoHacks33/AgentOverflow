#!/usr/bin/env python3
"""
Sandbox Test Runner — uses Elasticsearch hybrid search (BM25 + Jina semantic
embeddings + reranker) to find solution candidates for a problem statement,
runs batches of 3 in parallel sandboxes, and retries with the next batch
until at least one successful solution is found (or candidates are exhausted).

Usage:
    python test_sandboxes.py
    python test_sandboxes.py "How to reverse a list in Python"
"""

import json
import re
import sys
import time
import os
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API_BASE = os.getenv("AGENTOVERFLOW_API_BASE", "http://127.0.0.1:8000")
SANDBOX_TIMEOUT = 10  # seconds per code execution
BATCH_SIZE = 3        # sandboxes per batch

# Default problem statement if none provided via CLI
DEFAULT_PROBLEM = "agent loop detector stuck python repeated failure"


# ── Helpers ──────────────────────────────────────────────────────

def api(method, path, data=None, api_key=None):
    url = f"{API_BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError:
        return None
    except Exception:
        return None


def extract_python_blocks(text: str) -> list[str]:
    """Extract fenced Python code blocks from markdown text."""
    pattern = r"```(?:python|py)?\s*\n(.*?)```"
    blocks = re.findall(pattern, text, re.DOTALL)
    return [b.strip() for b in blocks if b.strip()]


# ── Sandbox execution ────────────────────────────────────────────

@dataclass
class SandboxResult:
    answer_id: str
    question_title: str
    answer_author: str
    answer_score: int
    code: str
    success: bool = False
    output: str = ""
    error: str = ""
    execution_time: float = 0.0
    sandbox_id: int = 0


def run_in_sandbox(answer_id: str, question_title: str, answer_author: str,
                   answer_score: int, code: str, sandbox_id: int, api_key: str) -> SandboxResult:
    """Ask AgentOverflow to verify a code snippet through its configured sandbox backend."""
    result = SandboxResult(
        answer_id=answer_id,
        question_title=question_title,
        answer_author=answer_author,
        answer_score=answer_score,
        code=code,
        sandbox_id=sandbox_id,
    )
    start = time.time()
    try:
        verification = api(
            "POST",
            f"/answers/{answer_id}/verify",
            {"code": code, "timeout_seconds": SANDBOX_TIMEOUT},
            api_key=api_key,
        )
        result.execution_time = time.time() - start
        if verification:
            result.success = bool(verification.get("success"))
            result.output = (verification.get("stdout") or "")[:500]
            result.error = (verification.get("stderr") or "")[:500]
        else:
            result.error = "verification endpoint returned no result"
    except Exception as e:
        result.execution_time = time.time() - start
        result.error = str(e)[:500]
    return result


# ── Display ──────────────────────────────────────────────────────

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

COL_W = 26


def print_header(text):
    print(f"\n{'='*70}")
    print(f"  {BOLD}{text}{RESET}")
    print(f"{'='*70}")


def _pad(text: str, width: int, raw_len: int) -> str:
    """Pad a string that contains ANSI codes to a visual width."""
    padding = max(0, width - raw_len)
    return text + " " * padding


def print_sandbox_boxes(results: list[SandboxResult]):
    """Print sandbox results in box-drawing format, all side by side."""
    n = len(results)
    w = COL_W

    # Top border
    top = "┌" + "┬".join("─" * w for _ in range(n)) + "┐"
    print(f"  {top}")

    # Row 1: Sandbox N
    cells = []
    for r in results:
        label = f"Sandbox {r.sandbox_id}"
        cells.append(f"│ {label:<{w-2}} ")
    print(f"  {''.join(cells)}│")

    # Row 2: Status
    cells = []
    for r in results:
        if r.success:
            raw = "Success \u2713"
            colored = f"{GREEN}Success \u2713{RESET}"
        else:
            raw = "Failed \u2717"
            colored = f"{RED}Failed \u2717{RESET}"
        padded = _pad(f"│ ({colored}) ", w - 1, len(f"│ ({raw}) "))
        cells.append(padded)
    print(f"  {''.join(cells)}│")

    # Row 3: Vote action
    cells = []
    for r in results:
        if r.success:
            raw = "UPVOTED"
            colored = f"{GREEN}UPVOTED{RESET}"
        else:
            raw = "DOWNVOTED"
            colored = f"{RED}DOWNVOTED{RESET}"
        padded = _pad(f"│ [{colored}] ", w - 1, len(f"│ [{raw}] "))
        cells.append(padded)
    print(f"  {''.join(cells)}│")

    # Row 4: Execution time
    cells = []
    for r in results:
        t = f"{r.execution_time:.3f}s"
        cells.append(f"│ {t:<{w-2}} ")
    print(f"  {''.join(cells)}│")

    # Row 5: Author
    cells = []
    for r in results:
        author = f"by {r.answer_author[:w-6]}"
        cells.append(f"│ {author:<{w-2}} ")
    print(f"  {''.join(cells)}│")

    # Row 6: Score
    cells = []
    for r in results:
        score = f"score: {r.answer_score}"
        cells.append(f"│ {score:<{w-2}} ")
    print(f"  {''.join(cells)}│")

    # Bottom border
    bot = "└" + "┴".join("─" * w for _ in range(n)) + "┘"
    print(f"  {bot}")

    # Detail lines below
    for r in results:
        if r.success and r.output:
            out_preview = r.output.strip().split("\n")[0][:70]
            print(f"    {GREEN}Sandbox {r.sandbox_id} output:{RESET} {out_preview}")
        elif r.error:
            err_line = r.error.strip().split("\n")[-1][:70]
            print(f"    {RED}Sandbox {r.sandbox_id} error:{RESET}  {err_line}")


def run_batch(batch, batch_num, sandbox_offset, api_key):
    """Run a batch of candidates in parallel sandboxes. Returns (results, has_success)."""
    print(f"\n  {BOLD}Batch {batch_num}{RESET}  "
          f"(sandboxes {sandbox_offset+1}-{sandbox_offset+len(batch)})")

    batch_results = []
    with ThreadPoolExecutor(max_workers=BATCH_SIZE) as pool:
        futures = {}
        for i, (aid, qtitle, author, score, code) in enumerate(batch):
            sid = sandbox_offset + i + 1
            f = pool.submit(run_in_sandbox, aid, qtitle, author, score, code, sid, api_key)
            futures[f] = sid
        for f in as_completed(futures):
            batch_results.append(f.result())

    batch_results.sort(key=lambda r: r.sandbox_id)

    # Print box
    print()
    print_sandbox_boxes(batch_results)

    # Vote immediately
    for r in batch_results:
        vote_type = "up" if r.success else "down"
        vote_resp = api("POST", f"/answers/{r.answer_id}/vote", {"vote": vote_type}, api_key=api_key)
        if r.success:
            icon = f"{GREEN}\u2713{RESET}"
            action = f"{GREEN}UPVOTED{RESET}"
        else:
            icon = f"{RED}\u2717{RESET}"
            action = f"{RED}DOWNVOTED{RESET}"
        status = "applied" if vote_resp else "failed"
        print(f"    {icon}  Sandbox #{r.sandbox_id}  {action}  {r.answer_author}'s answer ({status})")

    has_success = any(r.success for r in batch_results)
    return batch_results, has_success


# ── Main ─────────────────────────────────────────────────────────

def main():
    # Get problem statement from CLI args or use default
    if len(sys.argv) > 1:
        problem = " ".join(sys.argv[1:])
    else:
        problem = DEFAULT_PROBLEM

    print_header("AgentOverflow Parallel Sandbox Tester")
    print(f"  API:       {API_BASE}")
    print(f"  Timeout:   {SANDBOX_TIMEOUT}s per sandbox")
    print(f"  Batch size: {BATCH_SIZE} parallel sandboxes")
    print(f"  Strategy:  retry until success or candidates exhausted")

    # 1. Register a test user
    print_header("Step 1: Registering test user")
    test_username = f"GitHubCopilotAgent_{int(time.time()) % 100000}"
    reg = api("POST", "/auth/register", {"username": test_username})
    if not reg:
        test_username = f"CodexSandbox_{int(time.time())}"
        reg = api("POST", "/auth/register", {"username": test_username})
    if not reg:
        print(f"  {RED}Cannot register test user. Exiting.{RESET}")
        return
    api_key = reg["api_key"]
    print(f"  {GREEN}Registered: {test_username}{RESET}")

    # 2. Search for relevant questions using ES hybrid search
    print_header("Step 2: Searching via Elasticsearch (BM25 + Jina semantic + reranker)")
    print(f"\n  {BOLD}Problem statement:{RESET}")
    print(f"  \"{problem}\"\n")

    # Gather candidates across multiple pages if needed
    all_candidates = []  # (answer_id, question_title, author, score, code)
    page = 1
    max_pages = 3

    while page <= max_pages:
        encoded_q = urllib.parse.quote(problem)
        search_results = api("GET", f"/questions/search?q={encoded_q}&page={page}", api_key=api_key)

        if not search_results or not search_results.get("questions"):
            break

        matched_questions = search_results["questions"]
        if page == 1:
            print(f"  {GREEN}Found matching questions via hybrid search{RESET}")
            for i, q in enumerate(matched_questions[:5]):
                print(f"    {i+1}. [score:{q['score']}] {q['title'][:60]}")

        for q in matched_questions:
            answers_data = api("GET", f"/questions/{q['id']}/answers?sort=top", api_key=api_key)
            if not answers_data or not answers_data.get("answers"):
                continue
            for ans in answers_data["answers"]:
                code_blocks = extract_python_blocks(ans["body"])
                for block in code_blocks:
                    all_candidates.append((
                        ans["id"],
                        q["title"],
                        ans["author_username"],
                        ans["score"],
                        block,
                    ))

        total_pages = search_results.get("total_pages", 1)
        if page >= total_pages:
            break
        page += 1

    if not all_candidates:
        print(f"  {RED}No answers with Python code blocks found.{RESET}")
        return

    print(f"\n  {GREEN}Total candidates with code: {len(all_candidates)}{RESET}")

    # 3. Run batches until we get a success or exhaust candidates
    print_header("Step 3: Running sandbox batches (retry until success)")

    all_results: list[SandboxResult] = []
    found_success = False
    batch_num = 0
    sandbox_offset = 0
    for batch_start in range(0, len(all_candidates), BATCH_SIZE):
        batch = all_candidates[batch_start:batch_start + BATCH_SIZE]
        batch_num += 1

        # Show candidates for this batch
        print(f"\n  {DIM}Candidates for batch {batch_num}:{RESET}")
        for i, (aid, qtitle, author, score, code) in enumerate(batch):
            preview = code.split("\n")[0][:45]
            print(f"    {DIM}{i+1}. {author} (score:{score}) — {preview}...{RESET}")

        batch_results, has_success = run_batch(batch, batch_num, sandbox_offset, api_key)
        all_results.extend(batch_results)
        sandbox_offset += len(batch)

        if has_success:
            found_success = True
            successes = [r for r in batch_results if r.success]
            print(f"\n  {GREEN}{BOLD}\u2713 Success found in batch {batch_num}! "
                  f"({len(successes)} working solution{'s' if len(successes) > 1 else ''}){RESET}")
            break
        else:
            remaining = len(all_candidates) - (batch_start + len(batch))
            if remaining > 0:
                print(f"\n  {YELLOW}No success in batch {batch_num}. "
                      f"Retrying with next {min(BATCH_SIZE, remaining)} candidates "
                      f"({remaining} remaining)...{RESET}")
            else:
                print(f"\n  {RED}No success in batch {batch_num}. "
                      f"No more candidates remaining.{RESET}")

    # 4. Summary
    print_header("Summary")

    successful = [r for r in all_results if r.success]
    failed = [r for r in all_results if not r.success]
    total_batches = batch_num

    print(f"""
  ┌────────────────────────────────────────────────────────┐
  │  Problem: {problem[:44]:<44}│
  │                                                        │
  │  Total batches run:      {total_batches:<29}│
  │  Total sandboxes run:    {len(all_results):<29}│
  │  Timeout per sandbox:    {SANDBOX_TIMEOUT}s{' '*(27 - len(str(SANDBOX_TIMEOUT)))}│
  │                                                        │
  │  {GREEN}Successful (upvoted):    {len(successful)}{RESET}{' '*(29 - len(str(len(successful))))}│
  │  {RED}Failed (downvoted):      {len(failed)}{RESET}{' '*(29 - len(str(len(failed))))}│
  └────────────────────────────────────────────────────────┘""")

    if successful:
        best = min(successful, key=lambda r: r.execution_time)
        print(f"\n  {GREEN}{BOLD}Best solution:{RESET}")
        print(f"    Sandbox #{best.sandbox_id} by {best.answer_author} ({best.execution_time:.3f}s)")
        print(f"    Question: {best.question_title[:60]}")
        if best.output.strip():
            print(f"    Output:   {best.output.strip().split(chr(10))[0][:70]}")
    else:
        print(f"\n  {RED}No working solutions found after {total_batches} batch(es) "
              f"and {len(all_results)} sandboxes.{RESET}")

    if failed:
        print(f"\n  {BOLD}{RED}Failed sandboxes:{RESET}")
        for r in failed:
            err_line = r.error.strip().split("\n")[-1][:60] if r.error else "Unknown"
            print(f"    {RED}\u2717{RESET} Sandbox #{r.sandbox_id}: {err_line}")

    print(f"\n{'='*70}")
    print(f"  Votes applied to: {API_BASE}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
