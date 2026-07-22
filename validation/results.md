# Phase 1b results

| session | prompts | H threads | LLM threads | H crossload | LLM crossload | H switch prec | H switch rec | LLM revisits | interleaved | xref rate |
|---|--:|--:|--:|--:|--:|--:|--:|--:|:-:|--:|
| 01ecd0bb | 14 | 4 | 3.3 | 39% | 48% | 40% | 50% | 0.7 | N | 2% |
| 0aebc07d | 10 | 2 | 2.0 | 31% | 29% | 0% | 0% | 0.0 | N | 0% |
| 0cd7c167 | 5 | 2 | 3.0 | 40% | 71% | 100% | 100% | 0.0 | N | 27% |
| 3ae329ac | 18 | 5 | 3.0 | 33% | 57% | 0% | 0% | 1.3 | Y | 6% |
| 5315bab9 | 45 | 5 | 4.0 | 22% | 61% | 0% | 0% | 1.0 | N | 4% |
| 5f2a7b4f | 281 | 7 | 4.0 | 11% | 55% | 9% | 18% | 10.3 | Y | 0% |
| 91555dee | 31 | 3 | 3.3 | 17% | 72% | 20% | 25% | 3.7 | Y | 8% |
| c3e4e981 | 24 | 11 | 2.3 | 74% | 20% | 21% | 100% | 0.0 | N | 3% |
| ecb0b637 | 301 | 23 | 23.0 | 34% | 91% | 59% | 48% | 53.3 | Y | 1% |
| fb3c9575 | 337 | 12 | 8.3 | 43% | 77% | 11% | 29% | 9.7 | Y | 0% |

**Pooled (10 sessions):**

- Heuristic switch precision vs LLM consensus: **29%** (over-split rate 71%)
- Heuristic switch recall vs LLM consensus: **39%** (missed-switch rate 61%)
- Validated (LLM) crossload: mean **58.1%**, token-weighted **67.5%** (heuristic said 34.4% mean)
- Sessions interleaved under ALL LLM passes: **5/10**
- Cross-dependency (xref) rate: **5.0%** of prompts

Gate: validated token-weighted crossload >=15% AND over-split <30% -> FAIL
