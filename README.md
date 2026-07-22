# Sessions Are Braids

**Measuring latent thread structure in real coding-agent sessions — a measurement note and proposal.**

Thamilvendhan Munirathinam · July 2026

📄 **Paper:** [`paper/sessions-are-braids.pdf`](paper/sessions-are-braids.pdf)

## TL;DR

Coding agents (Claude Code, etc.) store conversation history as a single linear, append-only
context window. On a corpus of the author's own real Claude Code sessions (67 substantive
sessions, 5,182 user prompts, ≈20M estimated stored-context tokens), this note measures what
that window is actually made of:

1. **Negative result — by intent:** pure-comprehension turns ("explain this", "why?") are only
   **2.3%** of stored tokens (median session 1.6%). Intent-based *eviction* of explanation
   turns is not worth building for professional sessions. 84.3% of context is action exchanges
   (edits, commands, tool outputs).
2. **Positive result — by topic:** sessions are braids. **93%** of sessions interleave
   topically distinct threads (invariant to segmentation strictness), and at each prompt
   **23–44%** of the accumulated context belongs to *other* threads ("crossload").

This quantifies, on real usage data, the "logical context poisoning" formalized by the
Conversation Tree Architecture ([arXiv:2603.21278](https://arxiv.org/abs/2603.21278)), and
motivates exactly the two components that work leaves open: **automatic thread placement**
and **condensation on merge-back**. The note proposes an intent router implementing both and
a replay-ablation evaluation design.

## Repository contents

| Path | What it is |
|---|---|
| `paper/sessions-are-braids.pdf` | The measurement note (also `.html` source) |
| `measure.py` | Measurement 1: intent labeling (ACTION / RESEARCH / DECISION / COMPREHENSION) and token share per label |
| `measure_tree.py` | Measurement 2: thread segmentation (CONT / NEW / RETURN), interleaving, and cross-topic context load |
| `results/` | Raw per-session outputs behind the paper's tables (session UUIDs only, no content) |
| `explanation-turn-eviction-research.md` | The original research plan for Measurement 1, including the pre-registered go/no-go gate and adversarial review |

## Reproduce on your own sessions

Both scripts read Claude Code's local JSONL transcripts (`~/.claude/projects/`) — no
instrumentation, no API calls, nothing leaves your machine.

```bash
# Measurement 1: what share of your context is explanation turns?
python3 measure.py

# Measurement 2: how braided are your sessions?
python3 measure_tree.py                     # summary across all sessions
python3 measure_tree.py --show path/to/session.jsonl   # inspect one session's threads
SIM_TH=0.07 python3 measure_tree.py         # conservative (generous-merge) threshold
```

Contributions of numbers from other users' corpora are welcome — the biggest limitation of
this note is that it is a single-user corpus (see §7 of the paper).

## Caveats (read before quoting numbers)

- Single professional user's sessions; a feasibility signal, not a population estimate.
- Thread segmentation is lexical/heuristic; crossload is an **upper bound** on addressable
  savings.
- Token accounting is chars/4 estimation of stored content, cross-checked against native
  usage fields.

## Citation

```bibtex
@misc{munirathinam2026braids,
  author = {Munirathinam, Thamilvendhan},
  title  = {Sessions Are Braids: Measuring Latent Thread Structure in Real Coding-Agent Sessions},
  year   = {2026},
  month  = {July},
  url    = {https://github.com/mthamil107/sessions-are-braids}
}
```

## License

Code and paper are released under the [MIT License](LICENSE).
