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
        series_list.append({
            'file': fname, 'series': sname, 'legacy': legacy,
            'tags': sorted(tags), 'dlc': sorted(dlcs),
            'n_missions': len(missions),
            'regions': sorted(regions), 'supers': sorted(supers),
            'rweight': dict(rweight), 'sweight': dict(sweight),
        })

# aggregate per tag (active, tag-locked only)
nation = defaultdict(lambda: {'missions':0,'regions':set(),'supers':set(),'series':[],'dlc':set(),
                              'rweight':defaultdict(int),'sweight':defaultdict(int)})
for s in series_list:
    if s['legacy']:
        continue
    if not s['tags']:
        continue  # generic / non-tag-locked
    for tag in s['tags']:
        nation[tag]['missions'] += s['n_missions']
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
        'name': cname(tag), 'missions': d['missions'],
        'regions': sorted(d['regions']), 'supers': sorted(d['supers']),
        'n_series': len(d['series']), 'dlc': sorted(d['dlc']),
        'rweight': dict(d['rweight']), 'sweight': dict(d['sweight']),
        'series': sorted(set(d['series'])),
    }

with open('nations.json', 'w') as f:
    json.dump(out, f, indent=1)
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
