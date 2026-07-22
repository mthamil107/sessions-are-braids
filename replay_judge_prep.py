#!/usr/bin/env python3
"""
Build blinded judge inputs for the Phase 2 replay ablation.

For each replay item with both answers present, writes
validation/replay/judge_in/<sid>__r<idx>.md containing:
  - the historical actual response
  - Response A and Response B (FULL/SCOPED shuffled per item)
and records the assignment in validation/replay/judge_key.json (local only).
"""

import json, os, random

random.seed(7)


def main():
    items = json.load(open("validation/replay/manifest.json"))
    os.makedirs("validation/replay/judge_in", exist_ok=True)
    key, built = {}, 0
    for it in items:
        base = it["base"]
        name = os.path.basename(base)
        paths = {v: f"{base}__ans_{v}.md" for v in ("full", "scoped")}
        if not all(os.path.exists(p) for p in paths.values()):
            print(f"MISSING answers for {name} - skipped")
            continue
        actual = open(f"{base}__actual.md", encoding="utf-8").read()
        nxt = open(f"{base}__full.md", encoding="utf-8").read().split("# NEXT USER PROMPT")[-1].strip()
        order = ["full", "scoped"]
        random.shuffle(order)
        key[name] = {"A": order[0], "B": order[1]}
        a = open(paths[order[0]], encoding="utf-8").read()
        b = open(paths[order[1]], encoding="utf-8").read()
        open(f"validation/replay/judge_in/{name}.md", "w", encoding="utf-8").write(
            f"# The user's prompt at this point\n\n{nxt[:900]}\n\n"
            f"# What the assistant actually did (historical ground truth)\n\n{actual}\n\n"
            f"# Response A\n\n{a}\n\n# Response B\n\n{b}\n")
        built += 1
    json.dump(key, open("validation/replay/judge_key.json", "w"), indent=1)
    print(f"built {built} judge inputs")


if __name__ == "__main__":
    main()
