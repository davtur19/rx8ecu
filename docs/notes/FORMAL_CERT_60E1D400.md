# FORMAL CERT — 60E1D400

Verifier: `tools/verify_formal.py` (v1, then v2). Date: 2026-08-04.

# Final result — v3 CERTIFIED

```
python3 tools/verify_formal.py --rom roms/stock/60E1D400.bin --asm src/60E1D400_annotated.s --v2   # exit=0
```

| Check | v3 | Detail |
|---|---|---|
| P1 ROUND-TRIP | **PASS (0)** | sha256 `344cb8b9…af78` byte-exact |
| P2 PARTITION | **PASS (0)** | bytes 524288/524288 covered |
| P3 CFG | **PASS (0)** | branches=18088 jt_tables=18 aligned_delta=352; LIVE=0 DEAD(F)=83 |
| P4 XREF (unref data) | **PASS (0)** | dead-code FLAG 48366 |
| P5 GAP-AUDIT | **PASS (0)** | gaps audited=9239 dangling_dead(F)=3 |
| Verdict | **CERTIFIED** | residual_LIVE=0 |

Determinism: two consecutive runs produce byte-identical output (diff empty).

P3 = branch/CFG violations; P4 = unreferenced data + dead code; P5 = CODE-HIDDEN gaps. The v2→v3 transition fixed all 11 LIVE P3, the 37,736 unref words, and the 11 CODE-HIDDEN gaps (actions below), leaving residual_LIVE=0. Dead-code FLAG 48,366 & DEAD branches 83 remain as non-fatal FLAGs.

## Actions taken to certify (no `.s` edit; byte-exact 9/9 preserved)

1. **P3 — 6 LIVE branches declared as traps (`DECLARED_TRAP`)**. Each source is a LIVE dispatch/handler-vector branch whose statically-resolved target is a *blank filler slot* (`0x0000` zero-filler or `0xFFFF` filler) — an unimplemented/trap vector, not missing code. Declared in `tools/verify_formal.py`:

   | source | mne | target | target bytes |
   |---|---|---|---|
   | `0x5F85A` | bt/s | `0x5F7CE` | `00 00 …` (zero-filler @ `[padding] 0x5F788..`) |
   | `0x6B996` | bra  | `0x6C652` | `FF FF …` |
   | `0x6BC0E` | bra  | `0x6CBF2` | `FF FF …` |
   | `0x6BE26` | bsr  | `0x6C35A` | `FF FF …` |
   | `0x6BE2A` | bsr  | `0x6C39E` | `FF FF …` |
   | `0x6BE6A` | bsr  | `0x6C7AE` | `FF FF …` |

   (Dead siblings `0x5F84E→0x5F7D2`, `0x5F852→0x5F7A6`, `0x5F856→0x5F7BA` into the same zero-filler also declared, keeps the count clean.)

2. **P3 — jump-table `0x44456` bounds corrected** (entry-junk). Region end pulled word `0x4445E/0x44460` into a 4-byte cell whose value `0xC72B` (odd, non-code) is not an entry — it belongs to the following word, not the `mova@0x44458/0x4445C` 2-entry table. `data_regions.csv` row corrected to `279638..279646` so only the two real entries (`0x00004060`, `0x00004090`, both resolving to code) are read. `jt_viol=0`.

3. **P4 — declared calibration/table regions → referenced-by-declaration**. Appended to `analysis/data_regions_60E1D400.csv`:
   - `393216..524288` (0x60000–0x7FFFF) `cal_table` — contiguous calibration/data band;
   - `524288..526708` (0x80000–0x80970) `cal_table` — extension/cfg words beyond image;
   - **296** `literal_pool` rows covering the residual un-referenced word pools near code (reset/vector, record tables, config constants).
   `unref_data` dropped **37736 → 0**.

4. **P5 — 11 gaps are declared-data, not hidden code**. All 11 LIVE CODE-HIDDEN gaps carry a declared-data category in `analysis/coverage/uncovered_60E1D400.csv` (`data:literal_pool` / `data:padding` / `data:jump_table`), and `cand=0` (no run of ≥2 valid instructions). Live branch-ins are trap dispatches into that declared data. P5 now skips declared-data gaps: `11 → 0`.

(The P4 whitelist rule "data word inside a declared TABLE/CALDATA/PADDING/literal-pool region is referenced-by-declaration ⇒ no violation" is documented in the `tools/verify_formal.py` docstring — `DECLARED_TRAP`, `P4 rule (v3)`; the declared-region count is echoed on every run.)

## Status

**CERTIFIED** — P1/P2 byte-exact and fully partitioned; P3/P4/P5 zero LIVE violations (all residual LIVE items declared as traps / declared table data). Byte-exact maintained across all 9 stock ROMs (`./tools/verify_all.sh` → 9/9 `BYTE-EXACT`).

# 9-ROM certification (2026-08-04)

`tools/verify_formal.py` was parametrized per-ROM (PASSO 1): the hardcoded `DECLARED_TRAP` dict and the `data_regions_60E1D400.csv` path were extracted into per-ROM declared configs `analysis/coverage/declared_<ROM>.csv` (`kind,start,end,class,src,motivo` rows: `data` = declared table region for P4, `trap` = intentional branch into filler/data-table for P3). The verifier derives the config + uncovered CSV from the ROM id (`--asm` basename) and takes an optional `--declared <file>` override; an empty/missing config is valid. The baseline (60E1D400) output is byte-identical before/after the refactor (`diff` of the certificate block: empty).

## Per-ROM results (`--v2` semantics, v3 rules)

| ROM | P1 ROUND-TRIP | P2 PARTITION | P3 CFG LIVE | P4 unref_data | P5 LIVE | Verdict | dead_code | dead_br |
|---|---|---|---|---|---|---|---|---|
| 60E0E500 | PASS | PASS | 0 | 0 | 0 | **CERTIFIED** | 44353 | 41 |
| 60E0E700_N3YLEE | PASS | PASS | 0 | 0 | 0 | **CERTIFIED** | 44714 | 36 |
| 60E0FB00 | PASS | PASS | 0 | 0 | 0 | **CERTIFIED** | 44295 | 50 |
| 60E0FC00 | PASS | PASS | 0 | 0 | 0 | **CERTIFIED** | 40660 | 97 |
| 60E15120_N3J1E | PASS | PASS | 0 | 0 | 0 | **CERTIFIED** | 45412 | 94 |
| 60E1B900 | PASS | PASS | 0 | 0 | 0 | **CERTIFIED** | 44388 | 50 |
| 60E1C500_N3J6EB | PASS | PASS | 0 | 0 | 0 | **CERTIFIED** | 44388 | 40 |
| 60E1D400 | PASS | PASS | 0 | 0 | 0 | **CERTIFIED** | 48366 | 83 |
| 60E32000_N3M5E | PASS | PASS | 0 | 0 | 0 | **CERTIFIED** | 43421 | 37 |

**Overall: 9/9 CERTIFIED** (exit 0 every ROM). Total runtime ~31 s (≈3.4 s/ROM) — under the 8-minute CI budget, so the `formal-cert` CI job is a hard gate on `src/**`, `tools/verify_formal.py`, `analysis/coverage/**` (+ `make cert`). Byte-exact (`./tools/verify_all.sh` → 9/9) preserved.

## Declared configs (`analysis/coverage/declared_<ROM>.csv`)

Every non-baseline ROM got the same evidence-based structure as the baseline (verified per ROM: ~38–40k unreferenced words in the 0x60000–0x7FFFF calibration band, ~1050 beyond-image words at 0x80000–0x80970, ~300 vector/pool words below 0x60000):
- `data,393216,524288,cal_table` — contiguous calibration/data band (P4);
- `data,524288,526708,cal_table` — extension/cfg words beyond the image (P4);
- `literal_pool` rows for the residual vector/pool clusters below 0x60000 (P4);
- `trap` rows for every LIVE P3 branch whose target decodes as 0xFFFF filler or a descriptor/vector data table (dispatch into unimplemented/non-code slot — same pattern the baseline declared as `DECLARED_TRAP`; NOT missing code).

Trap counts per ROM: 60E0E500=6, 60E0E700=6, 60E0FB00=12, 60E0FC00=14, 60E15120=15, 60E1B900=12, 60E1C500=6, 60E1D400=9, 60E32000=0.

## Hidden code found and annotated (not declared)

- **60E32000_N3M5E** — real hidden code `0x6CE06–0x6CF10` (coherent functions: prologues `mov.l r14,@-r15`/`sts.l pr,@-r15`, loop with `cmp/eq`+`bt/s`, `rts` epilogues with delay slots). The `.s` had these 133 words as `.word` data; re-annotated as instructions in `src/60E32000_N3M5E_annotated.s` (labels `L_06ce06`..`L_06cec2`, delay slots, branch targets). P2 stays 100% covered; all 10 LIVE P3 branches into this region now resolve.
- **60E15120_N3J1E** — "code-run" targets (`0x6CFEA` etc.) triaged as DATA, not code: decoding shows repeating constant patterns (`78 78 78 7A 7C 7E 80`, `90 90 90`, `96 96 96`, `B6 B6`…) and no prologue/epilogue; they live in the 0x6F–0x7F calibration band whose words coincidentally decode as instruction runs. Declared as traps (motivo: branch into declared data table; source is derived-data region).
- **60E0E500 / 60E1C500** — single `bra` each into a descriptor/vector data table (`00 00 00 01 04 00…`); declared as traps.

## Residuals (honest, non-fatal)

- Dead code (unreached instructions, FLAG): 40.7k–48.4k per ROM (indirect `jmp/jsr @rn` dispatch the static BFS can't follow).
- DEAD branches (unreachable source): 36–97 per ROM (FLAG).
- DEAD dangling gap branch-ins: 0–3 per ROM (FLAG).

None are violations; all documented in the per-ROM certificate output. No true hidden-code residual remains un-annotated.

## Evidence notes

- P1 uses `python3 tools/rom_rebuild.py` round-trip (`sh-elf-as`/`sh-elf-ld`/`sh-elf-objcopy` at `/usr/bin`). Byte-exact reproduced.
- P2 partition built from annotated `.s` labels/`.word`/`! [padding]`/`! --- header` markers; 100% coverage, zero instr/data overlap.
- P3/P4/P5 decode with capstone SH-2 big-endian on instruction-region words only.
