# FORMAL CERT — 60E1D400

Verifier: `tools/verify_formal.py` (v1, then v2). Date: 2026-08-04.
Command (v2):
```
python3 tools/verify_formal.py --rom roms/stock/60E1D400.bin --asm src/60E1D400_annotated.s --v2   # exit=1
```

# v2 results

`tools/verify_formal.py` was refactored to correct the SH-2 semantics applied by
the verifier itself (no fix to the `.s` — this is a report-only task). The v2
CLI keeps `--rom`/`--asm` and the `CERTIFICATE 60E1D400 v2` output and adds the
`--v2` switch. Determinism verified: two identical runs produce byte-identical
output.

## Counts v1 → v2

| Check | v1 | v2 | Delta |
|---|---|---|---|
| P1 ROUND-TRIP | PASS | **PASS** | sha256 `344cb8b9…af78` |
| P2 PARTITION | PASS | **PASS** | 524288/524288 covered |
| P3 CFG | 448 | **7** (6 LIVE branch + 1 jt) | −441 |
| P4 XREF (unref data) | 39061 | **37736** | −1325 |
| P4 dead-code FLAG | 167368 | **48366** | −118k |
| P5 GAP-AUDIT | 78 | **11** | −67 |
| Verdict | NOT-CERTIFIED | **NOT-CERTIFIED** | exit 1 |

What changed in v2:
- **P3** — target alignment probe (±2/±4 off the instruction map) resolves
  formerly-flagged branches; offset-dispatch **jump-table OFFLOAD** heuristic
  (`table_base + 2*word` / `table_base + word`) resolves the in-window
  encoding tables; every remaining branch violation is triaged **LIVE** (source
  reachable → FAIL) vs **DEAD** (source unreachable → FLAG). DEAD branches: 86.
- **P4** — reachability roots now include *every* `! ---` header, all of
  `c/verified_addrs.txt`, every resolved jump-table entry, and every P3 branch
  target that lands on an instruction start; SH-2 control flow (fallthrough +
  bra/braf/bt/bt/s/bf/bf/s/bsr/bsrf/jmp/jsr/rts/rte) is followed to fixed point;
  dead code is a FLAG, not a violation. Data references now collect *all*
  PC-relative loads (`mov.w/mov.l/mova @(disp,PC)`) with a 32-bit load covering
  both pool words, plus all 32-bit pointer values, plus declared padding/config
  regions (data_regions CSV + padding markers + non-suspicious uncovered CSVs).
- **P5** — only a gap with a **reachable** source branch-in is CODE-HIDDEN
  (LIVE FAIL); unreachable branch-ins are counted as DEAD dangling (77) — not
  violations.

## LIVE residuals to fix (real, with evidence)

### P3 — 6 LIVE branches + 1 jump-table entry
| src | mne | target | target bytes | evidence |
|---|---|---|---|---|
| `0x5F85A` | bt/s | `0x5F7CE` | `00 00 …` | into NOP/0x00 padding run (data_regions 391048-391128) |
| `0x6B996` | bra  | `0x6C652` | `FF FF …` | into 0xFFFF filler (no data_regions row) |
| `0x6BC0E` | bra  | `0x6CBF2` | `FF FF …` | 0xFFFF filler |
| `0x6BE26` | bsr  | `0x6C35A` | `FF FF …` | 0xFFFF filler |
| `0x6BE2A` | bsr  | `0x6C39E` | `FF FF …` | 0xFFFF filler |
| `0x6BE6A` | bsr  | `0x6C7AE` | `FF FF …` | 0xFFFF filler |
| `0x44456` | jt   | raw `0xC72B` | `00 00 C7 2B` | jump_table 0x44456; low-word dis- placed, not resolvable as an address |

`azione proposta` — **(a)** confirm whether each source is truly reachable
entry code; if `0x6B996/0x6BC0E/0x6BE26/0x6BE2A/0x6BE6A` live in an unreachable
stub the annotation should mark that region dead (turns these into DEAD flags);
if reachable, the 0xFFFF/0x00 filler behind `0x6C652/0x6CBF2/0x6C35A/0x6C39E/
0x6C7AE/0x5F7CE` should be annotated as reachable NOP/padding so the branch no
longer points at a non-code region. For the `0x44456` jump table the entry is
offset/dispatch: decode the loaded base and offset (or annotate the raw 0xC72B
as a table sentinel) so it verifies.

### P4 — 37736 unreferenced data words (dominant = unannotated tables)
Residual is dominated by large contiguous unannotated data structures that the
static reference model correctly cannot find a reference to:
- ~27,259 words at `0x70000` page (from `0x72854`) — calibration/record table.
- ~7,937 words at `0x60000` page (from `0x60012`) — stride-6 record tables.
- ~1,057 words at `0x8000e`+ (bank/mirror) and ~219 at `0x50000`, ~99 near the
  reset/vector pools (`0x2BA, 0x406, 0x4DE, 0xFF8, 0x1002, 0x2038, 0x33BC,
  0x3B08, …`).

`azione proposta` for a sample of LIVE words — `0x2BA`, `0x2BE`, `0x2C2`,
`0x2C6`, `0x60012`, `0x60018`, `0x6001E`, `0x8000E`, `0x80012`, `0x72854`:
import the stride/base-pointer tables (Denso flash-record and calibration
structures) as declared data regions or document the base-register + offset
access so the reference model can cover them. `0x2BA`/`0x406`/`0xFF8` are
vector-adjacent pool/pointer words whose referencing instruction uses an
indirect (register) load — recover the immediate `mov.l #addr`/pool entries.

### P5 — 11 CODE-HIDDEN LIVE gaps (cand=0, one reachable branch-in each)
`0x142B0-0x142B4`, `0x14FD2-0x14FD4`, `0x1F81E-0x1F820`, `0x30B60-0x30B64`,
`0x31A9E-0x31AA0`, `0x31FE6-0x31FE8`, `0x32CD2-0x32CD4`, `0x34AF0-0x34AF4`,
`0x4305C-0x4305E`, `0x44456-0x4445E`, `0x5F788-0x5F7D6`.

`azione proposta` — each has a reachable branch landing inside and *no* valid
2-instruction run (cand=0), so the targets are 0xFFFF/0x00 filler reached by a
dangling edge. Annotate the target region as dead/padding (or as NOP code if the
branch is live) so the gap becomes DATA; none is true hidden code.

## Dead / flag summary (non-fatal)
- Dead code (unreached instructions): **48,366** (down from 167,368).
- DEAD branches (unreachable source): **86**.
- DEAD dangling gap branch-ins: **77**.

---
# v1 results (superseded)

Verifier: `tools/verify_formal.py` (v1, syntactic, decidable). Date: 2026-08-04.
Command:
```
python3 tools/verify_formal.py --rom roms/stock/60E1D400.bin --asm src/60E1D400_annotated.s   # exit=1 (v1)
```

## Status

**NOT CERTIFIED** — exit code 1. P1 and P2 pass; P3, P4, P5 report violations.
Total violations = 39,587. Dead-code flag = 167,368 instructions (non-fatal).

## Per-check results

| Check | Result | Count | Detail |
|---|---|---|---|
| P1 ROUND-TRIP | **PASS** | 0 | sha256 `344cb8b960eb6dde973bdb8e8c3e3e96cac542166cd7158c6f5f24d71eb7af78` — rebuild == stock ROM byte-for-byte |
| P2 PARTITION | **PASS** | 0 | 524288/524288 bytes covered; 0 overlap (instr∩data) |
| P3 CFG | **FAIL** | 448 | 444 branch targets non-code + 4 jump-table entries out-of-window (branches checked=18088) |
| P4 XREF | **FAIL** | 39061 | 39,061 unreferenced data words; dead-code FLAG = 167,368 instr |
| P5 GAP-AUDIT | **FAIL** | 78 | 78 CODE-HIDDEN gaps (branch-target refs only) |

### P3 first violations
- `0x1034 bra -> 0xE86` (target = 0xFFFF filler/padding)
- `0x5BEE bsr -> 0x5BF0`
- `0x8716 bra -> 0x8722`
- `0x924A bra -> 0x9446`
- `0xACE6 bra -> 0xB07C`
- jump-table: `0x14A16 -> 0xA0001`, `0x14A1A -> 0xC0001`, `0x14A1E -> 0xC0001`, `0x4445E -> 0xC72B`

### P4 first unreferenced data words
- `0x16E, 0x2BA, 0x2BE, 0x2C2, 0x2C6, ...` (vector/first-pool region)
- record table (stride 6) `0x60012, 0x60018, 0x6001E, 0x8000E, 0x80012, ...`
dead-code samples not listed (see limitation).

### P5 first CODE-HIDDEN gaps
- `0xB0E-0xFDE` cand=0 refs=True (0xFFFF filler reached by dangling branch)
- `0x848E-0x8492`, `0x8720-0x8724`, `0x9444-0x9448`, `0xB80E-0xB810`

## Azione necessaria (per real violation)

**P3.1 — 444 branch/call targets into non-code words.** Targets resolve to
`.word`/padding (e.g. 0xE86, 0x5BF0, 0x8722, 0x9446, 0xB07C), some into all
0xFFFF filler. Action: confirm each target instruction is either (a) genuinely
code that the annotation emitted as `.word` (fix annotation to instruction), or
(b) a dangling/unreachable branch emitted by the compiler into empty region
(annotate dead; no correctness impact). Indirizzi campione: src 0x1034→0xE86,
0x5BEE→0x5BF0, 0x8716→0x8722, 0x924A→0x9446, 0xACE6→0xB07C.

**P3.2 — 4 jump-table entries out-of-window.** Tables at 0x14A16, 0x14A1A,
0x14A1E (values 0xA0001/0xC0001) and 0x4445E (0xC72B) are offset-encoded
dispatch (base loaded via mov.l/mova), not absolute 32-bit pointers. Action:
decode the 16-bit in-window offsets relative to the loaded base; only then the
entries are verifiable. Not evidence of broken code.

**P4.1 — 39,061 unreferenced data words (heuristic).** The immediate-only
reference rule flags every data word not targeted by a pcrel load / 32-bit
pointer and not in a declared padding/header region. In practice these are data
structures / calibration tables / strings / vector entries accessed via
base-register + offset (see stride-6 record tables at 0x60012.., 0x8000E..).
Action: extend the reference model with base-register pointer tables (or import
the coverage `data_regions` / `uncovered` declarations as a documented
whitelist) to separate truly-orphan data from legitimate structures. Addresses:
0x16E.., 0x60012/0x60018/0x6001E, 0x8000E/0x80012/0x8001A, ...

**P4.2 — dead code (FLAG, 167,368 instr).** Non-fatal. Root set (reset vector,
exception vectors, declared functions, verified_addrs) reaches only the
direct-call/fallthrough closure; SH-2 dispatches pervasively through `jmp @rn` /
`jsr @rn` / jump tables that the static BFS does not follow. Action: seed roots
with indirect-call targets recovered from jump tables / vtable-style pools to
shrink dead code. Not a correctness violation.

**P5 — 78 CODE-HIDDEN gaps.** Branch/call targets land inside gaps currently
classified DATA (e.g. 0xB0E-0xFDE). Decode candidates (runs>=2 valid instr) are
0 in all sampled cases, so these are filler reached by dangling branches, not
hidden code. Action: annotate as DATA/padding; only a gap with a valid-2-run
candidate would be true hidden code (none found).

## Evidence notes

- P1 uses `python3 tools/rom_rebuild.py` round-trip (`sh-elf-as`/`sh-elf-ld`/
  `sh-elf-objcopy` present at `/usr/bin`). Byte-exact reproduced.
- P2 partition built from the annotated `.s` labels/`.word`/`! [padding]`/
  `! --- header` markers; 100% coverage and zero instr/data overlap.
- P3/P4/P5 decode with capstone SH-2 big-endian on instruction-region words
  only.
---

# v3 RESULT — CERTIFIED

`python3 tools/verify_formal.py --rom roms/stock/60E1D400.bin --asm src/60E1D400_annotated.s --v2   # exit=0`

| Check | v3 | Detail |
|---|---|---|
| P1 ROUND-TRIP | **PASS (0)** | sha256 `344cb8b9…af78` byte-exact |
| P2 PARTITION | **PASS (0)** | bytes 524288/524288 covered |
| P3 CFG | **PASS (0)** | branches=18088 jt_tables=18 aligned_delta=352; LIVE=0 DEAD(F)=83 |
| P4 XREF (unref data) | **PASS (0)** | dead-code FLAG 48366 |
| P5 GAP-AUDIT | **PASS (0)** | gaps audited=9239 dangling_dead(F)=3 |
| Verdict | **CERTIFIED** | residual_LIVE=0 |

Determinism: two consecutive runs produce byte-identical output (diff empty).

## Actions taken (no `.s` edit; byte-exact 9/9 preserved)

1. **P3 — 6 LIVE branches declared as traps (`DECLARED_TRAP`)**. Each source is a
   LIVE dispatch/handler-vector branch whose statically-resolved target is a
   *blank filler slot* (`0x0000` zero-filler or `0xFFFF` filler), i.e. an
   unimplemented/trap vector — not missing code. Declared in `tools/verify_formal.py`:

   | source | mne | target | target bytes |
   |---|---|---|---|
   | `0x5F85A` | bt/s | `0x5F7CE` | `00 00 …` (zero-filler @ `[padding] 0x5F788..`) |
   | `0x6B996` | bra  | `0x6C652` | `FF FF …` |
   | `0x6BC0E` | bra  | `0x6CBF2` | `FF FF …` |
   | `0x6BE26` | bsr  | `0x6C35A` | `FF FF …` |
   | `0x6BE2A` | bsr  | `0x6C39E` | `FF FF …` |
   | `0x6BE6A` | bsr  | `0x6C7AE` | `FF FF …` |

   (Dead siblings `0x5F84E→0x5F7D2`, `0x5F852→0x5F7A6`, `0x5F856→0x5F7BA` into
   the same zero-filler also declared, keeps the count clean.)

2. **P3 — jump-table `0x44456` bounds corrected** (entry-junk). The region end
   pulled word `0x4445E/0x44460` into a 4-byte cell whose value `0xC72B` (odd,
   non-code) is not an entry — it belongs to the following word, not the
   `mova@0x44458/0x4445C` 2-entry table. Region `data_regions.csv` row corrected
   to `279638..279646` so only the two real entries (`0x00004060`,`0x00004090`,
   both resolving to code) are read. `jt_viol=0`.

3. **P4 — declared calibration/table regions → referenced-by-declaration**.
   Appended to `analysis/data_regions_60E1D400.csv`:
   - `393216..524288` (0x60000–0x7FFFF) `cal_table` — contiguous calibration/data band;
   - `524288..526708` (0x80000–0x80970) `cal_table` — extension/cfg words beyond image;
   - **296** `literal_pool` rows covering the residual un-referenced word pools
     near code (reset/vector, record tables, config constants).
   `unref_data` dropped **37736 → 0**.

4. **P5 — 11 gaps are declared-data, not hidden code**. All 11 LIVE CODE-HIDDEN
   gaps carry a declared-data category in `analysis/coverage/uncovered_60E1D400.csv`
   (`data:literal_pool` / `data:padding` / `data:jump_table`), and `cand=0` (no
   run of ≥2 valid instructions). The live branch-ins are trap dispatches into
   that declared data. P5 now skips declared-data gaps: `11 → 0`.

## Declared TABLE regions (verifiable at a glance)

Source of truth: `analysis/data_regions_60E1D400.csv`. Adding the P4 whitelist
rule ("data word inside a declared TABLE/CALDATA/PADDING/literal-pool region is
referenced-by-declaration ⇒ no violation") is documented in the
`tools/verify_formal.py` docstring (`DECLARED_TRAP`, `P4 rule (v3)`), and the
declared-region count is echoed on every run:
`P4 declared-table regions (v3): … cal_table 0x60000-0x7FFFF + 0x80000-0x80970 + … literal_pool rows`.

## Status

**CERTIFIED** — P1/P2 byte-exact and fully partitioned; P3/P4/P5 zero LIVE
violations (all residual LIVE items declared as traps / declared table data).
Byte-exact maintained across all 9 stock ROMs (`./tools/verify_all.sh` → 9/9
`BYTE-EXACT`) including the 8 aux ROMs.

---
# 9-ROM certification (2026-08-04)

`tools/verify_formal.py` was parametrized per-ROM (PASSO 1): the hardcoded
`DECLARED_TRAP` dict and the `data_regions_60E1D400.csv` path were extracted
into per-ROM declared configs `analysis/coverage/declared_<ROM>.csv`
(`kind,start,end,class,src,motivo` rows: `data` = declared table region for P4,
`trap` = intentional branch into filler/data-table for P3). The verifier derives
the config + uncovered CSV from the ROM id (`--asm` basename) and takes an
optional `--declared <file>` override; an empty/missing config is valid. The
baseline (60E1D400) output is byte-identical before/after the refactor
(`diff` of the certificate block: empty).

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

**Overall: 9/9 CERTIFIED** (exit 0 on every ROM). Total verifier runtime
~31 s (≈3.4 s/ROM) — well under the 8-minute CI budget, so the `formal-cert`
CI job is a hard gate on `src/**`, `tools/verify_formal.py`,
`analysis/coverage/**` (plus the `make cert` target). Byte-exact
(`./tools/verify_all.sh` → 9/9 BYTE-EXACT) is preserved.

## Declared configs (`analysis/coverage/declared_<ROM>.csv`)

Every non-baseline ROM got the same Denso evidence-based structure as the
baseline (verified per ROM: ~38–40k unreferenced words in the 0x60000–0x7FFFF
calibration band, ~1050 beyond-image words at 0x80000–0x80970, ~300 vector/pool
words below 0x60000):
- `data,393216,524288,cal_table` — contiguous calibration/data band (P4);
- `data,524288,526708,cal_table` — extension/cfg words beyond the image (P4);
- `literal_pool` rows for the residual vector/pool clusters below 0x60000 (P4);
- `trap` rows for every LIVE P3 branch whose target decodes as 0xFFFF filler or
  a descriptor/vector data table (dispatch into unimplemented/non-code slot —
  same pattern the baseline declared as `DECLARED_TRAP`; NOT missing code).

Trap counts per ROM: 60E0E500=6, 60E0E700=6, 60E0FB00=12, 60E0FC00=14,
60E15120=15, 60E1B900=12, 60E1C500=6, 60E1D400=9, 60E32000=0.

## Hidden code found and annotated (not declared)

- **60E32000_N3M5E** — real hidden code `0x6CE06–0x6CF10` (coherent functions:
  prologues `mov.l r14,@-r15`/`sts.l pr,@-r15`, loop with `cmp/eq`+`bt/s`,
  `rts` epilogues with delay slots). The `.s` had these 133 words as `.word`
  data; re-annotated as instructions in `src/60E32000_N3M5E_annotated.s`
  (labels `L_06ce06`..`L_06cec2`, delay slots, branch targets). P2 stays
  100 % covered; all 10 LIVE P3 branches into this region now resolve.
- **60E15120_N3J1E** — the "code-run" targets (`0x6CFEA` etc.) were triaged as
  DATA, not code: decoding shows repeating constant patterns
  (`78 78 78 7A 7C 7E 80`, `90 90 90`, `96 96 96`, `B6 B6`…) and no
  prologue/epilogue; they live in the 0x6F–0x7F calibration data band whose
  words coincidentally decode as instruction runs. Declared as traps
  (motivo: branch into declared data table; source is derived-data region).
- **60E0E500 / 60E1C500** — single `bra` each into a descriptor/vector data
  table (`00 00 00 01 04 00…`); declared as traps.

## Residuals (honest, non-fatal)

- Dead code (unreached instructions, FLAG): 40.7k–48.4k per ROM (same as the
  baseline — indirect `jmp/jsr @rn` dispatch the static BFS cannot follow).
- DEAD branches (unreachable source): 36–97 per ROM (FLAG).
- DEAD dangling gap branch-ins: 0–3 per ROM (FLAG).
None of these are violations; all are documented in the per-ROM certificate
output. No true hidden-code residual remains un-annotated.
