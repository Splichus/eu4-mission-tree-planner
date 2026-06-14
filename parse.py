#!/usr/bin/env python3
"""Parse EU4 mission files -> per-nation mission size + geographic footprint, under all-DLC-enabled."""
import re, glob, os, json, sys
from collections import defaultdict

# EU4 install dir: override with EU4_DIR env var; defaults to the standard macOS Steam path.
EU4 = os.environ.get("EU4_DIR") or os.path.expanduser(
    "~/Library/Application Support/Steam/steamapps/common/Europa Universalis IV")
MAP = os.path.join(EU4, "map")

# ---------- tokenizer / parser for Paradox script ----------
def tokenize(s):
    # Character-level scanner. Correctly handles: multi-line quoted strings
    # (newer DLC scripted-effect blocks like first_effect = "...{...}..."),
    # backslash-escaped quotes (\") inside them, and '#' comments. Braces and '#'
    # INSIDE a string are literal, so structural brace matching stays correct.
    toks = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch == '"':
            j = i + 1
            while j < n:
                if s[j] == '\\' and j + 1 < n:
                    j += 2; continue
                if s[j] == '"':
                    break
                j += 1
            toks.append(s[i:j + 1])  # whole string as one token
            i = j + 1
        elif ch == '#':
            while i < n and s[i] != '\n':
                i += 1
        elif ch in '{}=':
            toks.append(ch); i += 1
        elif ch.isspace():
            i += 1
        else:
            j = i
            while j < n and (not s[j].isspace()) and s[j] not in '{}="#':
                j += 1
            toks.append(s[i:j]); i = j
    return toks

def parse_block(tokens, i):
    items = []
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t == '}':
            return items, i + 1
        if i + 1 < n and tokens[i + 1] == '=':
            key = t
            i += 2
            if i >= n:
                break
            v = tokens[i]
            if v == '{':
                block, i = parse_block(tokens, i + 1)
                items.append((key, block))
            else:
                items.append((key, v))
                i += 1
        else:
            if t == '{':
                block, i = parse_block(tokens, i + 1)
                items.append(('', block))
            else:
                items.append(('', t))
                i += 1
    return items, i

def parse_file(path):
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as f:
        txt = f.read()
    toks = tokenize(txt)
    items, _ = parse_block(toks, 0)
    return items

def children(block, key):
    return [v for (k, v) in block if k == key]

def first(block, key):
    for (k, v) in block:
        if k == key:
            return v
    return None

# ---------- geography ----------
def load_geo():
    prov2area = {}
    area_items = parse_file(os.path.join(MAP, "area.txt"))
    for (name, val) in area_items:
        if not name or not isinstance(val, list):
            continue
        for (k, v) in val:
            if k == '' and isinstance(v, str) and v.isdigit():
                prov2area[int(v)] = name
    area2region = {}
    region_items = parse_file(os.path.join(MAP, "region.txt"))
    region_names = set()
    for (name, val) in region_items:
        if not name or not isinstance(val, list):
            continue
        region_names.add(name)
        areas_block = first(val, "areas")
        if isinstance(areas_block, list):
            for (k, v) in areas_block:
                if k == '' and isinstance(v, str):
                    area2region[v] = name
    region2super = {}
    super_items = parse_file(os.path.join(MAP, "superregion.txt"))
    super_names = set()
    for (name, val) in super_items:
        if not name or not isinstance(val, list):
            continue
        super_names.add(name)
        for (k, v) in val:
            if k == '' and isinstance(v, str):
                region2super[v] = name
    all_area_names = set(prov2area.values()) | set(area2region.keys())
    return prov2area, area2region, region2super, region_names, super_names, all_area_names

prov2area, area2region, region2super, REGION_NAMES, SUPER_NAMES, AREA_NAMES = load_geo()

def prov_region(pid):
    a = prov2area.get(pid)
    return area2region.get(a) if a else None

def region_of_area(a):
    return area2region.get(a)

# ---------- country names from localisation ----------
def load_names():
    names = {}
    for path in glob.glob(os.path.join(EU4, "localisation", "*_l_english.yml")):
        try:
            with open(path, 'r', encoding='utf-8-sig', errors='replace') as f:
                for line in f:
                    m = re.match(r'\s*([A-Z0-9]{3}):\d*\s*"(.*?)"', line)
                    if m:
                        tag, nm = m.group(1), m.group(2)
                        if tag not in names and nm and '$' not in nm:
                            names[tag] = nm
        except Exception:
            pass
    return names
NAMES = load_names()
def cname(tag):
    return NAMES.get(tag, tag)

# ---------- targeted geographic extraction ----------
# Province references only via these keys (avoids numeric thresholds like development=30).
PROV_KEYS = {'province_id','owns','owns_core_province','owns_or_non_sovereign_subject_of',
             'controls','province','owned_by_and_state','has_owner_culture'}
GEO_KEYS = {'area','region','superregion','continent'}

def collect_geo(block, regions, supers, allow_bare_ints):
    for (k, v) in block:
        if isinstance(v, list):
            if k in AREA_NAMES:
                r = region_of_area(k)
                if r: regions.add(r)
            elif k in REGION_NAMES:
                regions.add(k)
            elif k in SUPER_NAMES:
                supers.add(k)
            collect_geo(v, regions, supers, allow_bare_ints)
        else:
            if k in PROV_KEYS and isinstance(v, str) and v.isdigit():
                r = prov_region(int(v))
                if r: regions.add(r)
            elif k in GEO_KEYS and isinstance(v, str):
                if v in AREA_NAMES:
                    r = region_of_area(v)
                    if r: regions.add(r)
                elif v in REGION_NAMES:
                    regions.add(v)
                elif v in SUPER_NAMES:
                    supers.add(v)
            elif k == '' and allow_bare_ints and isinstance(v, str) and v.isdigit():
                # bare province id inside provinces_to_highlight
                pid = int(v)
                if pid in prov2area:
                    r = prov_region(pid)
                    if r: regions.add(r)

def footprint_of_mission(mission_block):
    regions = set()
    supers = set()
    b = first(mission_block, "provinces_to_highlight")
    if isinstance(b, list):
        collect_geo(b, regions, supers, allow_bare_ints=True)
    b = first(mission_block, "trigger")
    if isinstance(b, list):
        collect_geo(b, regions, supers, allow_bare_ints=False)
    for r in list(regions):
        s = region2super.get(r)
        if s:
            supers.add(s)
    return regions, supers

# ---------- potential analysis ----------
def potential_tags(pot):
    tags = set()
    def walk(b):
        for (k, v) in b:
            if k == 'tag' and isinstance(v, str):
                tags.add(v)
            if isinstance(v, list):
                walk(v)
    if isinstance(pot, list):
        walk(pot)
    return tags

def potential_poslist_dlc(pot):
    dlcs = set()
    def walk(b, under_not):
        for (k, v) in b:
            if k == 'has_dlc' and isinstance(v, str) and not under_not:
                dlcs.add(v.strip('"'))
            if isinstance(v, list):
                walk(v, under_not or (k in ('NOT', 'not')))
    if isinstance(pot, list):
        walk(pot, False)
    return dlcs

def is_legacy(pot):
    """Inactive when a top-level NOT={has_dlc=...} exists (all DLC owned)."""
    if not isinstance(pot, list):
        return False
    for (k, v) in pot:
        if k in ('NOT', 'not') and isinstance(v, list):
            # does this NOT contain a has_dlc?
            for (k2, v2) in v:
                if k2 == 'has_dlc':
                    return True
    return False

def is_mission(block):
    # Every mission node has an 'icon' (its grid image). 'position' is NOT always
    # present (some Golden Century / older missions omit it), so keying off position
    # silently dropped real missions. icon is the reliable per-mission marker.
    return isinstance(block, list) and first(block, "icon") is not None

# ---------- mutual-exclusivity model (branch choices) ----------
# Model a series' `potential` as a boolean expression over *atoms* that encode the
# mutually-exclusive choices a single playthrough can't all satisfy:
#   cf:<flag>            -- has_country_flag (branch choices set by missions/events)
#   tag:<TAG>            -- the country tag (constant: true only for the tag analysed)
#   is/was_<origin>_nation -- steppe formation origin (Mongol/Tatar/Moghulistan)
# Everything else is treated as freely satisfiable. The completable count is the max
# over all valid atom assignments (free country flags x one formation origin).
# Origin scripted-trigger tag membership (from common/scripted_triggers):
MONGOL_TAGS = {"OIR","KHA","KRC","HMI","SYG","KSD","KLK","ZUN"}
TATAR_TAGS  = {"GOL","CRI","NOG","KAZ","SIB","BSH","AST","QAS","KLM","CHH"}
MOGH_TAGS   = {"KAS","CHG","SHY","BUK","KZH","KOK","KHI"}
ORIGIN_ATOMS = {"is_mongol_nation","is_tatar_nation","is_moghulistan_nation",
                "was_mongol_nation","was_tatar_nation","was_moghulistan_nation"}
WAS_ATOMS = {"was_mongol_nation","was_tatar_nation","was_moghulistan_nation"}

def build_item(k, v):
    kl = k.lower() if isinstance(k, str) else k
    if kl == 'has_country_flag' and isinstance(v, str):
        return ['flag', 'cf:' + v.strip('"')]
    if kl == 'tag' and isinstance(v, str):
        x = v.strip('"')
        # Only the 4 steppe formables need `tag` as a hard exclusive atom (their origin
        # else-defaults: GLH->Tatar, YUA->Mongol). Every other tag is freely satisfiable
        # (you can FORM tags) so flavor pairs like tag=POL/NOT tag=PLC aren't broken.
        return ['flag', 'tag:' + x] if x in STEPPE_FORMABLES else None
    if kl in ORIGIN_ATOMS:
        atom = ['flag', kl]
        return ['not', atom] if (isinstance(v, str) and v.strip('"').lower() == 'no') else atom
    if isinstance(v, list):
        if kl == 'not':
            inner = build_block(v)
            return ['not', inner] if inner is not None else None
        if kl == 'or':
            subs = [build_item(k2, v2) for (k2, v2) in v]
            if any(s is None for s in subs):
                return None  # an OR branch is freely satisfiable -> whole OR is
            subs = [s for s in subs if s is not None]
            if not subs:
                return None
            return ['or', subs] if len(subs) > 1 else subs[0]
        return build_block(v)  # AND / scope block
    return None  # leaf condition we don't model: freely satisfiable

def _ifelse(lim, body, els):
    # if {limit=lim body} [else {els}]  ==  (lim AND body) OR (NOT lim AND els_or_true)
    if lim is None:
        return body  # limit always satisfiable -> then-branch always taken
    then = ['and', [lim, body]] if body is not None else lim
    elsepart = ['not', lim] if els is None else ['and', [['not', lim], els]]
    return ['or', [then, elsepart]]

def build_block(block):
    parts = []
    i, n = 0, len(block)
    while i < n:
        k, v = block[i]
        kl = k.lower() if isinstance(k, str) else k
        if kl == 'if' and isinstance(v, list):
            lim = None; bodyitems = []
            for (k2, v2) in v:
                if (k2.lower() if isinstance(k2, str) else k2) == 'limit' and isinstance(v2, list):
                    lim = build_block(v2)
                else:
                    bodyitems.append((k2, v2))
            body = build_block(bodyitems)
            els = None
            if i + 1 < n and isinstance(block[i+1][0], str) and block[i+1][0].lower() == 'else' \
               and isinstance(block[i+1][1], list):
                els = build_block(block[i+1][1]); i += 1
            ie = _ifelse(lim, body, els)
            if ie is not None: parts.append(ie)
        else:
            it = build_item(k, v)
            if it is not None: parts.append(it)
        i += 1
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else ['and', parts]

def flags_in(e):
    if e is None:
        return set()
    t = e[0]
    if t == 'flag':
        return {e[1]}
    if t == 'not':
        return flags_in(e[1])
    if t in ('and', 'or'):
        out = set()
        for s in e[1]:
            out |= flags_in(s)
        return out
    return set()

STEPPE_FORMABLES = {"MGE", "YUA", "ILK", "GLH"}

def eval_expr(e, assign):
    if e is None:
        return True
    t = e[0]
    if t == 'flag':
        name = e[1]
        if name in assign:
            return assign[name]
        # tag:<X> not pinned -> treat as achievable (you can FORM other tags). Only the
        # steppe formables are pinned in `base` (mutually-exclusive origin defaults).
        if name.startswith('tag:'):
            return True
        return False
    if t == 'not':
        return not eval_expr(e[1], assign)
    if t == 'and':
        return all(eval_expr(s, assign) for s in e[1])
    if t == 'or':
        return any(eval_expr(s, assign) for s in e[1])
    return True

def detect_flag_families(flags):
    """Group country-flags that look like alternatives of one choice: identical
    except a single WORD token (e.g. sca_unlock_{catholic,humanist,norse,protestant}_missions,
    hordes_{confucian,devout,tolerance}_branch_flag, pol_{chose,denied}_pu_flag).
    Numeric-only differences (step_1/step_2) are NOT grouped (those are sequential).
    Returns {flag: family_id} for flags that belong to a family of >=2."""
    keymap = defaultdict(set)
    for f in flags:
        toks = f[3:].split('_')  # strip 'cf:'
        for i, t in enumerate(toks):
            if t.isalpha():      # only a word token may be the varying choice
                key = (tuple(toks[:i]), '*', tuple(toks[i+1:]))
                keymap[key].add(f)
    fam = {}
    for members in sorted((v for v in keymap.values() if len(v) >= 2), key=lambda s: -len(s)):
        fid = min(members)
        for f in members:
            fam.setdefault(f, fid)  # largest family a flag matches wins
    return fam

def _flag_total(items, base, fam_map):
    """Max missions over free country-flag (cf:) assignments, with `base` fixing
    tag/origin atoms. Series sharing a cf: flag -- or a flag in the same choice family --
    form one exclusion group; within a family at most one flag may be set."""
    n = len(items)
    free = [sorted(a for a in flags_in(e) if a.startswith('cf:')) for (_, e) in items]
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    f2i, fam2i = {}, {}
    for i, fs in enumerate(free):
        for f in fs:
            f2i.setdefault(f, []).append(i)
            if f in fam_map:
                fam2i.setdefault(fam_map[f], []).append(i)
    for idxs in list(f2i.values()) + list(fam2i.values()):  # union by shared flag AND by family
        for j in idxs[1:]:
            parent[find(j)] = find(idxs[0])
    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    total = 0
    for idxs in groups.values():
        gf = sorted(set().union(*[set(free[i]) for i in idxs])) if idxs else []
        if not gf or len(gf) > 18:
            a = dict(base)
            total += sum(items[i][0] for i in idxs if eval_expr(items[i][1], a))
            continue
        excl = defaultdict(list)            # choice families present in this group
        for f in gf:
            if f in fam_map:
                excl[fam_map[f]].append(f)
        excl = [fs for fs in excl.values() if len(fs) > 1]
        best = 0
        for mask in range(1 << len(gf)):
            a = dict(base)
            for b in range(len(gf)):
                a[gf[b]] = bool((mask >> b) & 1)
            if any(sum(a[f] for f in fam) > 1 for fam in excl):
                continue                    # can't pick two options of one choice family
            best = max(best, sum(items[i][0] for i in idxs if eval_expr(items[i][1], a)))
        total += best
    return total

def completable_missions(items, tag):
    """Max missions completable in one playthrough for `tag`: free country-flag
    branches x exactly one formation origin (Mongol/Tatar/Moghulistan/none)."""
    consts = {'is_mongol_nation': tag in MONGOL_TAGS,
              'is_tatar_nation': tag in TATAR_TAGS,
              'is_moghulistan_nation': tag in MOGH_TAGS}
    atoms = set()
    for _, e in items:
        atoms |= flags_in(e)
    fam_map = detect_flag_families({a for a in atoms if a.startswith('cf:')})
    use_origin = any(a in ORIGIN_ATOMS for a in atoms)
    if not use_origin:
        origins = [{}]
    elif tag in TATAR_TAGS:
        origins = [{'was_tatar_nation': True}]
    elif tag in MONGOL_TAGS:
        origins = [{'was_mongol_nation': True}]
    elif tag in MOGH_TAGS:
        origins = [{'was_moghulistan_nation': True}]
    else:  # formable / other: pick one origin (or none) -> take the best
        origins = [{'was_mongol_nation': True}, {'was_tatar_nation': True},
                   {'was_moghulistan_nation': True}, {}]
    best = 0
    for orig in origins:
        base = dict(consts)
        for w in WAS_ATOMS:
            base[w] = orig.get(w, False)
        base['tag:' + tag] = True
        for f in STEPPE_FORMABLES:        # pin the 4 steppe formables (exclusive origin defaults)
            base['tag:' + f] = (f == tag)
        best = max(best, _flag_total(items, base, fam_map))
    return best

SERIES_KEYWORDS = {'slot','generic','ai','potential','has_country_shield','has_country_flag','potential_on_load'}

# ---------- main parse ----------
series_list = []
for path in glob.glob(os.path.join(EU4, "missions", "*.txt")):
    fname = os.path.basename(path)
    try:
        items = parse_file(path)
    except Exception as e:
        print(f"PARSE FAIL {fname}: {e}", file=sys.stderr)
        continue
    for (sname, sblock) in items:
        if not isinstance(sblock, list):
            continue
        pot = first(sblock, "potential")
        legacy = is_legacy(pot)
        tags = potential_tags(pot)
        dlcs = potential_poslist_dlc(pot)
        missions = [v for (k, v) in sblock if k not in SERIES_KEYWORDS and is_mission(v)]
        if not missions:
            continue
        regions, supers = set(), set()
        rweight = defaultdict(int)
        sweight = defaultdict(int)
        for m in missions:
            r, s = footprint_of_mission(m)
            regions |= r
            supers |= s
            for x in r:
                rweight[x] += 1
            for x in s:
                sweight[x] += 1
        fexpr = build_block(pot) if isinstance(pot, list) else None
        series_list.append({
            'file': fname, 'series': sname, 'legacy': legacy,
            'tags': sorted(tags), 'dlc': sorted(dlcs),
            'n_missions': len(missions),
            'regions': sorted(regions), 'supers': sorted(supers),
            'rweight': dict(rweight), 'sweight': dict(sweight),
            'flags': sorted(flags_in(fexpr)), '_expr': fexpr,
        })

# aggregate per tag (active, tag-locked only)
nation = defaultdict(lambda: {'missions':0,'regions':set(),'supers':set(),'series':[],'dlc':set(),
                              'rweight':defaultdict(int),'sweight':defaultdict(int),'items':[]})
for s in series_list:
    if s['legacy']:
        continue
    if not s['tags']:
        continue  # generic / non-tag-locked
    for tag in s['tags']:
        nation[tag]['missions'] += s['n_missions']
        nation[tag]['items'].append((s['n_missions'], s['_expr']))
        nation[tag]['regions'] |= set(s['regions'])
        nation[tag]['supers'] |= set(s['supers'])
        nation[tag]['series'].append(s['series'])
        nation[tag]['dlc'] |= set(s['dlc'])
        for r, w in s['rweight'].items():
            nation[tag]['rweight'][r] += w
        for r, w in s['sweight'].items():
            nation[tag]['sweight'][r] += w

out = {}
for tag, d in nation.items():
    out[tag] = {
        'name': cname(tag), 'missions': completable_missions(d['items'], tag),
        'blueprint': d['missions'],
        'regions': sorted(d['regions']), 'supers': sorted(d['supers']),
        'n_series': len(d['series']), 'dlc': sorted(d['dlc']),
        'rweight': dict(d['rweight']), 'sweight': dict(d['sweight']),
        'series': sorted(set(d['series'])),
    }

with open('nations.json', 'w') as f:
    json.dump(out, f, indent=1)
for s in series_list:
    s.pop('_expr', None)
with open('series.json', 'w') as f:
    json.dump(series_list, f, indent=1)

# summary
active_taglocked = [s for s in series_list if not s['legacy'] and s['tags']]
print(f"total series parsed: {len(series_list)}")
print(f"legacy(inactive) series: {sum(1 for s in series_list if s['legacy'])}")
print(f"active tag-locked series: {len(active_taglocked)}")
print(f"distinct nations with active tag-locked trees: {len(out)}")
print()
ranked = sorted(out.items(), key=lambda kv: -kv[1]['missions'])
print("TOP 45 nations by active unique mission count:")
print(f"{'tag':4} {'name':28} {'miss':>4} {'ser':>3} {'regions':>4}  dlc")
for tag, d in ranked[:45]:
    print(f"{tag:4} {d['name'][:28]:28} {d['missions']:>4} {d['n_series']:>3} {len(d['regions']):>4}  {','.join(x[:12] for x in d['dlc'])}")
