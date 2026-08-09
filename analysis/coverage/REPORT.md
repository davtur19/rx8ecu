# REPORT — Coverage-gap analysis: the uncovered `.word` words

**Date:** 2026-08-01 · **Scope:** all 9 stock ROMs, window `0x800..0x60000`
**Deliverable:** classify the "uncovered instructions" gap (~6.4%) and make it recoverable.
**Safety:** read-only to `c/ docs/ tools/ src/*.s`; only script created: `analysis/coverage/coverage_gap.py`; output in `analysis/coverage/`.

---

## 1. How coverage is measured

Declared coverage (for example `60E1D400` = **93.63%**) is a *round-trip coverage* produced by
`tools/rom_rebuild.py` / `tools/organize_src.py`, frozen into `src/*_annotated.s`:

1. Linear sweep at every even offset of `0x800..0x60000` (195,584 words/ROM).
2. Decode with capstone (SH-2) + `disasm_sh2e.py` fallback.
3. GNU-as self-correction: any word `sh-elf-as -big` rejects/re-encodes differently is forced
   to `.word 0xNNNN`. The `.s` = ground truth of "covered".

93% **includes** words that are data but decode as instructions (§5: ~4-6% of "covered" words are
tables decoded as code).

Reproduced by `coverage_gap.py` (exact match with declared values):

| ROM | declared % | reproduced % | uncovered (words) | forced→.word | cluster |
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

Gap is identical across ROMs (12.1–12.8k words): a **structural feature of the firmware**, not a per-ROM artifact.

---

## 2. What the 12,464 uncovered words of `60E1D400` are

Per-word classification (pcrel/branch refs, labels, values, neighborhood) + manual verification:
**100% data, not code.**

| Category | words | % | cluster | notes |
|---|---|---|---|---|
| `data:pool_single` | 6,478 | **51.97%** | 6,478 | 16-bit constants via `mov.w @(disp,PC)`, no table placeholder |
| `data:literal_pool` | 2,282 | 18.31% | 883 | 16-bit literal pools (in `data_regions_60E1D400.csv`) |
| `data:padding` | 1,540 | 12.36% | 366 | filler runs (dominated by `0xFFFF`) |
| `data:unknown_data` | 782 | 6.27% | 218 | unreferenced data (config/calibration) |
| `data:padding_single` | 749 | 6.01% | 749 | isolated single filler words |
| `data:single_unref` | 463 | 3.71% | 463 | isolated words never referenced |
| `data:jump_table` | 107 | 0.86% | 23 | jump tables (ROM addresses, via switch) |
| `data:table_member` | 30 | 0.24% | 30 | members of 16-bit tables (0x82nn/0x86nn or near 0x0007/0x0009) |
| `label_on_data` | 24 | 0.19% | 24 | symbol labels resting on data |
| `data:string` | 7 | 0.06% | 3 | strings |
| `instr_forced` | 2 | 0.02% | 2 | decodable residue (verified: table, §4) |
| **TOTAL** | **12,464** | **100%** | 9,239 | = 24,928 bytes |

**Summary by value:** **79.02%** (9,849 words) is `0xFFFF`/`0x0000`; then `0x0001`, `0x0100`, `0x0200`
(masks/config), `0x8C2C` (addresses).

**Cluster structure:** 9,239 clusters, avg 1.3 words. Largest:

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

**31.88%** of the gap (3,974 words) is **inside named-function ranges**: pools/tables *inline* at
function edges (for example `0x27F68`, `0x51C44`, `0x50CAA`).

**Reset/exception vectors:** 20 entries in window, **0 point to uncovered words** → no handler lost as data.

---

## 3. The "decodable but forced" words (252)

Force-loop also leaves `.word` for words that decode as valid SH-2E instructions (GNU-as re-encodes
differently/rejects). Breakdown in D400:

- **241 (95.6%)** are `mov.l` **`0x82nn` / `0x86nn`** (16-bit disp): not assemblable by GNU-as
  (toolchain lacks SH-2E extensions).
- **11** are rare opcodes (`ldc`/`stc`/`synco`/`movua`/`mulr`/`divs`/`divu`), for example `0x403E` (`ldc r0,SSR`),
  `0x0132` (`stc SSR,r0`), `0x014B` (`synco`).

Manual verification of all D400 occurrences → data, not code:
- `0x86xx` pairs with `0x0007`/`0x0009` markers (for example `0x31064–0x3107C`, `0x31196`, `0x31406`) — div-library
  *register-save table* (16-bit rows).
- The two `0x403E` words (`0x4300`, `0x44D8`) sit in structured tables (values decreasing by 4 at `0x42F0`).

**Real instructions stranded as `.word` = 0** (`instr_forced` residue 0–2 words, always table members).
The project writes `.word` **correctly**. The cause is not a decode gap. The GNU-as toolchain does not know SH-2E.
Recovery yields **zero** extra code.

---

## 4. Answer: "what are the ~6.4%, how recoverable?"

**What:** 6.37% = 12,464 words = **pure data** (pools, padding, tables, config). No real uncovered instruction.

**Recoverability:**
- **~52%** (`pool_single`) + **~19%** (`literal_pool`): pools/constants already referenced by `mov.w @(disp,PC)` — legitimately excluded data; they re-enter only if the coverage definition changes (`@pool`).
- **~31%** (padding + padding_single + single_unref + unknown_data + strings): never-referenced filler (`0xFFFF`/`0x0000` ≈79% of gap). Unrecoverable as instructions — and should not be.
- **~1%** (`jump_table` + `table_member` + `label_on_data`): tables.
- **`instr_forced` 2 words (0.02%)**: verified table members → nothing to recover.

The force-loop already recovered all possible code; the residue is 100% data and **93.63% coverage is saturated** from an instruction-decode standpoint.

---

## 5. Opposite direction: *non-code* counted as *covered*

Data markers `0x0004/0x0005/0x0006/0x0007` (`mov r0,@(r0,r0)` / `mul.l r0,r0`, a sequence never used as
code) get decoded and counted covered:

| value | "covered" words |
|---|---|
| `0x0007` (`mul.l r0,r0`) | 3,519 |
| `0x0006` (`mov.l r0,@(r0,r0)`) | 2,198 |
| `0x0005` (`mov.w r0,@(r0,r0)`) | 976 |
| `0x0004` (`mov.b r0,@(r0,r0)`) | 491 |
| **total** | **7,184 = 3.92% of covered** |

If we add the `0x0008`/`0x0009` separators and the mis-decode regions (for example `0x30F30–0x31550`, 734 covered
words are tables), the honest estimate of "real" code is **~88–91%** of the window. A more honest
number, if wanted, would be **lower**, not higher.

---

## 6. Recommendations

1. **No action on decoding**: the gap contains no instructions; no decompilation work to do. Close the task.
2. **Do not "recover" the gap**: if you mark pools/padding as data (for example `@pool`), the change is cosmetic (at `0x60000`
   there is no code to run) and would **lower** the honest 93%.
3. **Toolchain note**: if the 241 `0x82nn/0x86nn` words were ever assembled as SH-2E, a custom emitter
   or newer binutils is needed. At present the words are correctly `.word`.
4. **Reproducibility**: `coverage_gap.py` regenerates the 9-ROM table in ~40 s + per-ROM CSV/TXT
   (`uncovered_<ROM>.{csv,txt}`).

---

## 7. Produced files

| file | contents |
|---|---|
| `analysis/coverage/coverage_gap.py` | reproduces round-trip coverage, classifies gap, generates output (only new script) |
| `analysis/coverage/uncovered_60E1D400.{csv,txt}` | 12,464 D400 words: per-word (csv) / per-category with clusters (txt) |
| `analysis/coverage/uncovered_60E32000_N3M5E.{csv,txt}` | same for second ROM |
| `analysis/coverage/REPORT.md` | this report |

**Open issues / uncertainties:**
- `data_regions_60E1D400.csv` categories exist only for D400; other ROMs use coarser script heuristics
  (classes `pool_unclassified`, `padding_pattern`, `run_unclassified`), equivalent outcomes.
- "Real code ~88–91%" is an indicative bound; exact covered-data count needs a human annotator.
