#!/usr/bin/env python3
"""
Phase 2b (three-arm) prep for the SUMMARY+ENTITIES arm.

Modes:
  python replay_entities_prep.py others    -> per replay item, write __others.md:
        compact rendering of the OTHER threads' exchanges (input for entity extraction)
  python replay_entities_prep.py assemble  -> per item, write __scoped_ent.md:
        the existing __scoped.md context + the extracted __ledger.md appended
  python replay_entities_prep.py judge3    -> blinded 3-way judge inputs + key

Arm definitions (same 18 RETURN points as the pilot):
  FULL        = linear history                      (existing __full.md / __ans_full.md)
  SUMMARY     = own thread + one-line stubs          (existing __scoped.md / __ans_scoped.md)
  SUMMARY+ENT = SUMMARY + entity ledger mined from the other threads (__scoped_ent.md)
"""

import json, glob, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from measure_tree import load_exchanges

OTHERS_CHAR_BUDGET = 45000


def load_item_context(sid_full, ref_k, r):
    root = os.path.expanduser("~/.claude/projects")
    labels = sorted(json.load(open(f"validation/passes/{sid_full}__p{ref_k}.json",
                                   encoding="utf-8"))["labels"], key=lambda x: x["i"])
    hits = glob.glob(os.path.join(root, "**", sid_full + ".jsonl"), recursive=True)
    exchanges = load_exchanges(hits[0], dedupe=False)
    seen, dup = set(), []
    for ex in exchanges:
        u = ex.get("uuid")
        d = bool(u) and u in seen
        if u:
            seen.add(u)
        dup.append(d)
    return exchanges, labels, dup


def main():
    mode = sys.argv[1]
    items = json.load(open("validation/replay/manifest.json"))
    sample = json.load(open("validation/sample/manifest.json"))
    sid_map = {m["session"][:8]: m["session"] for m in sample}

    if mode == "others":
        for it in items:
            exchanges, labels, dup = load_item_context(sid_map[it["sid"]], it["ref_pass"], it["r"])
            r, T = it["r"], it["thread"]
            lin = [i for i in range(r) if not dup[i]]
            by_thread = {}
            for i in lin:
                t = labels[i]["thread"]
                if t != T:
                    by_thread.setdefault(t, []).append(i)
            out, budget = [], OTHERS_CHAR_BUDGET
            for t, idxs in sorted(by_thread.items()):
                out.append(f"\n## Thread {t}\n")
                for i in idxs:
                    ex = exchanges[i]
                    block = (f"[{i}] USER: {ex['prompt'][:220]}\n"
                             f"    ASSISTANT ({', '.join(sorted(set(ex['tools']))) or 'no tools'}): "
                             f"{ex['reply'].strip()[:350]}\n")
                    if budget - len(block) > 0:
                        out.append(block)
                        budget -= len(block)
                    else:
                        out.append(f"[{i}] USER (abbrev): {ex['prompt'][:100]}\n")
            open(it["base"] + "__others.md", "w", encoding="utf-8").write(
                "# Exchanges from the OTHER work threads in this session\n" + "".join(out))
        print(f"wrote {len(items)} __others.md files")

    elif mode == "assemble":
        n = 0
        for it in items:
            lp = it["base"] + "__ledger.md"
            if not os.path.exists(lp):
                print(f"MISSING ledger for {it['base']}")
                continue
            scoped = open(it["base"] + "__scoped.md", encoding="utf-8").read()
            ledger = open(lp, encoding="utf-8").read()
            head, _, tail = scoped.partition("# NEXT USER PROMPT")
            open(it["base"] + "__scoped_ent.md", "w", encoding="utf-8").write(
                head + "# Entity ledger mined from the other work in this session\n\n" +
                ledger.strip() + "\n\n# NEXT USER PROMPT" + tail)
            n += 1
        print(f"assembled {n} __scoped_ent.md files")

    elif mode == "judge3":
        random.seed(11)
        os.makedirs("validation/replay/judge3_in", exist_ok=True)
        key, built = {}, 0
        arms = {"full": "__ans_full.md", "summary": "__ans_scoped.md",
                "summary_ent": "__ans_scoped_ent.md"}
        for it in items:
            name = os.path.basename(it["base"])
            paths = {a: it["base"] + s for a, s in arms.items()}
            if not all(os.path.exists(p) for p in paths.values()):
                print(f"MISSING answers for {name} - skipped")
                continue
            actual = open(it["base"] + "__actual.md", encoding="utf-8").read()
            nxt = open(it["base"] + "__full.md", encoding="utf-8").read().split(
                "# NEXT USER PROMPT")[-1].strip()
            order = list(arms)
            random.shuffle(order)
            key[name] = {slot: arm for slot, arm in zip("ABC", order)}
            body = "".join(
                f"\n# Response {slot}\n\n" + open(paths[arm], encoding="utf-8").read()
                for slot, arm in zip("ABC", order))
            open(f"validation/replay/judge3_in/{name}.md", "w", encoding="utf-8").write(
                f"# The user's prompt at this point\n\n{nxt[:900]}\n\n"
                f"# What the assistant actually did (historical ground truth)\n\n{actual}\n"
                + body)
            built += 1
        json.dump(key, open("validation/replay/judge3_key.json", "w"), indent=1)
        print(f"built {built} 3-way judge inputs")


if __name__ == "__main__":
    main()
