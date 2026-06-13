# EU4 Mission-Tree Race Planner

Picks pairs of nations for a **"first to finish all mission trees"** multiplayer race —
trees that **don't fight over the same land** and are **similar in size**.
All data is parsed straight from the game's own files (all DLC enabled).

**▶ Live page:** https://splichus.github.io/eu4-mission-tree-planner/

## What it shows
- **Recommended matchups** tiered by race length (e.g. Spain vs Russia, Japan vs Ottomans, Poland vs Mali).
- An interactive **matchups table** — filter by tier / theater / size-gap, "zero overlap only" toggle, hide formables, search, sortable columns.
- A **nations table** with each nation's mission count and geographic focus.

## Run locally
```bash
# A) just open it (no server needed)
open docs/index.html

# B) local server
./docs/run.sh            # serves http://localhost:8731/
```

## Regenerate the data (after a game patch / DLC change)
Requires EU4 installed. By default it looks in the standard macOS Steam location;
override with the `EU4_DIR` environment variable.
```bash
export EU4_DIR="/path/to/Europa Universalis IV"   # optional
python3 parse.py      # parse missions/ + map/ -> nations.json, series.json
python3 analyze.py    # -> REPORT.md (full candidate table + all clean pairs)
python3 export.py     # -> docs/data.js (powers the page)
```

## Files
- `parse.py`   – Paradox-script parser; resolves province→area→region→superregion,
                 finds active (non-legacy) tag-locked mission series, counts missions,
                 and extracts each nation's geographic footprint (weighted by mission).
- `analyze.py` – builds the candidate list + clean-matchup logic; writes `REPORT.md`.
- `export.py`  – writes `docs/data.js`.
- `docs/`      – the website (`index.html` + `data.js` + `run.sh`), served by GitHub Pages.
- `REPORT.md`  – static markdown version of the full analysis.
- `nations.json` / `series.json` – the parsed dataset.

## Method (short)
- **Missions** = total across all active, tag-locked series a tag can see (legacy pre-DLC trees excluded).
- **Core regions** = regions targeted by ≥ max(3, 12% of missions) — the nation's real objectives.
- **Clean matchup** = zero shared *core* regions **and** no shared mission series (not the same
  lineage/formable chain) **and** similar size (ratio ≥ 0.72 or within 12 missions).
- **Size ≠ difficulty.** The files encode mission *count*, not how hard a tree is — judge that yourselves.
- Formables are **included and flagged** (`F`): you must form them in-game before the tree unlocks.

## Note
This is transformative analysis (aggregate counts, region names) derived from
*Europa Universalis IV*, © Paradox Interactive. No game files are redistributed here.
