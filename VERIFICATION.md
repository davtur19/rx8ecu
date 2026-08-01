# VERIFICATION — evidence that the release does what it claims

Everything in this file was re-measured on 2026-07-31 with the shipped
toolchain (sh-elf binutils 2.46) and capstone 5.0.7 / Python 3.14, and
**re-run in this final refactored public tree** (see the notes below each
section).

**Scope note:** the original dataset has **10 stock ROMs**. The 10th —
`[REDACTED]`, the project owner's personal live-ECU dump — is verified
byte-exact (evidence kept below) but is **kept private** and not shipped in
this public repo. All byte-exact rebuild claims for the shipped tree are
**9/9**. The modified ([REDACTED]/[REDACTED]) images are also private and not
shipped.

## 1. Byte-exact rebuild — 9/9 public stock ROMs (+ [REDACTED] verified privately)

`make verify-all` (drives `tools/verify_all.sh` → `tools/rom_rebuild.py` for
each ROM: capstone SH-2 + `disasm_sh2e.py` fallback → single `.s` →
`sh-elf-as -big` + `sh-elf-ld -Ttext=0x0` + `sh-elf-objcopy -O binary` →
`sha256sum` compare).

**Re-run in this public tree** (2026-07-31, 9 ROMs):

```
Rebuilding and byte-exact-verifying 9 stock ROMs (code window 0x800..0x60000)...
ROM                            sha256 match                    cov%    raw  STATUS
-----------------------------------------------------------------------
60E0E500.bin                   c05dfd0422b2b773027a22dc        93.5    246  BYTE-EXACT
60E0E700_N3YLEE.bin            bba52346a076c35ded281c14        93.5    326  BYTE-EXACT
60E0FB00.bin                   3d32e2591a1170d5ac3feed7        93.6    315  BYTE-EXACT
60E0FC00.bin                   476ddcbed4549d89b9835dfb        93.6    377  BYTE-EXACT
60E15120_N3J1E.bin             a7cd953c2a87af12ee2814a9        93.7    294  BYTE-EXACT
60E1B900.bin                   b0dc94f96e8eaf6f154df8e7        93.6    308  BYTE-EXACT
60E1C500_N3J6EB.bin            b3b6e1e416826d9c9f51ddc8        93.5    253  BYTE-EXACT
60E1D400.bin                   344cb8b960eb6dde973bdb8e        93.6    252  BYTE-EXACT
60E32000_N3M5E.bin             d5406459cc0b19f831a73a02        93.8    265  BYTE-EXACT
-----------------------------------------------------------------------
OK: all 9 stock ROMs rebuilt byte-exact (code window 0x800..0x60000).
```

`raw` = number of code-window words the self-correction loop forced back to
`.word` because GNU-as has no syntax for them (mostly the SH-2E `0x82nn/0x86nn`
`mov.l @(disp,Rm)` encodings) or they are data words capstone over-decoded; they
are emitted verbatim, so byte-exactness is by construction.

The pre-exclusion run (in the pre-refactor tree, before `[REDACTED]` was moved
to private storage) verified the same for **10/10**, including:

```
[REDACTED]              (sha256 withheld — private)    93.6    253  BYTE-EXACT
...
OK: all 10 stock ROMs rebuilt byte-exact (code window 0x800..0x60000).
```

`[REDACTED]` is byte-exact verified; the image itself is kept private.

### sha256 — source ROM vs rebuilt output (identical)

| ROM (roms/stock/) | sha256(source) = sha256(rebuilt) | Status |
|---|---|---|
| 60E0E500.bin | `c05dfd0422b2b773027a22dcce2c24923969f27b94634bfcbdb44d6157087e11` | public, 9/9 |
| 60E0E700_N3YLEE.bin | `bba52346a076c35ded281c14b7ff81fcfa6c6e8119b6ec544048e269b0c53dc0` | public, 9/9 |
| 60E0FB00.bin | `3d32e2591a1170d5ac3feed7ae065c650bde525e56693a5ca7499e6c9eb5f661` | public, 9/9 |
| 60E0FC00.bin | `476ddcbed4549d89b9835dfbfb1aac48217d943fb53c73f489ffc9414803e35c` | public, 9/9 |
| [REDACTED] | *(sha256 withheld — the private dump's hash is not published)* | **PRIVATE** (verified pre-exclusion) |
| 60E15120_N3J1E.bin | `a7cd953c2a87af12ee2814a95c958dc23959d352ef9c5e7f82b8ab8952f264f1` | public, 9/9 |
| 60E1B900.bin | `b0dc94f96e8eaf6f154df8e7388d12fba490cf2adf13edb077677c4c82b3b1b5` | public, 9/9 |
| 60E1C500_N3J6EB.bin | `b3b6e1e416826d9c9f51ddc853cae0dea3235a3ddbb260cccd23effc77995c68` | public, 9/9 |
| 60E1D400.bin | `344cb8b960eb6dde973bdb8e8c3e3e96cac542166cd7158c6f5f24d71eb7af78` | public, 9/9 |
| 60E32000_N3M5E.bin | `d5406459cc0b19f831a73a021ad2ae47179127097a15cfa323a34bfa47e330de` | public, 9/9 |

Single-ROM spot check (re-run here): `make ROM=roms/stock/60E1D400.bin verify`
→ `OK: byte-exact rebuild of roms/stock/60E1D400.bin`.

## 2. Instruction-lift coverage (annotated sources)

Window `0x800..0x60000` = 195,584 words. Remainder is byte-exact `.word` data
(literal pools, jump tables, calibration, padding, strings). From
`src/ANNOTATED_SOURCES.md` (table reproduced; `[REDACTED]` marked PRIVATE):

> **Coverage honesty caveat.** The coverage figures below are *round-trip*
> coverage — every in-window word that decodes and re-encodes to valid bytes is
> counted — and the byte-exact rebuild is real and verified (section 1).
> However, a small fraction (~6%) of those counted words are data tables that
> happen to decode as valid instructions (e.g. the `0x0007` `mul.l r0,r0`
> marker appears 2,427× — more than `rts`), so the true code fraction is
> ~88–91%, with data ~9–12%.

| ROM | annotated .s | size (.s) | function labels | .word lines | coverage% (in-window) | byte-exact rebuildable? |
|---|---|---|---|---|---|---|
| 60E0E500 | src/60E0E500_annotated.s | 4,657,982 | 7,305 | 58,615 | 93.50 | YES |
| 60E0E700_N3YLEE | src/60E0E700_N3YLEE_annotated.s | 4,660,312 | 7,306 | 58,436 | 93.46 | YES |
| 60E0FB00 | src/60E0FB00_annotated.s | 4,640,621 | 7,197 | 60,236 | 93.60 | YES |
| 60E0FC00 | src/60E0FC00_annotated.s | 4,444,212 | 3,454 | 60,299 | 93.56 | YES |
| [REDACTED] | src/[REDACTED] (PRIVATE) | 4,656,172 | 7,096 | 56,245 | 93.62 | YES |
| 60E15120_N3J1E | src/60E15120_N3J1E_annotated.s | 4,688,306 | 7,473 | 55,730 | 93.65 | YES |
| 60E1B900 | src/60E1B900_annotated.s | 4,639,305 | 7,173 | 59,959 | 93.57 | YES |
| 60E1C500_N3J6EB | src/60E1C500_N3J6EB_annotated.s | 4,658,588 | 7,315 | 58,332 | 93.48 | YES |
| 60E1D400 | src/60E1D400_annotated.s | 4,522,135 | 2,789 | 56,030 | 93.63 | YES |
| 60E32000_N3M5E | src/60E32000_N3M5E_annotated.s | 4,662,623 | 6,899 | 53,236 | 93.80 | YES |

Regeneration check (this repo): `make src` produced a file **byte-identical**
to the shipped `src/60E1D400_annotated.s` (`cmp` == 0).

## 3. Test suite results (all re-run in this release)

| Suite | Command (from repo root) | Result |
|---|---|---|
| Host C behavior-equivalence suites | `make c-test` | **26/26 pass** (exit 0; e.g. req_queue 20,512 tests, DTC row-update 22,560 tests, all 0 failures) |
| Python per-function suites | `for t in c/tests/test_*.py; do python3 "$t"; done` | **115/115 pass** (115 Python suites total: 112 `test_*.py` in `c/tests/` + 2 in `tools/tests/` + `verify_emu.py`; re-run 2026-08-01) |
| Emulator cross-check (C lift vs ROM bytes) | `python3 c/tests/verify_emu.py` | **5/5 OK** — add16bitSaturate@0x2460, addSaturate8Bit@0x2478, addS32Saturate@0x2304, seed_mixer@0x366B8, calculateImmoSeed@0x3675C (100k random each) |
| Disassembler family regression | `python3 tools/tests/test_decode_families.py` | **38,008 checks, 0 failures** (incl. GNU-as 2.46 bulk round-trip on 60E1D400 + 60E0FC00) |
| Emulator family regression | `python3 tools/tests/test_emulator_families.py` | **73 checks, 0 failures** |

## 4. Track A / C lifts

- **49 verified addresses** in `c/verified_addrs.txt` (counted 2026-08-01:
  49 address lines, 288 address tokens) — functions proven
  behavior-equivalent against the emulated ROM (many over 20k–60k+ random
  inputs; the math-primitive cluster and memory accessors over 30k, lookup/
  interp leaves over 10k–40k, incl. inf/NaN edges).
- **Coverage honesty caveat:** ~3.9% of the "covered" words are data markers
  `0x0004`–`0x0007` that decode as instructions (`0x0007` `mul.l r0,r0` ×2427);
  real code coverage is ≈88–91%.
- **149 C lifts** in `c/*.c` covering: lookup/interp primitives (2D/3D, u8/u16,
  FP), the scalar-math cluster (0x2044–0x2510), redundant RAM accessors
  (8/16/32-bit + float, self-heal), RTOS scheduler/context switch, immobilizer/
  SecurityAccess, DTC/OBD handlers, sensors (coolant, IAT, MAP, knock, VSS,
  battery, throttle), PID controllers, fueling/ignition/OMP chain, CAN/UDS,
  boot/reset.

## 5. Analysis / symbols / docs

| Deliverable | Location | Count |
|---|---|---|
| Code-window data classification (1,491 runs; 1,485 commented into 60E1D400_annotated.s) | `analysis/data_regions_60E1D400.{csv,md}` | 2 files |
| Function symbol tables (kept set: 60E0FC00 plain/ghidra, 60E1D400 ida/merged) | `symbols/symbols*.csv` | 4 CSVs |
| Calibration table descriptors | `symbols/cal_tables.csv` | 1,210 tables (1,209 land in-ROM) |
| Call graph edges | `symbols/callgraph.csv` | 6,953 resolved (758 bsr-direct, 6,195 pooled jsr) |
| Subsystem + overview docs | `docs/subsystems/*.md` | 15 files |
| Function docs | `docs/functions/*.md` | 193 files |
| Knowledge / notes (FINDINGS, KNOWLEDGE, RESUME, BOOT_RECOVERY, CONNECTOR_PINOUT, DUMP_ALL, ECU, HARDWARE, CAN_PROTOCOL) | `docs/notes/*.md` | 9 files |
| Hardware notes | `hardware/HARDWARE_NOTES.md` | 1 file |

## 6. ROM inventory hashes (also in roms/ROMS.md)

All 9 shipped stock ROMs: 512 KB each, valid Denso additive checksum (descriptor
@0x7FB80, target 0x5AA5A55A). Verified here with
`python3 tools/denso_ck.py roms/stock/60E1D400.bin` → `OK — checksum corretto`.

| ROM | sha256[:16] | Status |
|---|---|---|
| 60E0E500.bin | `c05dfd0422b2b773` | public |
| 60E0E700_N3YLEE.bin | `bba52346a076c35d` | public |
| 60E0FB00.bin | `3d32e2591a1170d5` | public |
| 60E0FC00.bin | `476ddcbed4549d89` | public |
| [REDACTED] | *(hash not published)* | **PRIVATE** (verified pre-exclusion) |
| 60E15120_N3J1E.bin | `a7cd953c2a87af12` | public |
| 60E1B900.bin | `b0dc94f96e8eaf6f` | public |
| 60E1C500_N3J6EB.bin | `b3b6e1e416826d9c` | public |
| 60E1D400.bin | `344cb8b960eb6dde` | public |
| 60E32000_N3M5E.bin | `d5406459cc0b19f8` | public |

Modified ROMs (`[REDACTED]`, `[REDACTED]`,
`[REDACTED]`) are **not shipped** in
this public repo (kept private, see [ROMS.md](roms/ROMS.md)).

## 7. Self-containedness

`make verify-all` was executed with an **empty environment**
(`env -i PATH=/usr/bin:/bin` + the shipped `tools/toolchain/usr/bin` on PATH),
proving the repo needs no hidden exports, aliases or data outside its own
tree. Output identical to section 1. The fresh-clone procedure is
[REPLICATION.md](REPLICATION.md).
