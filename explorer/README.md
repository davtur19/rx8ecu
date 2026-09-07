# RX-8 ECU Firmware Explorer — generated build (dist/)

This directory is **generated** by `web/explorer/build_site.py` and must not
be edited by hand. Regenerate it (deterministic, stdlib-only):

```bash
python3 web/explorer/build_site.py
```

## Contents

- `index.html`, `app.js`, `style.css` — the application (source: `../src/`)
- `data.json` — full dataset (fetched by the app via `fetch`); includes the
  baseline (60E1D400) table values, the 9 firmware-model descriptors and the
  per-model table address map
- `data.js` — `window.EXPLORER_DATA = ...` fallback for opening via `file://`
- `models/<key>.json` — per-model table values (8 files), fetched on demand
  by the firmware-model selector (not available on `file://`)
- `.nojekyll` — required so GitHub Pages serves the raw files as-is

## Dataset summary

| Metric | Value |
|---|---|
| Symbols / functions | 6,083 |
| Callgraph edges (bsr / ref) | 6,952 (758 / 6,194) |
| Calibration-table entries (tables + axes) | 1,210 (1,210 + 0) |
| Tables with extracted values | 616 |
| Function docs (matched to symbols) | 189 (273) |
| Subsystem docs | 15 |
| Firmware models | 9 (value files: 8) |

Values are extracted from `roms/stock/60E1D400.bin`; symbols + callgraph use the `60E0FC00` context.
