# FORMAL CERT — 60E1D400

Verifier: `tools/verify_formal.py` (syntactic, decidable). Date: 2026-08-04.
Command:
```
python3 tools/verify_formal.py --rom roms/stock/60E1D400.bin --asm src/60E1D400_annotated.s   # exit=1
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