# REPORT — Coverage-gap analysis: the uncovered `.word` words

**Date:** 2026-08-01 · **Scope:** all 9 stock ROMs in the window `0x800..0x60000`
**Deliverable:** classify the "uncovered instructions" gap (~6.4%) and make it recoverable.
**Safety:** read-only access to `c/ docs/ tools/ src/*.s`; only script created: `analysis/coverage/coverage_gap.py`; output in `analysis/coverage/`.

---

## 1. How coverage is measured (exact method)

The declared coverage (e.g. `60E1D400` = **93.63%**) is a *round-trip coverage*, produced by
`tools/rom_rebuild.py` / `tools/organize_src.py` and frozen into the assembler `src/*_annotated.s`:

1. **Linear sweep** at every even offset of `0x800..0x60000` (195,584 words per ROM).
2. Decode with **capstone (SH-2)** + `disasm_sh2e.py` fallback.
3. **GNU-as self-correction**: every word that `sh-elf-as -big` *rejects* or *re-encodes with different
   bytes* than the original is forced to `.word 0xNNNN`. The resulting `.s` file is the ground truth
   of what is "covered" (the force-loop reproduces it 100%).

The 93% **includes** words that are data but *decode as instructions* (see §5: the "coverage
honesty" caveat is real: ~4-6% of "covered" words are tables decoded as code).

**Reproduced verification** by `coverage_gap.py` (exact match with the declared values):

| ROM | declared coverage% | reproduced coverage% | uncovered (words) | forced→.word | cluster |
|---|---|---|---|---|---|
| 60E0E500 | 93.50 | 93.498 | 12,716 | 246 | 9,373 |
| 60E0E700_N3YLEE | 93.46 | 93.458 | 12,796 | 326 | 9,384 |
| 60E0FB00 | 93.60 | 93.597 | 12,524 | 315 | 9,223 |
| 60E0FC00 | 93.57 | 93.565 | 12,586 | 377 | 9,231 |
| 60E15120_N3J1E | 93.65 | 93.654 | 12,412 | 294 | 9,165 |
| 60E1B900 | 93.57 | 93.566 | 12,583 | 308 | 9,208 |
| 60E1C500_N3J6EB | 93.48 | 93.477 | 12,758 | 253 | 9,387 |
| **60E1D400** | **93.63** | **93.627** | **12,464** | **252** | **9,239** |
| 60E32000_N3M5E | 93.80 | 93.800 | 12,126 | 265 | 8,937 |

The gap is identical across all ROMs (12.1–12.8k words): it is a **structural feature of the firmware**
(identical prologue, constant layout), not an artifact of a specific ROM.

---

## 2. What the 12,464 uncovered words of `60E1D400` (baseline) are

Per-word classification (heuristic: pcrel/branch references, labels, values, neighborhood) + manual
verification of ambiguous cases. **Conclusion: 100% data. Not code.**

| Category | words | % | cluster | notes |
|---|---|---|---|---|
| `data:pool_single` | 6,478 | **51.97%** | 6,478 | 16-bit constants referenced by `mov.w @(disp,PC)` with no table placeholder |
| `data:literal_pool` | 2,282 | 18.31% | 883 | 16-bit literal pools (already classified in `data_regions_60E1D400.csv`) |
| `data:padding` | 1,540 | 12.36% | 366 | filler runs (dominated by `0xFFFF`) |
| `data:unknown_data` | 782 | 6.27% | 218 | unreferenced data (config/calibration) |
| `data:padding_single` | 749 | 6.01% | 749 | isolated single filler words |
| `data:single_unref` | 463 | 3.71% | 463 | isolated words never referenced |
| `data:jump_table` | 107 | 0.86% | 23 | jump tables (ROM addresses, referenced via switch) |
| `data:table_member` | 30 | 0.24% | 30 | members of 16-bit tables (0x82nn/0x86nn values or near 0x0007/0x0009 markers) |
| `label_on_data` | 24 | 0.19% | 24 | symbol labels resting on data |
| `data:string` | 7 | 0.06% | 3 | strings |
| `instr_forced` | 2 | 0.02% | 2 | decodable residue (verified: table, see §4) |
| **TOTAL** | **12,464** | **100%** | 9,239 | = 24,928 bytes |

**Summary by value**: **79.02%** of the gap (9,849 words) is `0xFFFF`/`0x0000`
(filler/padding); the most common single values after those are `0x0001`, `0x0100`, `0x0200`
(masks/config), `0x8C2C` (addresses).

**Cluster structure**: 9,239 clusters, average 1.3 words. The largest:

| range | words | category |
|---|---|---|
| `0xB0E – 0xFDE` | 617 | padding `0xFFFF` |
| `0x5F702 – 0x5F776` | 59 | padding |
| `0x493C – 0x4994` | 45 | unknown_data (config) |
| `0x5F788 – 0x5F7D6` | 40 | padding |
| `0x1FC2 – 0x1FFE` | 31 | unknown_data |
| `0x4ED5C – 0x4ED82` | 20 | unknown_data |
| `0x4E946 – 0x4E968` | 18 | unknown_data |
| `0x5AAC – 0x5ACC` | 17 | literal_pool |

**31.88%** of the gap (3,974 words) is **inside named-function ranges**: they are pools/tables
*inline* at function edges (e.g. the dense patterns at `0x27F68`, `0x51C44`, `0x50CAA`), consistent with
the firmware emitting constants at the end of functions.

**Reset/exception vectors**: 20 entries fall in the window and **0 point to uncovered words**
→ no handler is "lost as data" through the vector.

---

## 3. The "decodable but forced" words (252) — the key point

The force-loop also leaves `.word` for words that **decode as valid instructions** (capstone reads them,
GNU-as re-encodes them differently or rejects them). Breakdown of the 252 in D400:

- **241 (95.6%)** are SH-2E `mov.l` **`0x82nn` / `0x86nn`** (16-bit disp): opcodes not assemblable
  by GNU-as (the toolchain lacks the SH-2E extensions).
- **11** are rare opcodes (`ldc`/`stc`/`synco`/`movua`/`mulr`/`divs`/`divu`), e.g. `0x403E` (`ldc r0,SSR`),
  `0x0132` (`stc SSR,r0`), `0x014B` (`synco`).

**Manual verification of all D400 occurrences → they are data, not code:**
- The `0x86xx` patterns appear in pairs with `0x0007`/`0x0009` markers (e.g. `0x31064–0x3107C`,
  `0x31196`, `0x31406`): this is the div-library *register-save table* (save/restore
  masks, 16-bit rows).
- The two `0x403E` words (`0x4300`, `0x44D8`) sit in **structured tables** (at `0x42F0` the values
  decrease by 4: `0x201E 0x1C1A 0x1816 0x1412 …`), again div-library tables.
- **Therefore: real instructions left stranded as `.word` = 0** (same outcome for all ROMs:
  `instr_forced` residue 0–2 words, always table members).

The project's `.word` writing is **correct**: it is not a decode gap, it is the GNU-as
toolchain not knowing SH-2E. Recovering them as instructions would yield **zero** extra code.

---

## 4. Answer to the question: "what are the ~6.4% and how recoverable are they?"

**What they are:** 6.37% = 12,464 words = **pure data** (pools, padding, tables, config). No
real uncovered instruction exists.

**Recoverability (how much "re-enters" coverage):**
- **~52%** (`pool_single`) and **~19%** (`literal_pool`): pools/constants already referenced by
  `mov.w @(disp,PC)`; they are *legitimately* excluded data — they would re-enter only by changing the
  coverage definition (e.g. marking them `@pool` instead of instructions).
- **~31%** (`padding` + `padding_single` + `single_unref` + `unknown_data` + strings): data never
  referenced (filler `0xFFFF`/`0x0000` for ~79% of the overall gap). Unrecoverable as
  instructions — and should not be recovered.
- **~1%** (`jump_table` + `table_member` + `label_on_data`): tables; same considerations as pools.
- **`instr_forced` 2 words (0.02%)**: verified = table members → nothing to recover.

**In one sentence:** the force-loop has already "recovered" all possible code; the residue is 100% data
and the 93.63% coverage is **saturated** from an instruction-decode standpoint.

---

## 5. Opposite direction (coverage "honesty"): there is *non-code* *counted as covered*

The `VERIFICATION.md` caveat is measurable: words with the data markers `0x0004/0x0005/0x0006/0x0007`
(`mov r0,@(r0,r0)` / `mul.l r0,r0`, a sequence never used as code) get **decoded and counted
covered**:

| value | "covered" words |
|---|---|
| `0x0007` (`mul.l r0,r0`) | 3,519 |
| `0x0006` (`mov.l r0,@(r0,r0)`) | 2,198 |
| `0x0005` (`mov.w r0,@(r0,r0)`) | 976 |
| `0x0004` (`mov.b r0,@(r0,r0)`) | 491 |
| **total** | **7,184 = 3.92% of covered** |

Adding the `0x0008`/`0x0009` separator patterns and the known mis-decode regions
(e.g. `0x30F30–0x31550`, 734 covered words, are tables), the honest estimate of "real" code is
**~88–91%** of the window. If a *more honest* number were ever wanted, it should be **lowered**
by labeling these words as data, not raised.

---

## 6. Recommendations

1. **No action on decoding**: the gap contains no instructions; there is no
   decompilation work to do on the uncovered words. Close the task with the classification documented
   here.
2. **Do not "recover" the gap**: marking pools/padding as data (e.g. `@pool` labels, defined bytes)
   is *cosmetic* (at `0x60000` there is no code to run) and would **lower** the honest 93%.
3. **Toolchain note**: if the 241 `0x82nn/0x86nn` words were ever to be assembled as
   SH-2E instructions, a custom emitter or a more recent binutils would be needed; for now they are
   correctly `.word` (they are data).
4. **Reproducibility**: `coverage_gap.py` regenerates the full 9-ROM table in ~40 s and the per-ROM
   CSV/TXT (`uncovered_<ROM>.{csv,txt}`); reusable to re-verify after any `.s` change.

---

## 7. Produced files

| file | contents |
|---|---|
| `analysis/coverage/coverage_gap.py` | reproduces the round-trip coverage, classifies the gap, generates output (the only new script) |
| `analysis/coverage/uncovered_60E1D400.{csv,txt}` | 12,464 D400 uncovered words: per-word (csv) and per-category with clusters (txt) |
| `analysis/coverage/uncovered_60E32000_N3M5E.{csv,txt}` | same for the second ROM |
| `analysis/coverage/REPORT.md` | this report |

**Open issues / uncertainties:**
- The CSV categories of `data_regions_60E1D400.csv` are only available for D400; for the other ROMs the
  classification uses the script heuristics (slightly "coarser": the classes
  `pool_unclassified`, `padding_pattern`, `run_unclassified` appear), with equivalent outcomes.
- The "real code ~88–91%" estimate is an indicative lower/upper bound: it would require a
  human annotator for the exact count of covered data words.
