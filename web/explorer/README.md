# RX-8 ECU Firmware Explorer

This is an interactive **static** explorer for `rx8ecu` project data. The files are
pre-generated: HTML, JS, and JSON. The site has zero build step and zero external
dependencies. It shows functions and symbols, the callgraph, calibration tables, and
address lookup. It also shows docs. The calibration values come from the stock ROM.
One script generates the site. CI publishes it to **GitHub Pages**
(`.github/workflows/pages.yml`).
**Live site:** [https://davtur19.github.io/rx8ecu/](https://davtur19.github.io/rx8ecu/)

## Local usage

Pages serves the same site that is built into `web/explorer/dist/` (no local/remote
diff). Run the commands from the repo root or from `web/explorer/`:

| # | Command | Effect |
|---|---|---|
| 1 | `make serve` | build `dist/` then serve on http://localhost:8000/ (recommended) |
| 2 | `python3 web/explorer/build_site.py --serve` | build + serve (default port 8000) |
| 3 | `python3 web/explorer/build_site.py` + `cd web/explorer/dist && python3 -m http.server 8000` | build, then serve manually |

- `make serve-port PORT=8080` / `build_site.py --serve 8080` → non-default port.
- Stop with **Ctrl+C**; clean shutdown. `make build`/`make clean`/`make check`
  regenerate / remove / verify `dist/` + `data.json`; quick check:
  `make clean && make build && make check`.
- You do not need a server. Open `dist/index.html` from the filesystem. If
  `fetch("data.json")` fails, the site loads `data.js` automatically. Browsers can
  block `fetch` on `file://`; use a server.

## Regenerate (one command)

```bash
python3 web/explorer/build_site.py    # from repo root
```
The builder uses only the standard library. It is read-only and deterministic.
The output goes to `web/explorer/dist/`: `index.html`, `app.js`, `style.css`,
`data.json` (fetched at runtime), `data.js` (`file://` fallback), `models/<key>.json`
(per-model values: E500/C500/FB00/FC00/B900/E700/15120/32000), `.nojekyll`,
`README.md` (auto build summary). Git ignores `dist/`; Pages rebuilds it on every
push.

## Source layout

- `Makefile` — build / serve / clean / check
- `data/` — REQUIRED INPUTS (committed, NOT gitignored): `roms_meta.json` (9 stock
  ROM models), `table_addr_map.csv` (wide, 1210 rows), `table_addr_map_long.csv`
  (long, 1210 x 9 = 10890 rows), `MAPPING_NOTES.md` (methodology, EN of IT notes)
- `src/` — `index.template.html` + `app.js` + `style.css`
- `build_site.py` — THE builder: dataset + site assembly (+ optional `--serve`)
- `dist/` — generated output (git-ignored, `.gitignore` ignores `dist/` only); edit
  `src/` (and `build_site.py`), never files in `dist/`

## Inputs read (read-only)

- `../../symbols/callgraph.csv` (6953 edges) · `../../symbols/cal_tables.csv` (1210
  entries) · `../../symbols/symbols_60E0FC00.csv` + `..._ghidra.csv` (60E0FC00) ·
  `../../symbols/symbols_60E1D400_ida.csv` + `..._merged.csv` (baseline 60E1D400)
- `../../roms/stock/60E1D400.bin` — **real values** (default model) ·
  `../../roms/stock/*.bin` — **real values** for the other 8 firmware models
- `data/roms_meta.json`, `data/table_addr_map_long.csv` — models + per-ROM map (committed) ·
  `../../docs/functions/*.md` — content, matched by exact/normalized name or header
  address · `../../docs/subsystems/*.md` — content for "Documentation → Subsystems"

## Site content

**Dashboard** — counts, category distribution, top functions by degree (hubs) ·
**Functions & Symbols** — live search (name/address), category/ROM/doc filters; click →
details + callers/callees + **Documentation** (real `.md`) · **Callgraph** — canvas
ego-graph: depth 1–2, `bsr`/`ref` filters; force layout, pan/zoom, drag, re-center ·
**Calibration Tables** — 1210 CSV entries (548 tables + 662 axes), filters; model/base
address, method/confidence, type, values; heatmap/chart when mapped, else est. f32 +
raw bytes · **Documentation** — all `docs/functions/*.md` + `docs/subsystems/*.md`,
full-text search, minimal markdown · **Address Lookup** — hex address → function /
table / nearest entries; baseline + model side by side.

## Firmware model selector

Header dropdown: `60E1D400`, `60E0E500`, `60E1C500`, `60E0FB00`, `60E0FC00`, `60E1B900`, `60E0E700`, `60E15120`, `60E32000`. To change the model:

- The addresses come from `data/table_addr_map_long.csv` (per-table method +
  confidence). There is **no global shift ever**; cal drift is piecewise-constant. The
  values come from the matching `roms/stock/<file>.bin` with the same Map1D/Map2D
  logic as the baseline. Descriptorless tables keep a fallback (raw bytes + estimated
  f32).
- Each row and detail shows a **confidence badge** (`high`/`medium`/`low`) + method.
  Tables without a map (16 trailing of `60E32000`) show **not mapped in this model**.
- Functions and symbols are never adjusted. The symbol CSVs exist only in the
  `60E1D400`/`60E0FC00` contexts. In other contexts the note reads
  "Symbols / functions are not adjusted".
- The data loads lazily. `data.json` (~2.3 MB) embeds only the baseline. The other 8
  models ship as `dist/models/<key>.json` (~0.1–0.22 MB each), **fetched on demand**,
  then cached. On `file://` the model fetch is blocked. The selector gives
  **addresses** (map in `data.json`). Non-baseline **values** show
  "values unavailable".

## Deep links

`#sym-0xADDR` opens **Functions & Symbols**. `#tbl-0xADDR` opens **Calibration
Tables**. `#doc-<filename>` opens **Documentation**.

## Data notes (ROM contexts)

- **Symbols + callgraph** → ROM **60E0FC00** (3363 callgraph addresses resolve into FC00
  symbols; 962 nodes non-FUN, 911 hand) and **60E1D400** (baseline IDA).
- **Calibration tables** → `cal_tables.csv` labeled `60E1D400` (RE baseline). The
  addresses match 1:1 the verified map descriptors in `roms/stock/60E1D400.bin`; all
  499 find the RX8Defs name by pointer. Values are *physical* (`raw × scale + offset`
  per Map1D/Map2D in `c/2DLookup.c` / `c/3dLookup.c`); axes monotonic `f32`. The
  cross-ROM methodology is in [`data/MAPPING_NOTES.md`](data/MAPPING_NOTES.md):
  **content-identity + per-table drift, not global shift**. Highest confidence is
  byte-identical (`content_match`); lower is retuned (`family_shift`).

## GitHub Pages deployment

`.github/workflows/pages.yml` builds the site on every push that touches
`web/explorer/**`, `symbols/**`, `docs/functions/**`, `docs/subsystems/**` or
`roms/**` (branches `main`/`master`). It deploys `web/explorer/dist` with
`upload-pages-artifact` + `deploy-pages`. The committed inputs
`data/roms_meta.json`, `table_addr_map*.csv`, `MAPPING_NOTES.md` are under
`web/explorer/data/`.

## Known limitations

- Per-model values load with `fetch`. On `file://` only the baseline is fully
  interactive.
- The cross-ROM method uses identity + drift, not target-descriptor disassembly.
  Retuned tables stay `medium`/`low`; the address can be off by bytes in shift zones;
  `60E32000` is the worst (16 unmapped, mostly `low`) — see
  `data/MAPPING_NOTES.md`. Baseline tables without a descriptor keep raw bytes +
  optional estimated f32 scalar.
- The ego-graph caps at ~320 nodes. Category assignment is a name-keyword heuristic.
  The markdown renderer is **minimal** (no images, no footnotes, no task lists, no
  syntax highlighting).
- 6 `.md` files do not match a symbol: case-duplicates, consolidated
  `dtc_management`, missing `security_access_handler` address, conflicting
  `mod32_signed`/`div32_signed`. All these appear in **Documentation**.