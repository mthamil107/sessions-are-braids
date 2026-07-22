#!/usr/bin/env python3
"""
Phase 1 feasibility for intent-routed conversation trees:
how much tree structure is hiding inside linear Claude Code sessions?

Usage:
    python3 measure_tree.py                          # scan all ~/.claude/projects
    python3 measure_tree.py <dir-or-.jsonl>
    python3 measure_tree.py --show <session.jsonl>   # print one session's segmentation

For each session with >=5 real user prompts, prompts are segmented into topical
threads using lexical similarity (content terms of the prompt + files touched by
tools in that exchange). Each prompt is labelled:

  CONT   - continues the current thread (same branch)
  NEW    - starts a new thread (would be a sibling branch)
  RETURN - resumes an earlier thread after working on something else (A..B..A)
           <- the pattern a manual /branch can't capture and a router can

Headline metrics:
  - branch rate: % of prompts that are NEW or RETURN (how non-linear the session is)
  - interleaved sessions: sessions with >=1 RETURN (linear context provably mixes topics)
  - cross-topic context load: at each prompt, the share of accumulated prior context
    tokens that belong to OTHER threads. Under an ancestor-path-only tree with
    merge-back condensation this is the addressable saving (upper bound: some
    cross-topic content, e.g. global decisions, must survive as summaries).

Heuristic-only (Phase 1a): lexical segmentation is noisy; treat numbers as bounds,
eyeball --show output for sanity, and use an LLM labeling pass for Phase 1b.
"""

import json, os, re, sys, glob
from collections import defaultdict

STOP = set("""a an the and or but if then else for while of to in on at by with without from into over under
is are was were be been being do does did done have has had having can could should would may might must will shall
i you he she it we they me him her us them my your his its our their this that these those there here what which who whom whose
please ok okay yes no not now just also very really some any all each both few more most other such only own same so than too
make making made get getting got use using used want wanted like need needs needed let lets try trying run running new work works working
add added see look looks check checking checked file files code line lines error errors fix fixed fixing issue issues thing things way ways
good right sure think know still dont doesnt didnt cant wont isnt about when where because should tell give come goes going does
create created update updated change changed changes show shows shown said says user users session sessions claude""".split())

CONT_RE = re.compile(
    r"^(ok(ay)?|yes|yeah|yep|no|nope|sure|go|go ahead|do it|continue|proceed|next|"
    r"and |also |then |now |why|how|what|which|hmm+|k|thanks?|ty|great|nice|good|perfect|"
    r"correct|right|wrong|try again|again|retry|fix( it)?|same|more|keep going)\b", re.I)

PATH_KEYS = {"file_path", "path", "notebook_path", "cwd"}
SIM_TH = float(os.environ.get("SIM_TH", "0.15"))

# harness-generated "user" events that carry no user intent
SYNTHETIC_RE = re.compile(
    r"toolu_[A-Za-z0-9]|^\[Request interrupted|^Caveat:|<local-command|"
    r"^<command-name>|task-notification|<task-notification", re.I)

def terms_of(text):
    toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.\-]{2,}", text.lower())
    out = set()
    for t in toks:
        t = t.strip("._-")
        if len(t) >= 3 and t not in STOP:
            out.add(t)
    return out

def walk_paths(obj, acc):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in PATH_KEYS and isinstance(v, str):
                acc.add(os.path.basename(v).lower())
            else:
                walk_paths(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            walk_paths(v, acc)

def est_tokens(s):
    return max(1, len(s) // 4)

def load_exchanges(path, dedupe=True):
    """Group JSONL events into exchanges keyed by real user prompts.

    dedupe: forked/resumed sessions re-log inherited history with the same
    event uuids; skip any event whose uuid was already seen (keep first).
    """
    exchanges, cur, seen = [], None, set()
    with open(path, errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            u = ev.get("uuid")
            if u:
                if dedupe and u in seen:
                    continue
                seen.add(u)
            etype = ev.get("type")
            msg = ev.get("message") or {}
            content = msg.get("content", "")
            # flatten text + collect touched files (+ pure prose and tool names)
            text_parts, files, pure, tnames = [], set(), [], []
            if isinstance(content, str):
                text_parts.append(content)
                pure.append(content)
            elif isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    bt = b.get("type")
                    if bt == "text":
                        text_parts.append(b.get("text", ""))
                        pure.append(b.get("text", ""))
                    elif bt == "tool_use":
                        inp = b.get("input", {})
                        walk_paths(inp, files)
                        tnames.append(b.get("name", "?"))
                        text_parts.append(json.dumps(inp)[:2000])
                    elif bt == "tool_result":
                        c = b.get("content", "")
                        if isinstance(c, list):
                            c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                        text_parts.append(str(c))
            text = "\n".join(text_parts)
            if etype == "user":
                is_real_prompt = not (isinstance(content, list) and any(
                    isinstance(b, dict) and b.get("type") == "tool_result" for b in content))
                if is_real_prompt and SYNTHETIC_RE.search(text[:300]):
                    is_real_prompt = False   # harness event: fold into current exchange
                if is_real_prompt:
                    if cur:
                        exchanges.append(cur)
                    # strip system-reminder / command wrapper noise from prompt terms
                    clean = re.sub(r"<[^>]+>", " ", text)
                    cur = {"prompt": clean.strip()[:400], "terms": terms_of(clean),
                           "files": set(), "tokens": est_tokens(text), "uuid": u,
                           "reply": "", "tools": []}
                    continue
            if cur is None:
                continue
            cur["tokens"] += est_tokens(text)
            cur["files"] |= files
            if etype == "assistant":
                cur["files"] |= files
                cur["reply"] += ("\n" + "\n".join(pure)) if pure else ""
                cur["tools"] += tnames
    if cur:
        exchanges.append(cur)
    return exchanges

def segment(exchanges):
    """Greedy topical threading. Returns per-exchange (seg_id, kind)."""
    segs = []            # {'terms': set, 'files': set, 'tokens': int}
    labels = []
    cur = -1
    for ex in exchanges:
        pt = ex["terms"] | ex["files"]
        short = len(ex["prompt"]) < 25 or CONT_RE.match(ex["prompt"]) and len(pt) <= 6
        if cur >= 0 and (not pt or short):
            sid, kind = cur, "CONT"
        else:
            best, bestsim = -1, 0.0
            for i, s in enumerate(segs):
                prof = s["terms"] | s["files"]
                inter = len(pt & prof)
                jac = inter / (len(pt | prof) or 1)
                containment = inter / (len(pt) or 1)   # small prompt vs big profile
                sim = max(jac, 0.6 * containment)
                if ex["files"] & s["files"]:
                    sim += 0.15
                if sim > bestsim:
                    best, bestsim = i, sim
            if cur == -1:
                sid, kind = len(segs), "NEW"
            elif bestsim >= SIM_TH and best == cur:
                sid, kind = cur, "CONT"
            elif bestsim >= SIM_TH:
                sid, kind = best, "RETURN"
            else:
                sid, kind = len(segs), "NEW"
        if sid == len(segs):
            segs.append({"terms": set(), "files": set(), "tokens": 0})
        segs[sid]["terms"] |= ex["terms"]
        segs[sid]["files"] |= ex["files"]
        segs[sid]["tokens"] += ex["tokens"]
        labels.append((sid, kind))
        cur = sid
    return segs, labels

def cross_topic_load(exchanges, labels):
    """Mean share of prior-context tokens belonging to other threads, per prompt."""
    shares, prior_by_seg, prior_total = [], defaultdict(int), 0
    for ex, (sid, _) in zip(exchanges, labels):
        if prior_total > 0:
            other = prior_total - prior_by_seg[sid]
            shares.append(other / prior_total)
        prior_by_seg[sid] += ex["tokens"]
        prior_total += ex["tokens"]
    return sum(shares) / len(shares) if shares else 0.0

def analyze(paths, show=False, dump_dir=None):
    tot = defaultdict(int)
    loads, seg_counts, n = [], [], 0
    interleaved = 0
    for path in paths:
        try:
            exchanges = load_exchanges(path)
        except OSError:
            continue
        if len(exchanges) < 5:
            continue
        n += 1
        segs, labels = segment(exchanges)
        if dump_dir:
            os.makedirs(dump_dir, exist_ok=True)
            name = os.path.basename(path).replace(".jsonl", "")
            with open(os.path.join(dump_dir, name + ".json"), "w", encoding="utf-8") as f:
                json.dump({"session": name, "n_prompts": len(exchanges), "prompts": [
                    {"i": i, "prompt": ex["prompt"][:300], "tokens": ex["tokens"],
                     "thread": tid, "kind": kind}
                    for i, (ex, (tid, kind)) in enumerate(zip(exchanges, labels))]},
                    f, indent=1)
        kinds = [k for _, k in labels]
        load = cross_topic_load(exchanges, labels)
        loads.append((load, sum(e["tokens"] for e in exchanges)))
        seg_counts.append(len(segs))
        ret = kinds.count("RETURN")
        if ret:
            interleaved += 1
        for k in kinds:
            tot[k] += 1
        if show:
            print(f"\n--- {os.path.basename(path)} : {len(exchanges)} prompts, "
                  f"{len(segs)} threads, cross-topic load {100*load:.0f}%")
            for ex, (sid, kind) in zip(exchanges, labels):
                p = re.sub(r"\s+", " ", ex["prompt"])[:90]
                print(f"  [T{sid:02d} {kind:6s}] {p}")
            continue
        print(f"{os.path.basename(path)[:38]:40s} prompts={len(exchanges):3d} "
              f"threads={len(segs):2d} returns={ret:2d} crossload={100*load:4.0f}%")
    if show or not n:
        return
    total_prompts = sum(tot.values())
    branchy = tot["NEW"] + tot["RETURN"] - n     # first NEW of each session isn't a switch
    mean_load = sum(l for l, _ in loads) / n
    wload = sum(l * t for l, t in loads) / (sum(t for _, t in loads) or 1)
    multi = sum(1 for c in seg_counts if c > 1)
    print(f"\n=== OVERALL ({n} sessions, {total_prompts} prompts) ===")
    print(f"  prompts: CONT {tot['CONT']} ({100*tot['CONT']/total_prompts:.0f}%)  "
          f"NEW {tot['NEW']}  RETURN {tot['RETURN']}")
    print(f"  branch events (excl. session start): {branchy} "
          f"({100*branchy/total_prompts:.0f}% of prompts)")
    print(f"  multi-thread sessions: {multi}/{n} ({100*multi/n:.0f}%)   "
          f"interleaved (>=1 RETURN): {interleaved}/{n} ({100*interleaved/n:.0f}%)")
    print(f"  avg threads/session: {sum(seg_counts)/n:.1f}")
    print(f"  cross-topic context load: mean {100*mean_load:.1f}%  "
          f"token-weighted {100*wload:.1f}%")
    print("\nReading: crossload = share of context each prompt drags along that belongs")
    print("to other threads (upper bound of ancestor-path-only + condensation savings).")
    print("Guide: crossload >=25% & interleaving common -> router has real headroom | "
          "<10% -> sessions are effectively linear, stop")

if __name__ == "__main__":
    args = sys.argv[1:]
    show = "--show" in args
    args = [a for a in args if a != "--show"]
    dump_dir = None
    if "--dump" in args:
        k = args.index("--dump")
        dump_dir = args[k + 1]
        del args[k:k + 2]
    root = os.path.expanduser(args[0]) if args else os.path.expanduser("~/.claude/projects")
    files = [root] if root.endswith(".jsonl") else glob.glob(
        os.path.join(root, "**", "*.jsonl"), recursive=True)
    if not files:
        sys.exit(f"No .jsonl transcripts found under {root}")
    print(f"Scanning {len(files)} transcript(s)...")
    analyze(files, show=show, dump_dir=dump_dir)
