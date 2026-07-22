#!/usr/bin/env python3
"""
Phase 1 measurement: what % of Claude Code session context is spent on
pure-comprehension (explanation) turns?

Usage:
    python3 measure_explanation_turns.py                    # scan all projects
    python3 measure_explanation_turns.py ~/.claude/projects/<project-dir>
    python3 measure_explanation_turns.py path/to/session.jsonl

Reads Claude Code transcripts (JSONL, one event per line), groups events into
exchanges (user prompt + assistant activity until the next user prompt),
labels each exchange, and reports token share per label.

Labels:
  ACTION        - exchange contains a state-changing tool call (Edit/Write/Bash/...)
  RESEARCH      - read-only tool calls only (Read/Grep/Glob/WebSearch/...)
  COMPREHENSION - no tool calls AND prompt/reply look like pure explanation  <- evictable candidate
  DECISION      - no tool calls but decision/constraint language present     <- never evict
  OTHER         - none of the above

Token accounting: persistent context contribution of an exchange is estimated
as chars/4 of its stored content (what actually sits in the window forever).
Assistant `usage.output_tokens` is used when present as a cross-check.

NOTE: heuristic-only (Phase 1a). Retrospective reference-check and LLM labeling
(Phase 1b) refine this; expect this script to OVERESTIMATE evictable share.
"""

import json, os, re, sys, glob
from collections import defaultdict

MUTATING_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Bash", "TodoWrite"}
READONLY_TOOLS = {"Read", "Grep", "Glob", "WebSearch", "WebFetch", "LS", "Task", "Agent"}

EXPLAIN_PATTERNS = re.compile(
    r"\b(explain|plain english|in short|in simple|eli5|what does .{0,40}(mean|do)|"
    r"why (is|did|does|do|are)|summari[sz]e|walk me through|help me understand|"
    r"conclusion|understand(ing)?|clarify|difference between)\b", re.I)

DECISION_PATTERNS = re.compile(
    r"\b(let'?s use|we should|go with|instead of|don'?t use|never|always|prefer|"
    r"from now on|stick with|decided?|use option|approach [ab12])\b", re.I)

def text_of(content):
    """Flatten a message content field to plain text; return (text, tools_used)."""
    tools = []
    if isinstance(content, str):
        return content, tools
    parts = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            t = block.get("type")
            if t == "text":
                parts.append(block.get("text", ""))
            elif t == "tool_use":
                tools.append(block.get("name", "?"))
                parts.append(json.dumps(block.get("input", {}))[:2000])
            elif t == "tool_result":
                c = block.get("content", "")
                if isinstance(c, list):
                    c = " ".join(b.get("text", "") for b in c if isinstance(b, dict))
                parts.append(str(c))
    return "\n".join(parts), tools

def est_tokens(s):
    return max(1, len(s) // 4)

def load_exchanges(path):
    """Group JSONL events into exchanges keyed by real user prompts."""
    exchanges, cur = [], None
    with open(path, errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = ev.get("type")
            msg = ev.get("message") or {}
            content = msg.get("content", "")
            text, tools = text_of(content)
            if etype == "user":
                is_real_prompt = not (isinstance(content, list) and any(
                    isinstance(b, dict) and b.get("type") == "tool_result" for b in content))
                if is_real_prompt:
                    if cur:
                        exchanges.append(cur)
                    cur = {"prompt": text, "reply": "", "tools": [],
                           "tokens": est_tokens(text), "usage_out": 0}
                    continue
            if cur is None:
                continue
            cur["tokens"] += est_tokens(text)
            cur["tools"] += tools
            if etype == "assistant":
                cur["reply"] += "\n" + text
                usage = msg.get("usage") or {}
                cur["usage_out"] += usage.get("output_tokens", 0) or 0
    if cur:
        exchanges.append(cur)
    return exchanges

def label(ex):
    tools = set(ex["tools"])
    if tools & MUTATING_TOOLS:
        return "ACTION"
    if tools & READONLY_TOOLS:
        return "RESEARCH"
    blob = ex["prompt"] + " " + ex["reply"]
    if DECISION_PATTERNS.search(blob):
        return "DECISION"
    if EXPLAIN_PATTERNS.search(ex["prompt"]) or (
            not tools and "```" not in ex["reply"] and len(ex["reply"]) > 300):
        return "COMPREHENSION"
    return "OTHER"

def analyze(paths):
    grand = defaultdict(int); n_sessions = 0
    for path in paths:
        exchanges = load_exchanges(path)
        if len(exchanges) < 3:      # skip trivial sessions
            continue
        n_sessions += 1
        per = defaultdict(int)
        for ex in exchanges:
            lab = label(ex)
            per[lab] += ex["tokens"]; grand[lab] += ex["tokens"]
        total = sum(per.values()) or 1
        comp = per["COMPREHENSION"]
        print(f"{os.path.basename(path)[:36]:38s} "
              f"turns={len(exchanges):3d}  est_tokens={total:8d}  "
              f"comprehension={comp:7d} ({100*comp/total:4.1f}%)")
    total = sum(grand.values()) or 1
    print("\n=== OVERALL ({} sessions) ===".format(n_sessions))
    for lab in ("ACTION", "RESEARCH", "COMPREHENSION", "DECISION", "OTHER"):
        print(f"  {lab:14s} {grand[lab]:10d} tokens  {100*grand[lab]/total:5.1f}%")
    comp_pct = 100 * grand["COMPREHENSION"] / total
    print(f"\nEvictable-candidate share: {comp_pct:.1f}% "
          f"(heuristic upper bound; expect the refined number to be lower)")
    print("Go/no-go guide: >=20% strong go | 10-20% conditional | <10% probably stop")

if __name__ == "__main__":
    args = sys.argv[1:]
    root = os.path.expanduser(args[0]) if args else os.path.expanduser("~/.claude/projects")
    if root.endswith(".jsonl"):
        files = [root]
    else:
        files = glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)
    if not files:
        sys.exit(f"No .jsonl transcripts found under {root}")
    print(f"Scanning {len(files)} transcript(s)...\n")
    analyze(files)