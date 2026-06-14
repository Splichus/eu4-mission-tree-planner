#!/usr/bin/env python3
"""Export parsed analysis to site/data.js for the local website."""
import json, itertools, os

nat = json.load(open("nations.json"))
FORMABLE = {"SCA","MGE","YUA","GLH","ILK","RUM","AUH","QNG","PLC","SPA","MUG","GBR",
            "GER","ITA","HLR","ROM","NED","HND","RFR","TIM","PRU","HSA","ADU","AVE"}
MIN_MISSIONS = 30

def core_set(d):
    # region targeted by >= 4 missions = a real objective (flat threshold;
    # >=4 drops marginal/incidental regions a nation only brushes a few times)
    rw = d["rweight"]
    return {r for r, w in rw.items() if w >= 4}
def top_super(d):
    sw = d.get("sweight", {})
    return (max(sw, key=sw.get) if sw else "?").replace("_superregion", "")
def short(r): return r.replace("_region", "")
def tier(m):
    if m >= 90: return "XXL"
    if m >= 60: return "XL"
    if m >= 50: return "L"
    if m >= 44: return "M"
    if m >= 38: return "S"
    return "XS"

# collapse exact-duplicate trees
groups, order = {}, []
for t, d in sorted(nat.items(), key=lambda kv: -kv[1]["missions"]):
    if d["missions"] < MIN_MISSIONS:
        continue
    if d.get("inherits"):        # "recolour" tags with no tree of their own (Roman Empire,
        continue                 # Austria-Hungary) -- drop entirely; the real predecessors show instead
    fp = (d["missions"], tuple(sorted(d["regions"])), tuple(sorted(d["series"])))
    if fp in groups:
        groups[fp].append(t)
    else:
        groups[fp] = [t]; order.append((fp, t, d))

# Handle formable recolours (a formable whose whole mission set is a subset of a real
# nation -- it adds nothing). Two cases:
#  - SPLIT parent: a real nation with >=2 distinct formable outcomes (England -> Great
#    Britain / Angevin, mutually-exclusive branches). Drop the parent, KEEP the outcomes
#    (they're genuinely different races).
#  - otherwise: drop the formable subset, keep the real nation.
# Spain/Commonwealth/Scandinavia survive either way -- they are SUPERSETS of their start
# nation, not subsets.
sermap = {t: set(d["series"]) for fp, t, d in order}
nonform = [t for fp, t, d in order if t not in FORMABLE]
split_parents = set()
for u in nonform:
    subs = [t for fp, t, d in order if t in FORMABLE and sermap[t] and sermap[t] <= sermap[u]]
    distinct = [t for t in subs if not any(s != t and sermap[t] < sermap[s] for s in subs)]
    if len(distinct) >= 2:
        split_parents.add(u)
def _is_recolour(t, st):
    if t in split_parents:                       # parent replaced by its outcomes
        return True
    if t in FORMABLE and any(st <= sermap[u] for u in nonform if u not in split_parents):
        return True                              # subset of a single-outcome real nation
    return False
_before = len(order)
order = [(fp, t, d) for fp, t, d in order if not _is_recolour(t, set(d["series"]))]
print(f"dropped {_before - len(order)} recolours; split-parents replaced by outcomes: "
      f"{sorted(nat[t]['name'] for t in split_parents)}")

info, cands = {}, []
for fp, t, d in order:
    cs = sorted(short(r) for r in core_set(d))
    info[t] = {"core": core_set(d), "all": set(d["regions"]), "series": set(d["series"]),
               "m": d["missions"], "name": d["name"], "sup": top_super(d), "f": t in FORMABLE}
    cands.append({"tag": t, "name": d["name"], "missions": d["missions"], "tier": tier(d["missions"]),
                  "blueprint": d.get("blueprint", d["missions"]),
                  "inherits": d.get("inherits", []),   # non-empty => no own tree (continuation of these)
                  "theater": top_super(d), "core": cs, "ncore": len(cs),
                  "formable": t in FORMABLE, "aliases": [x for x in groups[fp] if x != t],
                  "nseries": len(d["series"])})

def size_similar(a, b):
    lo, hi = sorted([info[a]["m"], info[b]["m"]])
    return (lo / hi >= 0.72) or (hi - lo <= 12)

pairs = []
for a, b in itertools.combinations(info, 2):
    if info[a]["series"] & info[b]["series"]: continue
    if info[a]["core"] & info[b]["core"]: continue
    if not size_similar(a, b): continue
    ov = sorted(short(r) for r in (info[a]["all"] & info[b]["all"]))
    pairs.append({"a": a, "b": b, "an": info[a]["name"], "bn": info[b]["name"],
                  "am": info[a]["m"], "bm": info[b]["m"], "delta": abs(info[a]["m"] - info[b]["m"]),
                  "ov": len(ov), "overlap": ov, "ta": info[a]["sup"], "tb": info[b]["sup"],
                  "fa": info[a]["f"], "fb": info[b]["f"],
                  "tierA": tier(info[a]["m"]), "tierB": tier(info[b]["m"]),
                  "well": len(core_set(nat[a])) >= 2 and len(core_set(nat[b])) >= 2})
pairs.sort(key=lambda p: (p["ov"], p["delta"]))

# curated editor picks (verified clean), tiered by race length
picks = [
    {"a":"SPA","b":"RUS","tier":"XL — long campaign","note":"Iberia+colonies vs Eastern Europe+Siberia. Δ1 mission, no core conflict. Both start as the great power — the fairest titan race."},
    {"a":"TUR","b":"FRA","tier":"XL — long campaign","note":"Ottomans (Balkans/Anatolia/Levant) vs France (Western Europe + Italy). Δ13, no core conflict. The two largest non-formable trees, at opposite ends of the Mediterranean."},
    {"a":"MUG","b":"PRU","tier":"XL — long campaign","note":"Mughals (India) vs Prussia (Baltic & Germany militarist). Δ0 missions (88 each), zero overlap — the subcontinent vs Central Europe. Both are formables with two of the game's biggest trees."},
    {"a":"JAP","b":"NED","tier":"L — medium","note":"Japan (unify the daimyo) vs the Netherlands (Atlantic trade & colonial empire). Δ7, no core overlap — Far East vs the Low Countries. Netherlands is a formable."},
    {"a":"POL","b":"POR","tier":"M — moderate","note":"Poland (Central-Eastern Europe) vs Portugal (Iberia + Atlantic/colonial empire). Δ0 missions (41 each), zero overlap — distinct theaters."},
    {"a":"KOR","b":"HUN","tier":"S — shorter","note":"Korea (vs Ming/Manchu/Japan) vs Hungary (Carpathia/Balkans). Δ1 mission, zero overlap. The quickest of the recommended races."},
]
pick_out = []
for p in picks:
    a, b = p["a"], p["b"]
    if a in info and b in info:
        pick_out.append({**p, "an": info[a]["name"], "bn": info[b]["name"],
                         "am": info[a]["m"], "bm": info[b]["m"],
                         "ta": info[a]["sup"], "tb": info[b]["sup"],
                         "fa": info[a]["f"], "fb": info[b]["f"]})

data = {"candidates": cands, "pairs": pairs, "picks": pick_out,
        "stats": {"nCandidates": len(cands), "nPairs": len(pairs),
                  "nMissionFiles": 228, "allDLC": True}}
os.makedirs("docs", exist_ok=True)
with open("docs/data.js", "w") as f:
    f.write("window.EU4_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n")
print(f"wrote docs/data.js: {len(cands)} candidates, {len(pairs)} pairs, {len(pick_out)} picks")
