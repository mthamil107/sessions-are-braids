# The Thread Router: Automatic Conversation-Tree Placement for Coding Agents

**Working title:** "Sessions Are Braids: Automatic Thread Routing and Scoped Context for
Long-Running Agent Sessions"
**Author:** Thamilvendhan M
**Status:** Phase 1a PASSED (go). Next: Phase 1b (boundary validation) → Phase 2 (replay ablation)
**Date:** July 2026
**Prior work by same author:** explanation-turn eviction (idea #1) — killed by measurement
(2.3% token share); methodology reused here.

---

## 1. The Idea in One Paragraph

Users of coding agents work on multiple interleaved threads inside one linear session: they
start task A, detour into a question, jump to task B, return to A. The session transcript is a
**braid pretending to be a line**. Every prompt therefore drags along context belonging to
*other* threads — measured at 23–44% of accumulated context (see §3). The proposal: an
**automatic thread router** that classifies each incoming prompt as (a) continuation of the
current thread, (b) a new child branch, (c) a return to an earlier thread, or (d) ambiguous —
in which case it lists the 2–3 most likely tree positions for the user to pick. Each prompt is
then served with **scoped context**: its own thread's history + ancestor path + condensed
summaries of sibling threads + global decisions. Completed threads collapse to one-line
conclusions. Result: sessions that stay lean indefinitely without the user managing anything.

---

## 2. Prior Art and the Exact Gap (verified July 2026)

**Already exists — do not rebuild:**
- **Claude Code `/branch`** (shipped ~April 2026): manual git-style session forking;
  branches shown as a tree in the session picker. Copy-and-diverge only — **no merge, no
  summaries, no automation**.
- **Community spec** for full fork/merge/tree-navigation: Claude Code issue #32631
  (open feature request — signals Anthropic may build manual tree management).
- **Tree-chat UIs:** Loom, GitChat, forky, LangChain branching chat — manual trees, mostly
  for exploring alternative model responses, not for scoping work threads.
- **Subagents:** already run a sub-task in isolated context and return only the conclusion —
  but agent-initiated, invisible to the user's own prompt stream.
- **Conversation Tree Architecture (CTA)** — arXiv 2603.21278 (Mar 2026): formalizes exactly
  this model (tree of topic nodes; context = ancestor path; upstream merge of conclusions;
  names the disease "logical context poisoning"). **Their prototype is manual; their open
  problems list is this project's contribution list:**
  1. automatic placement of prompts into the tree,
  2. selective/condensed context transfer (they only support all-or-nothing),
  3. merge-back condensation and insertion position,
  4. empirical validation (they have none yet).

**The gap this work owns:** the *router* (automatic intent-based placement), the *collapse*
(auto-condensation of finished threads), and the *evidence* (ablation numbers nobody has).

**Why manual branching can't solve it (data-backed):** users don't branch-and-return once;
they weave — avg ~14 thread-returns per session (§3). No one will hand-manage that tree.
Automation is not a convenience; it is the only viable form of the feature.

---

## 3. Phase 1a Results (COMPLETE — the go decision)

Measured on author's real Claude Code history: 67 substantive sessions, 5,182 real user
prompts (harness noise filtered), lexical segmentation via `measure_tree.py`.

| Metric | Default threshold | Conservative (generous merging) |
|---|---|---|
| Prompts that switch or return to a topic | 31% | 18% |
| Sessions with interleaved topics (A→B→A) | **93%** | **93%** |
| Avg topical threads per session | 11.1 | 6.1 |
| Cross-topic context load (mean / token-weighted) | 51% / 44% | 35% / 23% |

Interpretation:
- **Crossload 23–44%** = share of context each prompt carries that belongs to other threads.
  This is the addressable waste — 10–20× larger than idea #1's target (2.3%).
- **93% interleaving, identical at both thresholds** → structural fact, not segmentation noise.
  Qualitative spot-check confirmed clean thread separation and correct RETURN detection.
- Gate (≥25% crossload and interleaving common): **cleared**.

Caveats carried forward: crossload is an upper bound (global decisions must survive across
threads); lexical segmentation may over-split (11 threads/session is suspicious — validate);
router errors are *worse* than pruning errors (hiding needed context vs carrying extra).

---

## 4. System Design

### 4.1 The tree model

- **Node** = a thread: a contiguous-in-intent series of exchanges on one piece of work.
- **Context served for a prompt in node N** =
  `system + global memory (CLAUDE.md etc.)`
  `+ GLOBAL DECISIONS ledger (see 4.4)`
  `+ ancestor path of N (root → N), verbatim`
  `+ one-line conclusions of N's closed children and closed siblings`
  `+ N's own history, verbatim`
- Sibling threads' full content is NEVER served — that's the saving.

### 4.2 The router (the core contribution)

For each incoming prompt, classify against the live tree:

| Verdict | Meaning | Action |
|---|---|---|
| CONTINUE | same thread as last exchange | append to current node |
| BRANCH | new sub-task under current work | create child node |
| RETURN(X) | resumes earlier thread X | switch active node to X |
| NEW-ROOT | unrelated new work | create sibling of root-level threads |
| AMBIGUOUS | confidence below threshold | **show the user 2–3 candidate positions to pick** |

Design rules:
- Router input: the prompt + a compact "tree card" (one line per open thread: title, last
  activity, files touched). Never the full transcript — the router must stay cheap.
- Implementation ladder: (1) embedding similarity vs thread centroids + recency prior →
  (2) small LLM (Haiku-class) with the tree card → (3) fine-tuned/RL later if warranted.
- **Precision-first:** when unsure, prefer CONTINUE (safe default — matches today's
  behavior) or ask. A wrong BRANCH/RETURN hides needed context; a wrong CONTINUE merely
  keeps baggage. Asymmetric loss must be built into thresholds.
- The AMBIGUOUS fallback is a feature, not a failure: it is the user's original
  "list the options in the hierarchy to choose" — and doubles as labeled training data.

### 4.3 Thread lifecycle

- **Open** → normal serving.
- **Dormant** (no activity for k prompts): full content retained but only served on RETURN.
- **Closed** (task done — detected by commit/tests-pass/user says done, or user command):
  collapse to a conclusion line: outcome + artifacts (files, commits) + decisions made.
  Full content archived on disk, re-expandable on demand (regenerability principle from
  idea #1 survives here).

### 4.4 What must cross threads (the crossload discount)

A GLOBAL DECISIONS ledger — mined continuously, served to every thread:
- constraints and preferences ("never touch auth", "target py3.11")
- architecture decisions
- environment facts (versions, paths, credentials layout)
This is why realized savings < measured crossload. Idea #1's decision-mining design is
reused verbatim for the miner.

### 4.5 Cache interaction (lesson from idea #1)

- Per-thread context = stable prefix while a thread is active → thread switches are the only
  cache-miss events. With ~14 switches/session, cache misses are bounded and predictable —
  far better than per-turn dynamic retrieval.
- Batch tree mutations (collapse, re-scope) at switch moments, which are cache breaks anyway.
- Report **cache-adjusted cost**, never raw tokens alone.

### 4.6 Implementation homes

| Option | Notes |
|---|---|
| A. Offline experiments (Phases 1b–2) | No product needed. Transcript replay via API/Agent SDK. |
| B. API proxy (`ANTHROPIC_BASE_URL`) | True context control per request; router runs in proxy; works with today's Claude Code. |
| C. Agent SDK harness | Full control incl. UI for AMBIGUOUS prompts; best for the paper. |
| D. Claude Code plugin | Cannot rewrite context (transcript immutable to plugins) — at most a UX layer (`/thread` suggestions) on top of manual /branch. Weakest option. |

**Recommended: A now → B for dogfooding → paper from A+B evidence.**

---

## 5. Failure Modes (adversarial review) and Mitigations

1. **Router mis-routes → model loses needed context.** The dominant risk; worse than any
   pruning error. → Precision-first thresholds, CONTINUE as safe default, AMBIGUOUS
   fallback, and the ablation in §7 measures exactly this before anything ships.
2. **Hidden cross-thread dependencies.** Thread B silently depends on a fact from thread A
   (a function A renamed, a port A changed). → Global-decisions ledger + "files touched"
   overlap check: if two threads touch the same file, serve each other's conclusions
   automatically; run the staleness check on RETURN (re-read touched files — Codex-style
   post-compact recovery).
3. **Over-splitting.** Segmenter/router creates threads for every stray sentence; tree becomes
   noise; constant switches destroy the cache advantage. → Minimum-thread-size rule; merge
   heuristic (threads that keep co-referencing each other get merged); measure switch-rate as
   a health metric.
4. **User confusion / trust.** Invisible context scoping means the model "forgot" things from
   the user's point of view. → Always-visible thread indicator; a `/tree` view; one-keystroke
   "serve full context for this prompt" escape hatch.
5. **Sherlocking.** Anthropic shipped /branch and holds spec #32631; they can absorb the
   router. → The durable asset is the evidence (93% interleaving; ablation numbers) and being
   first — publish early, build only what the experiments need. (Accepted risk; same posture
   as idea #1.)
6. **Evaluation validity.** Replay-based evaluation with LLM judges is noisy. → 3-vote judging,
   human spot-checks, and prefer hard metrics where possible (same files edited? same commands
   run? tests pass?).

---

## 6. Phase 1b — Boundary Validation (next step, days)

**Question:** are the lexically-detected threads real, and what is the honest crossload?

1. Sample 10 sessions across the size distribution (incl. the largest).
2. LLM pass (strong model): given the full prompt sequence, segment into threads and mark
   switch/return points. Compare with `measure_tree.py` labels: agreement rate,
   over-split rate, missed-switch rate.
3. Hand-adjudicate disagreements on ~100 prompts (cheap; author knows own sessions).
4. Recompute crossload on validated boundaries → the citable number.
5. Also extract: how often a prompt in thread B *actually references* content from thread A
   (true cross-dependency rate — feeds mitigation #2 and discounts the savings estimate).

**Gate:** validated crossload ≥15% and over-split rate manageable (<30% of detected switches
are spurious) → proceed. Expected landing zone: 15–30%.

## 7. Phase 2 — Replay Ablation (the make-or-break experiment)

**Question:** does scoped context preserve (or improve) answer quality at thread returns?

1. From validated sessions, take every RETURN point (user comes back to thread A after
   working in B). These are the danger points — scoped context omits B entirely.
2. For each, build two contexts: FULL (linear history, as today) vs SCOPED (§4.1 assembly,
   with conclusions + decision ledger standing in for other threads).
3. Replay the actual next prompt against both (API/Agent SDK; temperature 0; 3 samples).
4. Judge: action equivalence (same edits/commands), answer consistency, and specifically
   **dependency failures** — cases where SCOPED lacked something FULL used.
5. Report: quality delta, token delta, cache-adjusted cost delta, and the dependency-failure
   rate (this number decides the router's required precision).

**Success:** quality within noise (or better — per Less Context, Better Agents, removing
cross-thread noise may *improve* results) at 20–40% context reduction.
**Bonus experiment:** if quality *improves*, lead the paper with that, not the savings.

## 8. Phase 3 — Router Prototype and Dogfood

1. Implement ladder step 1 (embeddings + recency) offline; measure routing accuracy against
   Phase 1b's validated labels (this costs nothing — the labels already exist).
2. If accuracy <90% on CONTINUE/RETURN, escalate to Haiku-class LLM router; re-measure.
3. Build option B (proxy); dogfood 2–4 weeks; log every routing decision + every escape-hatch
   use (each escape = a routing failure worth studying).
4. Ship/publish per §10.

## 9. Metrics (report all, always)

- **Routing:** accuracy per verdict class; AMBIGUOUS rate; escape-hatch rate in dogfood.
- **Context:** tokens served per prompt vs linear baseline; crossload removed.
- **Cost:** cache-adjusted $ per session (switch-rate × miss cost included).
- **Quality:** replay equivalence; dependency-failure rate; task success in dogfood.
- **Longevity:** prompts until forced compaction, scoped vs linear.

## 10. Outputs (in order of durability)

1. **The finding (publish regardless of product):** "93% of real agent sessions interleave
   multiple threads; prompts carry 23–44% cross-thread context" — first measurement of its
   kind; directly answers CTA paper's call for empirical validation. Short paper / arXiv note.
2. **The ablation result** (Phase 2): scoped context at returns — quality vs savings numbers.
3. **The router** as open-source proxy for Claude Code power users.
4. Commentary/PR on issue #32631 with the data — visibility either way.

## 11. Immediate Next Steps

1. [ ] Freeze `measure_tree.py` outputs for the 10-session validation sample.
2. [ ] Write the Phase 1b LLM segmentation prompt + agreement scorer.
3. [ ] Hand-adjudicate the disagreement sample; recompute crossload.
4. [ ] Extract RETURN points for Phase 2; write the replay harness (Agent SDK).
5. [ ] Decide go/no-go for router build on §6–7 gates.

## 12. References

- Conversation Tree Architecture — https://arxiv.org/abs/2603.21278
- Claude Code /branch — https://webdeveloper.com/news/claude-code-branch-session-forking/
- Claude Code branching spec (feature request) — https://github.com/anthropics/claude-code/issues/32631
- Less Context, Better Agents — https://arxiv.org/abs/2606.10209
- ActiveContext (RL context curation) — https://arxiv.org/html/2604.11462v1
- Subagents guide — https://www.tembo.io/blog/claude-code-subagents
- GitChat — https://github.com/DrustZ/GitChat ; forky — https://github.com/ishandhanani/forky
- LangChain branching chat — https://docs.langchain.com/oss/python/langchain/frontend/branching-chat
- Prior negative result (idea #1, explanation-turn eviction) — author's
  `explanation-turn-eviction-research.md` + measurement scripts
