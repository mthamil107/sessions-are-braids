#!/usr/bin/env python3
"""
Phase 1b scoring: compare heuristic thread boundaries (measure_tree.py) against
3 independent blind LLM segmentation passes per session.

Reads:  validation/sample/<sid>.json   (heuristic labels + token counts)
        validation/passes/<sid>__p{1,2,3}.json  (blind LLM labels)
Writes: validation/results.md, validation/disagreements.md
"""

import json, glob, os, sys
from collections import defaultdict

TOL = 1  # switch-point matching tolerance (prompts)

def switches(kinds):
    return {i for i, k in enumerate(kinds) if i > 0 and k in ("NEW", "RETURN")}

def interleaved(threads):
    seen_after = set()
    last = threads[0]
    revisits = 0
    visited = {last}
    for t in threads[1:]:
        if t != last:
            if t in visited:
                revisits += 1
            visited.add(t)
            last = t
    return revisits

def crossload(threads, tokens):
    prior_by, prior_tot, shares = defaultdict(int), 0, []
    for t, tok in zip(threads, tokens):
        if prior_tot:
            shares.append((prior_tot - prior_by[t]) / prior_tot)
        prior_by[t] += tok
        prior_tot += tok
    return sum(shares) / len(shares) if shares else 0.0

def near(i, pts, tol=TOL):
    return any(abs(i - j) <= tol for j in pts)

def consensus_switches(pass_switch_sets):
    cand = set().union(*pass_switch_sets)
    cons = {i for i in cand
            if sum(1 for s in pass_switch_sets if near(i, s)) >= 2}
    # merge adjacent consensus indices into single points
    merged, last = [], None
    for i in sorted(cons):
        if last is None or i - last > TOL:
            merged.append(i)
        last = i
    return set(merged)

def main():
    rows, pooled = [], defaultdict(list)
    dis_lines = ["# Disagreement worksheet (heuristic vs LLM consensus)",
                 "", "Tick the correct call for each. H=heuristic, C=LLM consensus.", ""]
    for sp in sorted(glob.glob("validation/sample/*.json")):
        if sp.endswith("manifest.json"):
            continue
        d = json.load(open(sp, encoding="utf-8"))
        sid = d["session"]
        toks = [p["tokens"] for p in d["prompts"]]
        h_threads = [p["thread"] for p in d["prompts"]]
        h_kinds = [p["kind"] for p in d["prompts"]]
        passes = []
        for k in (1, 2, 3):
            pp = f"validation/passes/{sid}__p{k}.json"
            if not os.path.exists(pp):
                continue
            try:
                pd = json.load(open(pp, encoding="utf-8"))
                labels = sorted(pd["labels"], key=lambda x: x["i"])
                if len(labels) != len(toks):
                    print(f"WARN {sid} p{k}: {len(labels)} labels vs {len(toks)} prompts - skipped")
                    continue
                passes.append(labels)
            except Exception as e:
                print(f"WARN {sid} p{k}: {e} - skipped")
        if len(passes) < 2:
            print(f"SKIP {sid}: <2 valid passes")
            continue

        h_sw = switches(h_kinds)
        p_sw = [switches([l["kind"] for l in ls]) for ls in passes]
        cons = consensus_switches(p_sw)

        matched_h = {i for i in h_sw if near(i, cons)}
        matched_c = {i for i in cons if near(i, h_sw)}
        prec = len(matched_h) / len(h_sw) if h_sw else 1.0
        rec = len(matched_c) / len(cons) if cons else 1.0

        p_threadseqs = [[l["thread"] for l in ls] for ls in passes]
        p_loads = [crossload(ts, toks) for ts in p_threadseqs]
        p_revisits = [interleaved(ts) for ts in p_threadseqs]
        p_nthreads = [len(set(ts)) for ts in p_threadseqs]
        xrefs = [sum(1 for l in ls if l.get("xref") is not None) / len(ls) for ls in passes]

        rows.append({
            "sid": sid[:8], "n": len(toks), "h_threads": len(set(h_threads)),
            "llm_threads": sum(p_nthreads) / len(p_nthreads),
            "h_load": crossload(h_threads, toks),
            "llm_load": sum(p_loads) / len(p_loads),
            "prec": prec, "rec": rec,
            "revisits": sum(p_revisits) / len(p_revisits),
            "interleaved": all(r > 0 for r in p_revisits),
            "xref": sum(xrefs) / len(xrefs),
            "tokens": sum(toks),
        })
        pooled["h_sw"].append(len(h_sw)); pooled["cons"].append(len(cons))
        pooled["matched_h"].append(len(matched_h)); pooled["matched_c"].append(len(matched_c))

        # worksheet entries
        for i in sorted(h_sw - matched_h):
            dis_lines += [f"## {sid[:8]} prompt {i} — H says SWITCH, C says continue",
                          f"- [ ] H correct  - [ ] C correct",
                          f"  - prev: {d['prompts'][i-1]['prompt'][:120]!r}",
                          f"  - this: {d['prompts'][i]['prompt'][:120]!r}", ""]
        for i in sorted(cons - matched_c):
            dis_lines += [f"## {sid[:8]} prompt {i} — C says SWITCH, H says continue",
                          f"- [ ] C correct  - [ ] H correct",
                          f"  - prev: {d['prompts'][i-1]['prompt'][:120]!r}",
                          f"  - this: {d['prompts'][i]['prompt'][:120]!r}", ""]

    out = ["# Phase 1b results", "",
           "| session | prompts | H threads | LLM threads | H crossload | LLM crossload | H switch prec | H switch rec | LLM revisits | interleaved | xref rate |",
           "|---|--:|--:|--:|--:|--:|--:|--:|--:|:-:|--:|"]
    for r in rows:
        out.append(f"| {r['sid']} | {r['n']} | {r['h_threads']} | {r['llm_threads']:.1f} | "
                   f"{100*r['h_load']:.0f}% | {100*r['llm_load']:.0f}% | {100*r['prec']:.0f}% | "
                   f"{100*r['rec']:.0f}% | {r['revisits']:.1f} | {'Y' if r['interleaved'] else 'N'} | "
                   f"{100*r['xref']:.0f}% |")
    n = len(rows)
    tot_h = sum(pooled["h_sw"]); tot_c = sum(pooled["cons"])
    mprec = sum(pooled["matched_h"]) / tot_h if tot_h else 1
    mrec = sum(pooled["matched_c"]) / tot_c if tot_c else 1
    mean_llm_load = sum(r["llm_load"] for r in rows) / n
    tw_llm_load = sum(r["llm_load"] * r["tokens"] for r in rows) / sum(r["tokens"] for r in rows)
    mean_h_load = sum(r["h_load"] for r in rows) / n
    inter = sum(1 for r in rows if r["interleaved"])
    mean_xref = sum(r["xref"] for r in rows) / n
    out += ["", f"**Pooled ({n} sessions):**", "",
            f"- Heuristic switch precision vs LLM consensus: **{100*mprec:.0f}%** "
            f"(over-split rate {100*(1-mprec):.0f}%)",
            f"- Heuristic switch recall vs LLM consensus: **{100*mrec:.0f}%** "
            f"(missed-switch rate {100*(1-mrec):.0f}%)",
            f"- Validated (LLM) crossload: mean **{100*mean_llm_load:.1f}%**, "
            f"token-weighted **{100*tw_llm_load:.1f}%** (heuristic said {100*mean_h_load:.1f}% mean)",
            f"- Sessions interleaved under ALL LLM passes: **{inter}/{n}**",
            f"- Cross-dependency (xref) rate: **{100*mean_xref:.1f}%** of prompts",
            "",
            f"Gate: validated token-weighted crossload >=15% AND over-split <30% "
            f"-> {'PASS' if tw_llm_load >= 0.15 and (1-mprec) < 0.30 else 'FAIL'}"]
    open("validation/results.md", "w", encoding="utf-8").write("\n".join(out) + "\n")
    open("validation/disagreements.md", "w", encoding="utf-8").write("\n".join(dis_lines) + "\n")
    print("\n".join(out))

if __name__ == "__main__":
    main()
