# Explanation-Turn Eviction: Intent-Based Context Pruning for Coding Agents

**Working title:** "Delete What Can Be Regenerated: Intent-Based Context Eviction for Long-Running Agent Sessions"
**Author:** Thamilvendhan M
**Status:** Research plan — Phase 1 (measurement) not yet started
**Date:** July 2026

---

## 1. The Idea in One Paragraph

In long coding-agent sessions (Claude Code, Codex CLI, etc.), a large share of turns are
*comprehension turns*: the user asks "explain this in plain English", "why did you do that?",
"what does this mean?" — follow-ups that build the human's understanding but trigger no action,
no file change, and no decision. These exchanges are **regenerable**: the model can re-create
any explanation at any time from the code and decisions that remain in context. Therefore they
are the safest possible content to evict — yet no shipped tool or published system classifies
turns by intent and evicts on that basis. The hypothesis: **evicting pure-comprehension turns
at task boundaries cuts session token growth significantly (target: 20%+) with zero loss in
task success.**

---

## 2. Why This Is a Real Gap (Prior-Art Check, July 2026)

Every existing context-reduction technique targets one of three axes — none targets *intent*:

| Axis | What it prunes | Who ships it |
|---|---|---|
| **Bulk** | Large tool outputs (file reads, test logs) | Claude Code microcompaction, Anthropic context editing, OpenClaw session pruning, OpenCode prune |
| **Age** | Old turns, everything before a threshold | /compact, auto-compact, Codex server-side compact |
| **Similarity** | Turns not semantically related to current query | LangChain VectorStoreRetrieverMemory, MemGPT/Letta recall, Mem0, Zep |
| **Intent (THIS WORK)** | Turns whose *purpose* was human comprehension only | **Nobody** |

Closest research (not shipped, and different angle):

- *Less Context, Better Agents* (arXiv 2606.10209): pruning whole tool-interaction units +
  rolling summary → task success 71% → 91.6%, tokens 1.48M → 553K. Key lesson: **stale context
  actively hurts performance; unit-level deletion beats token-level compression.**
- *ActiveContext* (arXiv 2604.11462): RL-trained 7B curator prunes noise → up to 8× token
  reduction, higher success. Key lesson: **the bottleneck is signal-to-noise, not capacity.**
- Open problems named by these papers: importance-pruning (recently-*referenced* vs recently
  *added*), reasoning anchors, staleness detection. Intent-based eviction is adjacent to
  importance-pruning but is a distinct, more tractable slice.

Why the incumbents haven't done it: their pruning is content-driven (size, age) because that
needs no semantic judgment. Intent classification requires understanding *what a turn was for* —
a small extra step nobody has bothered to take, but cheap with today's models.

### Supporting trend

Vibe coding / non-expert usage is growing. Non-experts ask far more "explain" questions than
professionals, so the share of comprehension turns in real sessions is rising. The idea gets
*more* valuable over time.

---

## 3. Core Principle: Regenerability

> **Keep only what cannot be regenerated. Evict first what can be fully re-derived from
> what remains.**

Content classes ranked by regenerability (evict top-first):

1. **Explanations / rephrasings / plain-English summaries** — fully regenerable from code +
   decisions. ← *this work's target*
2. **Tool outputs** — regenerable by re-running the tool (already handled by existing pruning).
3. **Reasoning that led to a decision** — partially regenerable; keep the decision, drop the path.
4. **Decisions, constraints, user preferences** — NOT regenerable. Never evict.
5. **User corrections ("no, not like that")** — NOT regenerable. Never evict.
6. **Current file/state facts** — regenerable from disk but cheap to keep pinned.

---

## 4. Turn Taxonomy (the classifier's labels)

Each assistant/user exchange gets one label:

- **ACTION** — caused a state change: file edit, command run, commit, config change.
- **DECISION** — produced or changed a plan, constraint, or preference
  ("use approach B", "never touch auth module", "target Python 3.11").
- **COMPREHENSION** — pure understanding-building: explain / why / what-does-this-mean /
  plain-English / summarize-for-me, with **no** state change and **no** new decision. ← evictable
- **CORRECTION** — user fixed the agent's misunderstanding. Never evict.
- **MIXED** — comprehension exchange that *contains* a decision or correction inside it.
  Mine the decision out (one line), then treat remainder as COMPREHENSION.

### Classification signals

Cheap heuristics (Phase 1 can start with these):
- No tool_use blocks in the assistant reply → strong COMPREHENSION signal.
- Prompt patterns: "explain", "in plain english", "in short", "why", "what does … mean",
  "summarize", "eli5", "conclusion?".
- Assistant reply is long prose with no code fences / no diffs.

Necessary retrospective check (the hard part — see §6.3):
- A turn is only *confirmed* COMPREHENSION if **no later turn took action on it or referred
  back to it**. Classification must be finalized looking backward (e.g., at task boundaries),
  not at the moment the turn happens.

---

## 5. System Design (target: Claude Code first)

### 5.1 Pipeline

```
every turn ──► tag (heuristic intent guess)
task boundary / compaction trigger ──►
    1. finalize labels retrospectively (was anything referenced later?)
    2. MINE: extract decisions/corrections/preferences from MIXED turns → one-liners
    3. EVICT: remove confirmed COMPREHENSION turns
    4. TOMBSTONE: leave one line per evicted exchange
       e.g. "[evicted] explained caching tradeoff; user confirmed understanding; chose B"
    5. batch the rewrite with a cache-expiry or compaction moment (see §6.4)
```

### 5.2 Where it can live (implementation options)

| Option | True deletion? | Effort | Notes |
|---|---|---|---|
| **A. Offline measurement scripts** | n/a | Days | Phase 1. Parse Claude Code transcripts, no product needed. |
| B. Claude Code plugin (slash command) | No — rides on steered /compact | 1–2 weeks | `/task-done` → steered compact with eviction instructions. Approximate but shippable & installable. Hooks CANNOT delete turns (verified against hooks docs, July 2026 — transcript is immutable to plugins). |
| C. API proxy (`ANTHROPIC_BASE_URL`) | **Yes** — strips turns from each request before forwarding | 3–6 weeks | Real surgical eviction. Precedent: claude-mem, claude-code-router. Clean with API keys; subscription OAuth traffic is murkier. |
| D. Own harness via Claude Agent SDK | Yes — full control of message array | Most | Best for the *paper*; full experimental control. |

**Recommended path: A → (C or D). Skip B unless you want early users fast.**

### 5.3 Claude Code data source (Phase 1)

Claude Code stores full session transcripts as JSONL:

```
~/.claude/projects/<project-hash>/<session-uuid>.jsonl
```

Each line is an event (user message, assistant message, tool_use, tool_result) and assistant
events carry `usage` fields (input/output token counts). This is everything needed to measure
the idea on **your own real sessions** with zero instrumentation.

---

## 6. The Four Failure Modes (and the required mitigations)

These came out of adversarial review of the idea. A credible version MUST handle all four.

### 6.1 Explanations secretly contain decisions
Mid-explanation the user says "oh, then let's use option B" or "avoid recursion, I don't get it."
**Mitigation:** MIXED label + decision-mining step before eviction. Never delete without mining.

### 6.2 Later references break ("do it the way you explained")
**Mitigation:** (a) defer eviction to task boundaries, never immediate; (b) tombstones that
name the topic so the model knows an explanation existed and can regenerate it; (c) the
retrospective reference check in §4.

### 6.3 Prompt-time classification is unreliable
"Explain why this test fails" looks like COMPREHENSION but is debugging (leads to ACTION).
**Mitigation:** two-stage labels — provisional at turn time, **finalized retrospectively**:
confirmed-evictable ⇔ no subsequent ACTION consumed it and no subsequent turn referenced it.

### 6.4 The cache trap
Deleting a middle turn invalidates the cached prefix; done naively, "saving" tokens costs more.
**Mitigation:** batch evictions with moments the cache is already being broken or has expired —
piggyback on compaction events, or use the cache-TTL-aware timing trick shipped by OpenClaw
(prune only after the 5-minute cache TTL lapses, then re-establish the cache once).
**Metric discipline:** always report *cost* (cache-adjusted $) alongside raw token counts.

---

## 7. Phase 1 — Measurement (the go/no-go gate)

**Question:** what fraction of real Claude Code session tokens belong to confirmed
COMPREHENSION turns?

**Method:**
1. Collect 20–50 real session transcripts from `~/.claude/projects/` (own sessions first;
   later, ask community for donated anonymized transcripts).
2. Script A (heuristic pass): label every exchange with the taxonomy in §4 using the cheap
   signals. Count tokens per label (use the `usage` fields; fall back to a tokenizer estimate
   for user turns).
3. Script B (LLM pass): have a model (Haiku-class is enough) label the same exchanges;
   measure agreement with heuristics; adjudicate disagreements by hand on a sample.
4. Apply the retrospective filter: demote any COMPREHENSION turn that a later turn referenced.
5. Report: % of turns and **% of tokens** that are confirmed-evictable, per session and overall;
   distribution across session types (pro coding vs exploratory/learning sessions).

**Go/no-go:**
- ≥ 20% of tokens evictable → strong; proceed to Phase 2 and start writing.
- 10–20% → proceed, but position as one layer that composes with tool-result pruning.
- < 5–10% → publish the negative/measurement result as a short note; stop building.

*(Even the measurement alone — "what are agent-session tokens actually spent on, by intent?" —
is a publishable/bloggable contribution. Nobody has published this breakdown.)*

## 8. Phase 2 — Ablation Replay (does eviction hurt?)

1. Take sessions with known outcomes (task completed, tests passing).
2. Build two context variants at several checkpoints: FULL vs EVICTED
   (comprehension turns removed, tombstones + mined decisions inserted).
3. Replay the next user turn(s) against both variants (Agent SDK or direct API).
4. Judge outputs: same actions taken? same files edited? decision consistency?
   (LLM-as-judge + spot manual review; 3-vote judging to reduce noise.)
5. Report: Δ task success, Δ tokens, Δ cache-adjusted cost, Δ answer consistency.

**Headline claim to aim for:** *"Same task success, N% fewer tokens, sessions run M× longer
before hitting compaction."* Per the *Less Context, Better Agents* result, success may even
**improve** — stale explanations are noise. If observed, that's the strongest possible finding.

## 9. Phase 3 — Live Prototype

- Implement option C (proxy) or D (Agent SDK harness) with the §5.1 pipeline.
- Dogfood on your own daily sessions for 2–4 weeks; log every eviction + tombstone.
- Failure logging: every time the model asks about something that was evicted, or regenerates
  an explanation inconsistent with the original, record it. This is the honest error rate.
- Then decide: open-source release (npm/pip proxy), arXiv note, blog post, or PR/comment on
  the Claude Code feature requests (#7821, #64371 — validated demand for selective removal).

---

## 10. Metrics (report all, always)

- **Tokens:** raw input tokens per turn; cumulative session tokens; % evicted.
- **Cost:** cache-adjusted $ per session (the only number that survives §6.4 scrutiny).
- **Longevity:** turns until first forced compaction (FULL vs EVICTED).
- **Quality:** task success rate; decision consistency; evicted-content miss rate
  (how often the model needed something that was deleted).
- **Classifier:** precision/recall of COMPREHENSION labeling vs human labels
  (precision matters most — a false positive deletes something needed).

## 11. Honest Risk Assessment

- **Sherlocking:** Anthropic/OpenAI are actively shipping context management; intent-eviction
  could be absorbed into products within months. Defense: the *measurement + evidence* is
  durable even if the mechanism gets absorbed — publish early.
- **Small effect size:** if comprehension turns are <10% of tokens in pro sessions, the pro
  audience won't care. Defense: the vibe-coder / learning-session segment likely runs much
  higher — segment the measurement.
- **Classifier false positives:** deleting a needed turn is worse than keeping a useless one.
  Defense: precision-first thresholds; tombstones make errors recoverable (model can ask or
  regenerate).
- **Cache economics:** any per-turn context rewriting can cost more than it saves.
  Defense: batch-with-compaction discipline + always report cache-adjusted cost.

## 12. Positioning (how to talk about it)

- Don't pitch: "vector memory / RAG for chat history" (crowded, will be dismissed).
- Do pitch: **"Intent-based eviction: coding agents waste N% of context on explanations the
  model can regenerate at any time. We measured it, deleted it, and nothing broke."**
- One-line novelty claim: *first system to classify agent-session turns by speech-act intent
  (action / decision / comprehension) and evict on regenerability rather than size, age, or
  similarity.*

## 13. Immediate Next Steps (this week)

1. [ ] Locate transcripts: `ls ~/.claude/projects/` — confirm JSONL sessions exist.
2. [ ] Write the parser: JSONL → list of exchanges with roles, tool_use flags, token usage.
3. [ ] Implement heuristic labeler (§4 signals) + token counter per label.
4. [ ] Run on 10 of your own sessions → first % evictable number.
5. [ ] Decide go/no-go against §7 thresholds.

---

## 14. Adversarial Review (challenge round — read before starting)

Five attacks the idea must survive, with honest odds:

1. **Tokens aren't where you think.** In coding sessions, tool outputs typically eat 70–90%
   of context; explanations may be 30% of *turns* but only 5–8% of *tokens*. This is the most
   likely kill — and it's exactly what Phase 1 measures. Do not build before measuring.
2. **Compaction already eats explanations for free.** Auto-compact summarizes them away anyway;
   the marginal benefit is only the window before compaction fires. Users' real complaint is
   losing *decisions*, not explanations — this idea doesn't touch that pain.
3. **Dollar savings ≈ zero.** Old explanation turns sit in cached prefix at ~10% rate; deleting
   20% of cheap tokens saves ~2% of cost, and each eviction rewrite costs a cache miss.
   The honest pitch is **headroom and longevity**, not money.
4. **Explanations may be load-bearing.** They record shared vocabulary; deleting risks
   inconsistency ("as you explained earlier"). Tombstones mitigate; proving "nothing broke"
   is proving a negative and needs many replayed sessions.
5. **Audience mismatch + zero moat.** Heavy explainers (beginners) don't care about tokens;
   token-carers (pros) rarely ask for explanations. And Anthropic's context-editing can absorb
   the mechanism as a one-line policy. The only durable asset is being first with the evidence.

**Surviving version of the claim:** per *Less Context, Better Agents*, stale context *degrades*
models — so aim for "evicting explanation turns makes later work equal-or-BETTER, with longer
sessions as a bonus," not "saves money." Estimated odds Phase 1 clears the bar in coding
sessions: ~30–40% (higher in learning-style sessions). The measurement is cheap and settles
attacks 1–2 with data — run it first.

## 15. Phase 1a Measurement Script (ready to run)

The script `measure_explanation_turns.py` (shipped alongside this doc) implements §7 steps 1–2:

```
python3 measure_explanation_turns.py                       # scan all ~/.claude/projects
python3 measure_explanation_turns.py <project-dir-or-.jsonl>
```

What it does: parses Claude Code JSONL transcripts → groups events into exchanges (user prompt
+ assistant activity until next prompt) → labels each exchange (ACTION / RESEARCH /
COMPREHENSION / DECISION / OTHER) using the §4 heuristics → reports estimated token share per
label, per session and overall, with the go/no-go verdict line.

Caveats (by design, Phase 1a): heuristic-only labels, chars/4 token estimation for persistent
contribution, no retrospective reference-check yet — so it reports an **upper bound** on the
evictable share. If even the upper bound is <10%, stop (attack #1 confirmed). If it clears
20%, proceed to Phase 1b: LLM labeling pass + retrospective filter (§7 steps 3–4), then the
replay ablation (§8).

Full script source (for reference):

```python
# see measure_explanation_turns.py — key logic:

MUTATING_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Bash", "TodoWrite"}
READONLY_TOOLS = {"Read", "Grep", "Glob", "WebSearch", "WebFetch", "LS", "Task", "Agent"}

EXPLAIN_PATTERNS = r"explain|plain english|in short|eli5|what does...mean|why is/did|" \
                   r"summarize|walk me through|help me understand|conclusion|clarify"
DECISION_PATTERNS = r"let's use|we should|go with|instead of|don't use|never|always|" \
                    r"prefer|from now on|decided|use option"

# label(exchange):
#   any mutating tool call        -> ACTION
#   only read-only tool calls     -> RESEARCH
#   decision language, no tools   -> DECISION   (never evict)
#   explain-pattern prompt, or long prose reply with no tools/code -> COMPREHENSION (evictable)
#   else                          -> OTHER
#
# token share = chars/4 of each exchange's stored content (its permanent
# contribution to the context window), cross-checked against usage.output_tokens
```

## 16. References

- Less Context, Better Agents: Efficient Context Engineering for Long-Horizon Tool-Using LLM
  Agents — https://arxiv.org/abs/2606.10209
- ActiveContext: Escaping the Context Bottleneck via RL Context Curation —
  https://arxiv.org/html/2604.11462v1
- ACON: Optimizing Context Compression — https://openreview.net/pdf?id=7JbSwX6bNL
- Memory for Autonomous LLM Agents: survey — https://arxiv.org/html/2603.07670v1
- Anthropic context editing — https://platform.claude.com/docs/en/build-with-claude/context-editing
- Anthropic context management announcement — https://www.anthropic.com/news/context-management
- Claude Code hooks reference (transcript immutability) — https://code.claude.com/docs/en/hooks
- OpenClaw session pruning (cache-TTL-aware) — https://docs.openclaw.ai/concepts/session-pruning
- Claude Code feature requests for selective removal —
  https://github.com/anthropics/claude-code/issues/7821 ,
  https://github.com/anthropics/claude-code/issues/64371
- Why /compact loses useful context — https://faafospecialist.substack.com/p/claude-code-figured-out-why-compact
- Awesome agent papers (2026) — https://github.com/VoltAgent/awesome-ai-agent-papers
