# Execution Plan: Phase 1b (Boundary Validation) → Phase 2 (Replay Ablation)

**Status:** planned July 22, 2026 · follows `thread-router-research.md` §6–7
**Goal:** turn the heuristic Phase 1a numbers (93% interleaving, 23–44% crossload) into
validated, citable numbers — then answer the make-or-break question: does scoped context
hurt, match, or improve quality at thread returns?

---

## Phase 1b — Boundary Validation (≈2–3 days, near-zero cost)

**Question:** are the lexically-detected threads real, and what is the honest crossload?

### Step 1. Freeze the validation sample
- Add a `--dump` flag to `measure_tree.py`: writes per-session JSON
  (prompt text ≤300 chars, exchange token count, heuristic thread id + CONT/NEW/RETURN label).
- Stratified sample of 10 sessions: 3 small (5–15 prompts), 4 medium (16–50),
  3 large (50+, must include the two largest). Fixed list, committed to `validation/sample/`.

### Step 2. Independent LLM segmentation (3 passes per session)
- A strong-model labeler gets ONLY the prompt sequence (no heuristic labels — blind pass)
  and segments it: thread id per prompt + switch/return marks + a 3–6 word thread title.
- 3 independent passes per session; majority-vote the boundaries (a switch point counts if
  ≥2 passes agree within ±1 prompt).
- Additionally each pass flags **cross-references**: prompts in thread B that need content
  from thread A (this measures the true cross-dependency rate — the discount on savings,
  and the router's hardest cases).

### Step 3. Agreement scoring (`validate_boundaries.py`)
- Switch-point precision/recall of heuristic vs LLM-consensus (±1 prompt tolerance).
- Over-split rate: % of heuristic switches with no LLM-consensus counterpart.
- Missed-switch rate: % of LLM-consensus switches the heuristic missed.
- Thread-mapping by greedy max-overlap; report per-session and pooled.

### Step 4. Hand adjudication (~100 prompts, author)
- Script emits `validation/disagreements.md`: every disagreement with prompt text and both
  labels, as a checklist. Author (who knows the sessions) ticks the correct label.
- Adjudicated labels become ground truth for the disagreement set.

### Step 5. The citable numbers
- Recompute on validated boundaries: interleaving rate, threads/session, crossload
  (mean + token-weighted), and the **cross-dependency rate**.
- Update paper §5 + limitations; release as v0.3.0 (Zenodo picks it up automatically).

**Gate (pre-registered):** validated token-weighted crossload ≥15% AND over-split rate <30%
→ proceed to Phase 2. Expected landing zone: 15–30%.

---

## Phase 2 — Replay Ablation (≈1–2 weeks, needs API budget)

**Question:** at RETURN points — where scoped context omits the intervening thread entirely —
does the model behave the same, worse, or better?

### Step 1. Extract RETURN points
- From the 10 validated sessions, every consensus RETURN point: full prior transcript,
  the next real user prompt, and the actual historical assistant response (the reference).
- Target ≈50–100 return points (add sessions from the 67 if the sample yields fewer).

### Step 2. Context assembler (`assemble_context.py`)
Two variants per return point:
- **FULL:** linear history as today (truncated to model context limit the same way the
  harness would).
- **SCOPED:** per `thread-router-research.md` §4.1 — active thread's history verbatim +
  ancestor path + one-line LLM-generated conclusions of other threads + a mined
  global-decisions ledger. Conclusion/ledger generation is itself LLM-assisted and cached.

### Step 3. Replay
- Claude API (Agent SDK or direct Messages), temperature 0, 3 samples per variant.
- Budget estimate before running: ~100 points × 2 variants × 3 samples; contexts average
  30–80K tokens → rough order $100–300 on Sonnet-class. Confirm budget before launch;
  can pilot on 15 points first (~$30) to check the pipeline and effect direction.

### Step 4. Judging
- **Hard metrics first:** same files edited? same commands run? same tool sequence class?
- **LLM judge panel (3 votes)** only for the soft residue: answer consistency with the
  historical response, decision consistency.
- **Dependency failures** logged explicitly: any case where SCOPED lacked something FULL
  used. This rate decides the router's required precision — it is the paper's key safety
  number.

### Step 5. Report
- Δ action equivalence, Δ consistency, dependency-failure rate, Δ tokens served,
  Δ cache-adjusted cost, projected turns-to-compaction.
- **If quality is flat or better at 20–40% context reduction → lead the paper with that**
  ("linear history is the wrong data structure, measured") and consider arXiv at this point
  — the result is no longer "immature" once the ablation lands.
- If dependency failures are high → the honest result is "scoped context needs a smarter
  condenser"; publish that finding and gate Phase 3 on fixing it.

---

## Phase 3 preview (only if Phase 2 clears)
Router prototype: embeddings + recency vs Haiku-class classifier, measured against the
Phase 1b validated labels (free — labels already exist). Then the proxy + dogfood per
`thread-router-research.md` §8.

## Division of labor
- **Automatable now, no budget:** Phase 1b steps 1–3 and 5 (LLM passes can run as local
  subagent tasks), disagreement worksheet generation.
- **Author required:** Step 4 adjudication (~1 hour), Phase 2 budget go/no-go, and the
  Phase 2 pilot review.

## Risks specific to this plan
- LLM labeler sees only prompts (not replies/tools) — cheaper and less biased, but may
  under-detect switches that are only visible in tool activity; the adjudication step
  catches this, and if missed-switch rate is high, rerun passes with tool-name summaries.
- Adjudicator is also the session author — bias risk; mitigate by adjudicating blind
  (worksheet shows both labels unattributed).
- Replay non-determinism even at temperature 0; hence 3 samples and hard metrics first.
