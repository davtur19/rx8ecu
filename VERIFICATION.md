# VERIFICATION — evidence that the release does what it claims

Measured 2026-07-31 (sh-elf binutils 2.46, capstone 5.0.7, Python 3.14); re-run in this public tree. All rebuild claims are **9/9** for the 9-ROM set.

## 1. Byte-exact rebuild — 9/9 public stock ROMs

`make verify-all` → `tools/verify_all.sh` → `tools/rom_rebuild.py` (capstone SH-2 + `disasm_sh2e.py` fallback → single `.s` → `sh-elf-as -big` + `sh-elf-ld -Ttext=0x0` + `sh-elf-objcopy -O binary` → `sha256sum`).

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

`raw` = code-window words self-correction forced back to `.word` (GNU-as has no syntax: SH-2E `0x82nn/0x86nn` `mov.l @(disp,Rm)`) or capstone over-decoded as data; emitted verbatim ⇒ byte-exact by construction.

### sha256 — source ROM vs rebuilt output (identical)

| ROM (roms/stock/) | sha256(source) = sha256(rebuilt) | Status |
|---|---|---|
| 60E0E500.bin | `c05dfd0422b2b773027a22dcce2c24923969f27b94634bfcbdb44d6157087e11` | public, 9/9 |
| 60E0E700_N3YLEE.bin | `bba52346a076c35ded281c14b7ff81fcfa6c6e8119b6ec544048e269b0c53dc0` | public, 9/9 |
| 60E0FB00.bin | `3d32e2591a1170d5ac3feed7ae065c650bde525e56693a5ca7499e6c9eb5f661` | public, 9/9 |
| 60E0FC00.bin | `476ddcbed4549d89b9835dfbfb1aac48217d943fb53c73f489ffc9414803e35c` | public, 9/9 |
| 60E15120_N3J1E.bin | `a7cd953c2a87af12ee2814a95c958dc23959d352ef9c5e7f82b8ab8952f264f1` | public, 9/9 |
| 60E1B900.bin | `b0dc94f96e8eaf6f154df8e7388d12fba490cf2adf13edb077677c4c82b3b1b5` | public, 9/9 |
| 60E1C500_N3J6EB.bin | `b3b6e1e416826d9c9f51ddc853cae0dea3235a3ddbb260cccd23effc77995c68` | public, 9/9 |
| 60E1D400.bin | `344cb8b960eb6dde973bdb8e8c3e3e96cac542166cd7158c6f5f24d71eb7af78` | public, 9/9 |
| 60E32000_N3M5E.bin | `d5406459cc0b19f831a73a021ad2ae47179127097a15cfa323a34bfa47e330de` | public, 9/9 |

Single-ROM spot check: `make ROM=roms/stock/60E1D400.bin verify` → `OK: byte-exact rebuild of roms/stock/60E1D400.bin`.

## 2. Instruction-lift coverage (annotated sources)

Window `0x800..0x60000` = 195,584 words; remainder byte-exact `.word` data (literal pools, jump tables, calibration, padding, strings). From `src/ANNOTATED_SOURCES.md`:

> **Coverage honesty caveat.** Figures are *round-trip* coverage — every in-window word that decodes/re-encodes to valid bytes counts. ~6% are data tables that decode as valid instructions (`0x0007` `mul.l r0,r0` marker appears 2,427× — more than `rts`); true code ≈88–91%, data ≈9–12%.

| ROM | annotated .s | size (.s) | function labels | .word lines | coverage% (in-window) | byte-exact rebuildable? |
|---|---|---|---|---|---|---|
| 60E0E500 | src/60E0E500_annotated.s | 4,657,982 | 7,305 | 58,615 | 93.50 | YES |
| 60E0E700_N3YLEE | src/60E0E700_N3YLEE_annotated.s | 4,660,312 | 7,306 | 58,436 | 93.46 | YES |
| 60E0FB00 | src/60E0FB00_annotated.s | 4,640,621 | 7,197 | 60,236 | 93.60 | YES |
| 60E0FC00 | src/60E0FC00_annotated.s | 4,444,212 | 3,454 | 60,299 | 93.56 | YES |
| 60E15120_N3J1E | src/60E15120_N3J1E_annotated.s | 4,688,306 | 7,473 | 55,730 | 93.65 | YES |
| 60E1B900 | src/60E1B900_annotated.s | 4,639,305 | 7,173 | 59,959 | 93.57 | YES |
| 60E1C500_N3J6EB | src/60E1C500_N3J6EB_annotated.s | 4,658,588 | 7,315 | 58,332 | 93.48 | YES |
| 60E1D400 | src/60E1D400_annotated.s | 4,522,135 | 2,789 | 56,030 | 93.63 | YES |
| 60E32000_N3M5E | src/60E32000_N3M5E_annotated.s | 4,662,623 | 6,899 | 53,236 | 93.80 | YES |

Regeneration check: `make src` → file **byte-identical** to shipped `src/60E1D400_annotated.s` (`cmp` == 0).

## 3. Test suite results (all re-run in this release)

| Suite | Command (from repo root) | Result |
|---|---|---|
| Host C behavior-equivalence suites | `make c-test` | **26/26 pass** (exit 0; e.g. req_queue 20,512 tests, DTC row-update 22,560 tests, 0 failures) |
| Python per-function suites | `for t in c/tests/test_*.py; do python3 "$t"; done` | **194/194 pass** (194 suites in `c/tests/`: 192 `test_*.py` + `verify_emu.py` + `smoke_dtc_functions.py`; re-run 2026-08-03, 0 failures — the historically BLOCKED `test_sensorADCRead_68A8.py` was unblocked by the emulator MMIO hook `c1e49b6` and now passes) |
| Emulator cross-check (C lift vs ROM bytes) | `python3 c/tests/verify_emu.py` | **5/5 OK** — add16bitSaturate@0x2460, addSaturate8Bit@0x2478, addS32Saturate@0x2304, seed_mixer@0x366B8, calculateImmoSeed@0x3675C (100k random each) |
| Disassembler family regression | `python3 tools/tests/test_decode_families.py` | **38,008 checks, 0 failures** (incl. GNU-as 2.46 bulk round-trip on 60E1D400 + 60E0FC00) |
| Emulator family regression | `python3 tools/tests/test_emulator_families.py` | **83 checks, 0 failures** |

## 4. Track A / C lifts

- **266 verified addresses** in `c/verified_addrs.txt` (counted 2026-08-03) — behavior-equivalent vs emulated ROM (many over 20k–60k+ random inputs; math primitives + memory accessors over 30k; lookup/interp leaves 10k–40k, incl. inf/NaN edges).
- **Coverage honesty caveat:** ~3.9% of "covered" words are data markers `0x0004`–`0x0007` that decode as instructions (`0x0007` `mul.l r0,r0` ×2427); real code coverage ≈88–91%.
- **177 C lifts** in `c/*.c`: lookup/interp primitives (2D/3D, u8/u16, FP), scalar-math cluster (0x2044–0x2510), redundant RAM accessors (8/16/32-bit + float, self-heal), RTOS scheduler/context switch, immobilizer/SecurityAccess, DTC/OBD handlers, sensors (coolant, IAT, MAP, knock, VSS, battery, throttle), PID controllers, fueling/ignition/OMP chain, CAN/UDS, boot/reset.
- **Recent verification batches (commits)** — OBD vars/vector `test_obd_vars_vector.py` f7f6424, OBD vars-lift fix c0fa7e3, CAN packers + MAF limits a7fc6d5, OBD getters + CAN/O2 batch 14dcbf3, seed_gen 91193ac, emulator MMIO hook (unblocks sensorADCRead) c1e49b6, badges/README regen 6994add.

## 5. Analysis / symbols / docs

| Deliverable | Location | Count |
|---|---|---|
| Code-window data classification (1,491 runs; 1,485 commented into 60E1D400_annotated.s) | `analysis/data_regions_60E1D400.{csv,md}` | 2 files |
| Function symbol tables (kept set: 60E0FC00 plain/ghidra, 60E1D400 ida/merged) | `symbols/symbols*.csv` | 4 CSVs |
| Calibration table descriptors | `symbols/cal_tables.csv` | 1,210 tables (1,209 land in-ROM) |
| Call graph edges | `symbols/callgraph.csv` | 6,953 resolved (758 bsr-direct, 6,195 pooled jsr) |
| Subsystem + overview docs | `docs/subsystems/*.md` | 15 files |
| Function docs | `docs/functions/*.md` | 194 files |
| Knowledge / notes | `docs/notes/*.md` | 11 files |
| Hardware notes | `hardware/HARDWARE_NOTES.md` | 1 file |

## 6. ROM inventory hashes (also in roms/ROMS.md)

All 9 shipped stock ROMs: 512 KB each, valid Denso additive checksum (descriptor @0x7FB80, target 0x5AA5A55A); `python3 tools/denso_ck.py roms/stock/60E1D400.bin` → `OK — checksum corretto`.

| ROM | sha256[:16] | Status |
|---|---|---|
| 60E0E500.bin | `c05dfd0422b2b773` | public |
| 60E0E700_N3YLEE.bin | `bba52346a076c35d` | public |
| 60E0FB00.bin | `3d32e2591a1170d5` | public |
| 60E0FC00.bin | `476ddcbed4549d89` | public |
| 60E15120_N3J1E.bin | `a7cd953c2a87af12` | public |
| 60E1B900.bin | `b0dc94f96e8eaf6f` | public |
| 60E1C500_N3J6EB.bin | `b3b6e1e416826d9c` | public |
| 60E1D400.bin | `344cb8b960eb6dde` | public |
| 60E32000_N3M5E.bin | `d5406459cc0b19f8` | public |

## 7. Self-containedness

`make verify-all` ran with **empty environment** (`env -i PATH=/usr/bin:/bin` + shipped `tools/toolchain/usr/bin` on PATH) — no hidden exports, aliases, or external data; output identical to section 1. Fresh-clone procedure: [REPLICATION.md](REPLICATION.md).
