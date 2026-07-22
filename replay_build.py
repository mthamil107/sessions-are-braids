#!/usr/bin/env python3
"""
Phase 2 builder: extract RETURN points from validated sessions and construct
FULL vs SCOPED context documents for replay.

Uses measure_tree.load_exchanges(dedupe=False) so exchange indexing matches the
Phase 1b label files exactly; duplicate (forked-history) exchanges are masked
via uuid and excluded from both context variants and from return selection.

For each selected RETURN point r (reference LLM pass labels it RETURN to thread T):
  FULL   = linear history of non-dup exchanges 0..r-1
  SCOPED = non-dup exchanges of thread T only + one-line stubs for other threads
Reference pass per session = median thread count of the three passes.
Session ecb0b637* excluded (inter-pass agreement too low).
"""

import json, glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from measure_tree import load_exchanges

CHAR_BUDGET = 60000
REPLY_EXCERPT = 1200
MAX_PER_SESSION = 5
EXCLUDE = {"ecb0b637-8945-4f0a-9463-9933e001dceb"}


def render(exchanges, idxs):
    lines, budget, rendered = [], CHAR_BUDGET, {}
    for i in reversed(idxs):
        ex = exchanges[i]
        block = (f"### [{i}] USER: {ex['prompt']}\n"
                 f"ASSISTANT ({', '.join(sorted(set(ex['tools']))) or 'no tools'}): "
                 f"{ex['reply'].strip()[:REPLY_EXCERPT]}\n")
        if budget - len(block) > 0:
            rendered[i] = block
            budget -= len(block)
        else:
            rendered[i] = f"### [{i}] USER (older, abbreviated): {ex['prompt'][:150]}\n"
    return "\n".join(rendered[i] for i in sorted(rendered))


def main():
    manifest = json.load(open("validation/sample/manifest.json"))
    root = os.path.expanduser("~/.claude/projects")
    os.makedirs("validation/replay", exist_ok=True)
    out_items = []
    for m in manifest:
        sid = m["session"]
        if sid in EXCLUDE:
            continue
        passes = []
        for k in (1, 2, 3):
            pp = f"validation/passes/{sid}__p{k}.json"
            if os.path.exists(pp):
                pd = json.load(open(pp, encoding="utf-8"))
                labels = sorted(pd["labels"], key=lambda x: x["i"])
                passes.append((k, labels, len({l["thread"] for l in labels}),
                               {t["id"]: t.get("title", "") for t in pd.get("threads", [])}))
        if len(passes) < 2:
            continue
        passes.sort(key=lambda x: x[2])
        ref_k, labels, _, titles = passes[len(passes) // 2]

        hits = glob.glob(os.path.join(root, "**", sid + ".jsonl"), recursive=True)
        exchanges = load_exchanges(hits[0], dedupe=False)
        if len(exchanges) != len(labels):
            print(f"WARN {sid[:8]}: exchanges={len(exchanges)} labels={len(labels)} — skipped")
            continue
        seen, dup = set(), []
        for ex in exchanges:
            u = ex.get("uuid")
            d = bool(u) and u in seen
            if u:
                seen.add(u)
            dup.append(d)

        returns = [l["i"] for l in labels
                   if l["kind"] == "RETURN" and not dup[l["i"]] and l["i"] >= 3]
        step = max(1, len(returns) // MAX_PER_SESSION)
        for r in returns[::step][:MAX_PER_SESSION]:
            T = labels[r]["thread"]
            thread_idxs = [l["i"] for l in labels
                           if l["thread"] == T and l["i"] < r and not dup[l["i"]]]
            lin_idxs = [i for i in range(r) if not dup[i]]
            other_threads = sorted({labels[i]["thread"] for i in lin_idxs
                                    if labels[i]["thread"] != T})
            stubs = "\n".join(
                f"- [thread {t}] {titles.get(t) or 'untitled'}: last activity: "
                f"\"{exchanges[max(i for i in lin_idxs if labels[i]['thread'] == t)]['prompt'][:120]}\""
                for t in other_threads)
            nxt = exchanges[r]["prompt"]
            actual = (exchanges[r]["reply"].strip()[:1500] +
                      "\nTOOLS USED: " + (", ".join(sorted(set(exchanges[r]["tools"]))) or "none"))
            base = f"validation/replay/{sid[:8]}__r{r}"
            open(base + "__full.md", "w", encoding="utf-8").write(
                "# Conversation history (linear)\n\n" + render(exchanges, lin_idxs) +
                f"\n\n# NEXT USER PROMPT\n\n{nxt}\n")
            open(base + "__scoped.md", "w", encoding="utf-8").write(
                "# Conversation history (current work thread only)\n\n" +
                render(exchanges, thread_idxs) +
                "\n\n# Other work in this session (condensed)\n\n" + (stubs or "(none)") +
                f"\n\n# NEXT USER PROMPT\n\n{nxt}\n")
            open(base + "__actual.md", "w", encoding="utf-8").write(
                "# What the assistant actually did at this point (historical)\n\n" + actual + "\n")
            out_items.append({"sid": sid[:8], "r": r, "thread": T, "ref_pass": ref_k,
                              "base": base.replace("\\", "/")})
    json.dump(out_items, open("validation/replay/manifest.json", "w"), indent=1)
    print(f"built {len(out_items)} replay items")
    for it in out_items:
        print(f"  {it['sid']} r={it['r']} thread={it['thread']}")


if __name__ == "__main__":
    main()
