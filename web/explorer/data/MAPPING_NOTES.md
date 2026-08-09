# MAPPING NOTES — Cross-ROM calibration-table address map

An autonomous analysis generated this map. The script is in `/tmp/opencode/rx8/map_final.py`;
it is not committed. The analysis covered the 9 stock 512 KB ROMs (`roms/stock/*.bin`,
SH-2E big-endian). It used `symbols/cal_tables.csv` (1210 entries) as the master
list. **No repository source file was modified; output only in `web/explorer/data/`.**

## Produced files

| file | content |
|---|---|
| `table_addr_map.csv` | wide format: 1210 rows (one per table), columns `table_id, baseline_addr, addr_D400, addr_E500, addr_C500, addr_FB00, addr_FC00, addr_B900, addr_E700, addr_15120, addr_32000, method, confidence`. `method`/`confidence` are per-row summaries (`method:count`); the per-ROM detail is in `table_addr_map_long.csv` |
| `table_addr_map_long.csv` | long format (10890 rows = 1210 tables × 9 ROMs): `table_id, baseline_addr, rom, addr, method, confidence` — convenient for the web UI "choose firmware model → read address" |
| `roms_meta.json` | metadata of the 9 ROMs (cal ID, SW module, task module, security-key offset, sha256, code_end, cal_lo/span, `SW-` string offset, family, family shift vs baseline, coverage statistics) |
| `MAPPING_NOTES.md` | this document |

## Structure of the symbol CSVs (verification requested)

- **There is no per-ROM column** in the symbol CSVs.
- `symbols/cal_tables.csv`: columns `src,name,address`; `src` is always
  `60E1D400` (the RE baseline), whose addresses match 1:1 the baseline
  `60E1D400` (already verified by the project: 499/499 descriptors).
- The function symbols are split **by file name**, not by column:
  - `symbols_60E1D400_ida.csv` / `symbols_60E1D400_merged.csv` → context **60E1D400**
  - `symbols_60E0FC00.csv` / `symbols_60E0FC00_ghidra.csv` → context **60E0FC00**
  - `callgraph.csv` → context **60E0FC00** (as per `web/explorer/README.md`)
- **Existing contexts/bases**: two, `60E1D400` (RE baseline) and `60E0FC00`
  (Z-line, equinox reference). No other base addresses in the CSVs.

## Methodology

For each ROM ≠ baseline, in order of reliability:

1. **same_addr** — baseline `60E1D400` only: `addr = baseline_addr`. Confidence high.
2. **content_match** — **exact** match of the table's 16-byte baseline window
   inside the target cal region (`[cal_lo, 0x7DAFF]`). The candidate is chosen
   consistently with the local drift curve (mode of the deltas of the unambiguous
   matches within ±0x800/±0x2000/±0x4000). Confidence high.
   *The vast majority of tables are byte-identical across builds. The "delta"
   of the diff at the same address was actually relocation, not retune.*
3. **family_shift** — for tables without an exact match: candidate address
   `baseline_addr + local_drift`, verified with *fuzzy byte-equality* over
   min(extent,64) bytes:
   - score ≥ 0.80 → medium;
   - 0.60–0.80 → limited refinement to ±8 bytes (only if it reaches ≥0.85,
     otherwise the drift address is kept) → medium/low;
   - 0.50–0.60 (retuned table: values have changed) → the drift address is
     assigned anyway, confidence **low** (no refinement: avoids "jumping" to
     the neighbouring table with similar content);
   - only non-0xFF occupancy at the drift address → low.
4. **hole** — tables that are 0xFF holes in the baseline (1 case: `Table 3D - 14_`
   @0x6EDF4): mapped only through drift, confidence low (exact matches are spurious).
5. **unmatched** — no valid candidate (outside the target cal region or no
   evidence). `addr` left empty.

`cal_table_diffs_baseline.csv` (analysis/romdiff) was **examined but not used as
a shift**: its methodology compares the **u16 values at the same address**
(value delta, not displacement). It is only useful as indirect evidence of
occupancy. The real displacements were derived from the content match and from
the `SW-` identity string shift.

### Family shift (`SW-` string vs baseline) and drift

The cal layout is NOT a uniform shift. The shift is **piecewise-constant**
(table blocks are reordered/resized between builds). Initial shift from the
`SW-` string (offset `0x6CE43` in the baseline):

| family | ROM | `SW-` shift | main drift (baseline_addr → target) |
|---|---|---|---|
| J-line | E500, C500 | **−0x800** | −0x800 → −0x1040 → −0x1788 → −0x1C1C |
| N3YL | E700 | **−0x800** | −0x800 → −0xF90 → −0x16D8 → −0x1B6C |
| Z-line | FB00, FC00, B900 | **+0x500** | +0x500 → −0x4BC/−0x4F8/−0x58C/−0x7AC → −0x123C/−0x12F4/−0x125C → −0x1480 |
| hybrid | 15120 | **−0xE00** | −0xE00 → −0xB70/−0x948/−0x840 → −0x3DC/−0xF4 → +0x238/+0x434 |
| outlier | 32000 | **+0x4700** | +0x4700 → +0x1900 → +0x1160 → +0xE5C (block 5–50 KB further, short span 50687) |

The per-table drift curve was reconstructed from the **unambiguous** matches
(16B windows with a single occurrence in the target) and validated (see below).

## Coverage per ROM (1210 tables in cal_tables.csv)

| ROM | mapped | unmapped | high | medium | low | prevailing method |
|---|---|---|---|---|---|---|
| D400 (baseline) | 1210 | 0 | 1209 | 0 | 1* | same_addr |
| E500 | 1209 | 1 | 845 | 232 | 132 | content_match |
| C500 | 1209 | 1 | 947 | 178 | 84 | content_match |
| FB00 | 1210 | 0 | 762 | 144 | 304 | content_match |
| FC00 | 1210 | 0 | 764 | 141 | 305 | content_match |
| B900 | 1210 | 0 | 764 | 141 | 305 | content_match |
| E700 | 1209 | 1 | 723 | 265 | 221 | content_match |
| 15120 | 1209 | 1 | 799 | 207 | 203 | content_match |
| 32000 | 1194 | 16 | 401 | 16 | 777 | family_shift |

\* the baseline "low" is the hole table (`hole`).

Average confidence (the baseline excluded): high ≈ 700–950, medium ≈ 140–270,
low ≈ 80–300 for the J/Z families. For 32000 the low values dominate (777),
because it is the structurally most distant build (cal block 0x71500, 16 trailing
tables of the baseline @0x7C4F4–0x7D92C not mappable: the 32000 span ends first).

## Validation performed

- **content_match**: 6005/6005 mappings verified byte-identical (16B) by
  construction of the method.
- **Known constants**: `Rev Limit`=9000.0, `Cold Rev Limit`=5500.0,
  `Cold Rev Limit Threshold`=20.0 verified byte-exact at the mapped addresses
  in E500/C500/FB00/FC00/B900/15120 (E700 retunes them: 7500/5500/0.0 → correct
  mapping of retuned values; 32000 not reliable → low).
- **Drift curve**: fraction of mappings whose delta equals the local mode:
  E500 98%, C500 98%, E700 98%, Z-line 88%, 15120 88%, 32000 79%.
- **Monotonic f32 axes** (148 baseline axes): the high/medium mappings land on
  monotonic sequences in 95–100% of the cases for the J/Z families; the few
  "failures" are axes with trailing duplicates/denormals (the window invades
  the next table).
- **Region**: all mapped addresses lie in `[cal_lo, 0x7DAFF]`.

## Known limitations

- The mapping is **content-identity + drift curve**, not a *disassembly* of the
  target's Map1D/Map2D descriptors. For retuned tables (values changed) the
  confidence stays medium/low. The address can be off by a few bytes in
  layout-transition zones.
- **32000 (N3M5E)** is the worst case: short cal span (0x71500→0x7DAFF),
  non-uniform drift, 17 unmapped tables and 775 low-confidence mappings. Redo it
  with dedicated analysis (descriptors) if editorial use is required.
- Duplicated axes/tables (same sequences reused by several tables) can produce
  multiple exact matches. The per-curve disambiguation resolves them in most
  cases but is not guaranteed.
- `cal_tables.csv` includes 662 X/Y axes and 548 tables: for the "Table 3D" (87)
  the true size (from the descriptor) is unknown; the verification window uses
  the extent up to the next entry (cap 512 B).

## How it was generated

```bash
python3 /tmp/opencode/rx8/map_final.py   # reads symbols/cal_tables.csv + roms/stock/*.bin
```

Regenerable in ~60 s, stdlib-only. If the script is ever committed, move it to
`web/explorer/tools/` and document the input (no repository file is modified:
the outputs go only into `web/explorer/data/`).

## Suggested next step

1. Extend `web/explorer/build_site.py` to read `table_addr_map_long.csv` and
   `roms_meta.json`. Add the ability to choose the firmware model in the
   "Calibration Tables" tab (values extracted from the chosen ROM + mapped
   addresses).
2. For 32000: extract the Map1D/Map2D descriptors from the ROM itself (scan for
   the pointers to the tables) to raise the confidence from low to medium/high.
3. Cross-validate against the 60E1D400 descriptors (499 tables with a
   descriptor) → report the *element size* (u8/u16/f32) per table in the CSV
   to help the UI display the values.
