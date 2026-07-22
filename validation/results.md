# Validation results (Phases 1a-corrected, 1b, and 2 pilot)

All numbers computed from the author's own Claude Code transcripts. Raw prompt text is
kept local (never published); this file contains aggregates only.

## Corpus artifact fix (uuid dedupe)

Forked/resumed sessions re-log inherited history with duplicate event uuids. Both parsers
now dedupe by uuid (keep first). Effect on Phase 1a aggregates was minor — the structure
was real, not an artifact:

| Metric (Phase 1a, all substantive sessions) | Pre-dedupe | Post-dedupe |
|---|--:|--:|
| COMPREHENSION token share (intent measurement) | 2.3% | 2.3% |
| Crossload, default θ=0.15 (mean / token-weighted) | 51.1% / 44.1% | 51.3% / 44.9% |
| Crossload, conservative θ=0.07 (mean / token-weighted) | 34.5% / 23.2% | 34.5% / 24.7% |
| Sessions interleaved (default θ) | 93% | 93% (63/68) |

## Phase 1b — blind LLM boundary validation (10 sessions, 30 passes, 3 lenses)

Per-session detail (pre-dedupe indexing; heuristic vs mean of 3 blind LLM passes):

| session | prompts | H threads | LLM threads | H crossload | LLM crossload | H switch prec | H switch rec |
|---|--:|--:|--:|--:|--:|--:|--:|
| 01ecd0bb | 14 | 4 | 3.3 | 39% | 48% | 40% | 50% |
| 0aebc07d | 10 | 2 | 2.0 | 31% | 29% | 0% | 0% |
| 0cd7c167 | 5 | 2 | 3.0 | 40% | 71% | 100% | 100% |
| 3ae329ac | 18 | 5 | 3.0 | 33% | 57% | 0% | 0% |
| 5315bab9 | 45 | 5 | 4.0 | 22% | 61% | 0% | 0% |
| 5f2a7b4f | 281 | 7 | 4.0 | 11% | 55% | 9% | 18% |
| 91555dee | 31 | 3 | 3.3 | 17% | 72% | 20% | 25% |
| c3e4e981 | 24 | 11 | 2.3 | 74% | 20% | 21% | 100% |
| ecb0b637 | 301 | 23 | 23.0 | 34% | 91% | 59% | 48% |
| fb3c9575 | 337 | 12 | 8.3 | 43% | 77% | 11% | 29% |

Pooled findings:

- Heuristic switch-point agreement with 2-of-3 LLM consensus (±1 prompt):
  **precision 29% (over-split 71%), recall 39% (missed 61%)** → the lexical heuristic is
  not viable as a router; per the pre-registered gate this arm FAILS (<30% over-split
  required), mandating an LLM-based router.
- Two-judge adjudication of 40 sampled disagreements (85% judge agreement):
  **LLM consensus correct 30, heuristic correct 4, unclear 6.** By direction: of 26
  heuristic-claimed switches the LLM rejected, judges upheld the LLM 25 (1 unclear, 0 for
  the heuristic); of 14 LLM-claimed switches the heuristic missed, judges upheld the LLM 5,
  the heuristic 4, unclear 5 — i.e. the LLM's *extra* switches were upheld only about half
  the time when decidable.
- **Validated crossload (LLM segmentations, uuid-deduped): mean 57.3%, token-weighted
  63.2%** across the 10-session sample. Excluding the one low-agreement session
  (ecb0…, inter-pass thread counts 14/22/33), mean is 53.7%.
  Cross-dependency (xref) rate: ~5% of prompts.
- Interleaving under all three passes: 7/10 sessions (all sessions ≥18 prompts
  interleave except one).

## Phase 2 pilot — replay ablation at RETURN points (18 points, 6 sessions)

Setup: at each LLM-labeled RETURN point, the next real prompt was replayed against two
context variants — FULL (linear history) vs SCOPED (own-thread history + one-line stubs
for other threads; deliberately the weakest condenser, so results are a floor). Blinded
single-judge comparison against the historical actual response.

| Metric | FULL | SCOPED |
|---|--:|--:|
| Context size (total over items) | 906 KB | 453 KB (**−50.0%**) |
| Equivalent to actual (same+similar) | 12/18 | 10/18 |
| Dependency failures | 11/18 | 12/18 |
| Judge preference | **11** | 5 (2 ties) |

Reading: naive scoping halves context at a modest quality cost (preference 11–5 toward
FULL; dependency-failure delta only +1). The strong hypothesis (scoped ≥ full) is NOT
supported at this pilot's power (n=18, one judge, excerpt-based replay harness that
handicaps both arms). The gap is attributable mostly to condensation quality, not to
thread isolation itself — making the condenser the demonstrated open problem.

## Provenance

- Segmentation passes: 30 independent blind runs (3 prompt-lens variants × 10 sessions),
  Sonnet-class labelers; schema-validated.
- Adjudication: 2 independent judges × 4 batches × 10 sampled disagreements.
- Replay: 36 replays (18 points × 2 variants) + 18 blinded comparison judges.
- Scripts: `measure.py`, `measure_tree.py`, `validate_boundaries.py`, `replay_build.py`,
  `replay_judge_prep.py`.
