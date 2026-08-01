# RX-8 ECU Reverse Engineering — Session Resume

## 1. Objective
- Full 1:1 byte-exact firmware reverse engineering of Mazda RX-8 ECU (Denso 279700-3313, Renesas SH-2E / SH7055, 512KB ROM), plus behavioral C lifts (Track A) verified against a custom SH-2E emulator.
- Track A: write readable behavior-equivalent C lifts in `c/*.c`, prove correct by executing actual ROM bytes in `tools/sh2emu.py` over tens of thousands of random RAM states, then document in `docs/notes/FINDINGS.md` + `docs/subsystems/`.
- Track B: asm-first byte-exact ROM rebuild via `tools/rom_rebuild.py` (capstone + sh-elf binutils), converging to `cmp == 0` byte-identical.

## 2. Environment (critical setup facts)
- Project root: repository root (this repo)
- Toolchain NOT on PATH: `export PATH="$PWD/tools/toolchain/usr/bin:$PATH"` (sh-elf-as/ld/objcopy 2.46; install via `./tools/get_toolchain.sh` — the Makefile and verify_all.sh resolve it themselves)
- Emulator: `tools/sh2emu.py`; disassembler: `tools/disasm_sh2e.py`; function extractor: `tools/extract_func.py`
- Baseline ROM: `roms/stock/60E1D400.bin` (524288 B). All 9 shipped stock ROMs (10 with the private [REDACTED]) share header `0000 08b8 ffff dfa0`; ROM ID string at 0x2000 (e.g. 60E1D400). 60E1D400 = analysis baseline; 60E0FC00 = hand-annotated reference (931 equinox names); [REDACTED] = user's live ECU ROM.
- Symbols: `symbols_60E1D400_merged.csv` (2789 named functions: 2475 ida-ai + 314 ghidra-hand-xmap). Name transfer: `tools/xmap_names.py`, `tools/idamap.py`.
- Calibration tables: `symbols/cal_tables.csv` (1210 tables). RTOS docs in `docs/subsystems/RTOS_SUBSYSTEM.md`.
- Git: fresh public repo, single commit after the 2026-07-31 refactor (old history kept in `.git.private-backup/`).

## 3. CRITICAL CORRECTNESS VERDICTS (do not regress these)
1. **FCMP/GT semantics** (SETTLED 2026-07-31, do NOT "fix" the emulator):
   - `FCMP/GT FRm,FRn` sets T=1 iff **FRn > FRm** (n = bits 11-8, m = bits 7-4). This is the documented Renesas SH-2E behavior, confirmed by Ghidra SuperH4 sleigh, QEMU sh4 translate.c, and the Renesas manual. Note: opposite of integer CMP/GT Rm,Rn (T = Rm > Rn).
   - Emulator `tools/sh2emu.py` lines ~114-115 are CORRECT: `nib==0x4: T = f[n]==f[m]` (fcmp/eq), `nib==0x5: T = f[n]>f[m]` (fcmp/gt). Disassembler is consistent.
   - The old FINDINGS.md entry claiming a "fcmp/gt operand order bug fix" is FALSE — that change was never committed (git shows identical code in both commits) and would have introduced a real bug. Later FINDINGS entries (lines 100-103, 253) and the control-logic pseudocode doc (moved to private storage, not shipped) at :1316 correctly state T = (FRN > FRM).
   - **PENDING FIX**: `c/tests/test_o2_lambda.py` has 3 failing subtests with INVERTED expectations, and `c/o2_lambda_subsystem.c` `calc_lambda_integration_time` is inverted. ROM function @0x1418C: fr3=2.5 threshold, fr2=signal, `fcmp/gt fr2,fr3` → T=(2.5>signal); bt → countdown when signal<2.5, reload to 7 when signal>2.5. Correct expected outputs: signal=3.0,timer=7→7 (reload); signal=1.0,timer=3→2 (countdown); signal=3.0,timer=0→7 (reload). Fix the C model to `if (threshold > engine_speed) countdown; else reload`. Also correct the misleading note in notes/FINDINGS.md lines 3-7.
2. **0x6-group ALU encoding**: `0x6n<op>m` = dst n in bits 11-8, src m in bits 3-0 (e.g. 0x6477 = not r7,r4). Implemented correctly in emulator.
3. **Emulator missing opcodes remain**: e.g. `0x440E` MOV.W R0,@(0xE,R4) and some 0x4n group; `jsr @Rn` display bug in disassembler. Known gap.

## 4. Verified progress (Track A)
- Test suite: **84 PASS / 2 FAIL / 0 SKIP** across 86 standalone test scripts in `c/tests/`. The 2 failures are the O2 inverted-expectation test (see section 3) and `test_div32_signed.py` (test bug: its SH2Div subclass mis-implements div0s/div1/rotcl/subc — writes partial remainder to r[m] instead of r[n]; the ROM function @0x3FE8 itself is a standard 32x div1 loop, and the C lift is independently verified 100K+26 edge cases on host).
- Cross-check `c/tests/verify_emu.py`: 5/5 OK (100k random each): add16bitSaturate @0x2460, addSaturate8Bit @0x2478, addS32Saturate @0x2304, seed_mixer @0x366B8, calculateImmoSeed @0x3675C.
- `c/verified_addrs.txt`: 85 unique addresses. Notable verified function families:
  - Lookup: 2D/3D lookup family (0x2068, 0x20C4, 0x20AC, 0x2624, 0x20DC, 0x2120, 0x213C, 0x2658)
  - Math/mem: setSR/getSR/setSR_PARAM (0x3920/0x3934/0x2054), div32_signed (0x3FE8), mod32_signed (0x4144), shifts (0x4308/0x44E0/0x43C8), bitfield_extract_merge (0x48C8), checkFloatValidity (0x46CC), memcpy (0x42B0), least_square (0x5687A)
  - RTOS: osTaskScheduler (0x9668), consistencyCheck (0x3A28), task_full_context_save (0x3BF4), task_execute_by_index (0x3854), task_flag_run_C (0x35EE)
  - Security/immobilizer: seed_mixer (0x366B8), calculateImmoSeed (0x3675C)
  - PID: dispatch hubs 0x1252C, 0x12BC8, 0x18054, 0x11A34
  - Faults: getFaultStatus (0x6743C), dtc_data_read (0x60F58), dtcRelated (0x62002), dtc_code_set/clear (0x46780/0x467AA), dtc_debounce_monitor (0x43760), dtc_handler (0x610FA, 0x61550)
  - Sensors: getKnockSensorADC (0xC3CE), knockSensorADCFault (0xC460)
  - Boot: resetHandler (0x4E0), Manual_Reset (0x8B8), bsc_init (0x8CC), gpio_init (0x8F6), boot_entry/main 0xD49C (NOT 0xD4B6 — that's warm-restart validation), secondary_boot_main (0xA038), task_context_switch (0x3AD8), init_main (0x3E10), vector_trampoline_set_sp (0x40)
  - OMP chain: omp_control_task_1825E @0x1825E, omp_stepper_waveform_driver (0x18552), omp_waveform_state_machine_18860 (0x18860), rotor_sync_position_detector (0x189EE), 0x18C5C, 0x18C6C, 0x18C08 (all 0 mismatches, 20k-60k inputs each). Note: ida-ai names for this cluster (leading_edge_spark_calc etc.) look WRONG — hardware-port + waveform-step behavior + equinox name say OMP stepper.
- Emulator bug found & fixed in this cluster: 0x189EE state-4 gate uses `add #0xFE,r1` which SIGN-EXTENDS (0xFE = -2), so condition is `(A8F1 - 2) >= A974` signed, not `(A8F1 + 0xFE) >= A974`.

## 5. Verified progress (Track B — byte-exact ROM rebuild)
- 9 public ROMs (and the private [REDACTED]) rebuilt byte-identical (cmp clean, 524288 B): 60E1D400 (84.6% instr coverage), 60E0FC00 (84.7%), 60E1C500 (84.6%), 60E32000 (84.3%). Artifacts in `build/` (out.bin, rom.s/.elf/.o). Tool `tools/rom_rebuild.py`: emits one reassemblable .s, links at VMA 0, forces non-reassemblable words back to .word, converges to cmp==0.

## 6. Key architecture knowledge (high-confidence)
- RTOS: cooperative multitasking, 100-entry circular queue (head @0x400, tail @0x404), task table @0xDB14 (27 tasks + system), descriptor table @0xD9E4, task stubs @0xA12E-0xA3D0, RTOS CB @0xFFFF72B0, task state/priority @0xFFFF9304, osTaskScheduler @0x9668, task_table_scan_init @0x3EC0. OS task table @0x18000; 0x18024=0x1825E (OMP task), 0x1802C=0x18CC0 (omp_rotor_overshoot_detector_18CC0).
- UDS: dispatch table @0x5F57C (28 entries, 12-byte, session access bitmask 0x01 default/0x02 prog/0x04 extended), SecurityAccess handler @0x584A0, seed/key routine @0x56ADA. Secret "MazdA" @0x5FAC0, LFSR params @0x5FAC8 (init C5 41 A9; KNOWLEDGE.md says taps 0x909028), position/lookup tables @0x5FA90/0x5FAA2. Known keys: stock "MazdA", [REDACTED] "vendor-family secret", [REDACTED] "[REDACTED]". RESOLVED (2026-07-31, emulator-verified): the stock LFSR IS the ECOMcat/Craig-Smith 24-bit Galois algorithm (init 0xC541A9, taps 0x909028) with a per-level init table @0x5FAC5 (3 bytes/level); the legacy stock vector 0x3B15E1 was wrong — ROM-verified value for seed 0x45820A / 'MazdA' / level 1 is 0xA07258. Remaining unknowns: UDS subfunction→level mapping, seed_gen (@0x5699A) internals for level≠3, key_validate middle-byte source.
- OBD: Mode 1 @0x66258, Mode 9 @0x66CFC, PID table @0x5F6D8, floatToOBDBounded @0x24D0. Dual TX buffers @0xFFFFCEAC (CAN 0x240) and @0xFFFFCEB4 (CAN 0x250).
- CAN: RX dispatch = secondary_system_controller @0xDE8E (NOT CANRX_Main @0xDBF6), TX dispatcher CANTX_Main @0xDDF0, CAN41TXPack @0x39348, mailbox config @0x4EA60, placeCANRX @0x99C4 (CAN receive path, not checksum). [REDACTED] LC patch: hook @0x94C8, code cave 0x6C7FE-0x6CBFA, anti-tamper = EEPROM 17-byte checksum kill + PairingByte.
- Fueling: MAF-based speed-density, 420cc/min @3.9 bar injectors, latency tables @0x780F4/0x77F58, MAF 48-point table @0x6A0E4, coolant delta filter constants, battery thresholds @0x751B0. O2/lambda subsystem with dual 2.5V threshold logic (see section 3).
- Ignition: rotary leading/trailing 4 plugs via MTU2, spark config table @0xDAB4, spark state RAM @0xFFFFA0D8.
- Boot: cold/warm split via magic 0x5AA5A55A @0xFFFFDFFC; VBR=0x7FC50, FPSCR=0x40001, SP=0xFFFF7304. 0x6C8 bootloader dispatch, 0x12B4/0x1038 ROM-ID check. Note: 0x5A1F is a WDT write value, not code — WDT_RESET_ADDR is 0x572.
- DTC: packed output buffer in dtcRelated (out[count]=code, count increments, NOT out[i] indexed by entry). dtcRelated @0x62002 (not 0x5FEB6 — that was 60E0FC00 build). Checksum convention documented in docs/functions/dtc_management.md.
- Hardware: practice ECU (live = [REDACTED]) never entered Renesas BOOT mode via CN400 jig; FDT Error 15024; need active RESET pulse not just power-on. J2534 OBDX Pro VX tool. Hardware notes in docs/notes/BOOT_RECOVERY.md, CONNECTOR_PINOUT.md, DUMP_ALL.md.

## 7. Active / in-progress
- Track-A OBD/UDS service handlers: 0x64258 (c/obd_dtc_row_update_0x64258.c) and 0x64418 (c/obd_dtc_row_update_0x64418.c) lifted and emulator-verified (host C 22048/22560 tests + 20000 random each, 0 mismatches); 0x62ABC, 0x648B4, 0x63312, 0x632D6, 0x63834, 0x63B46 — lifts + side-effect tests exist in c/ + c/tests/ (untracked), full verification pending.
- OMP task 0x1825E itself (A97B countdown, state gates, port writes, dispatch) — **LIFTED + emulator-verified** (`c/omp_task_0x1825E.c` with `test_omp_task_0x1825E.py`, 150000+ inputs, 0 mismatches). Companion task 0x18CC0 (`omp_rotor_overshoot_detector_18CC0`) — **LIFTED + emulator-verified** (`c/omp_rotor_overshoot_detector_18CC0.c` with its test). Honest caveats: downstream consumers of the OMP RAM cluster (A990/A991) are still unknown, and the internal task leaves 0x18C5C/0x18C6C/0x18C08 run natively in the emulator (effects inlined, not separately lifted as C).
- Hardware BOOT-mode debug session (FDT handshake, read practice ECU ROM/EEPROM).

## 8. Next steps (priority order)
1. **Fix the 2 failing tests** (highest priority, low effort): correct inverted expectations in test_o2_lambda.py (expected: 7, 2, 7) AND the inverted logic in c/o2_lambda_subsystem.c (`if (threshold > engine_speed) countdown`), and correct the false fcmp/gt "bug fix" note in notes/FINDINGS.md lines 3-7. Then run test_o2_lambda.py → expect 11/11.
2. Fix test_div32_signed.py SH2Div subclass (div0s/div1/rotcl/subc operand order: partial remainder to r[n]; subc operand order).
3. Continue Track-A verification of remaining named unverified functions (work down callgraph, ≥2 callers next).
4. Finish verification of the remaining OBD/UDS service handlers in section 7 (0x62ABC, 0x648B4, 0x63312, 0x632D6, 0x63834, 0x63B46 — side-effect tests exist, full verification pending).
5. Extract numeric PID/Lambda coefficients from FP-heavy cores (esp. 0x1ACDE, 247 FPU ops).
6. Map OBD PID handlers under Mode 1 @0x66258 to SAE J1979 PIDs; analyze KWP2000 serial diag stack (0x1572-0x1D98).
7. Track-B: continue raising instruction coverage above 84.6% (investigate non-reassemblable word buckets).
8. RESOLVED 2026-07-31: stock LFSR == ECOMcat 24-bit Galois (vector 0xA07258 emulator-verified). Remaining: UDS subfunction→level mapping, seed_gen level≠3 internals, key_validate middle-byte source.
9. Hardware: complete BOOT-mode debug (trace CN430/RST-OPEN, find RESET pin, get FDT handshake).

## 9. Workflow rules (from AGENTS.md)
- Update the session notes (kept in private storage, not shipped; overwrite with current state at end of each session), docs/notes/FINDINGS.md (append confirmed facts), docs/subsystems/*.md as verification progresses.
- Every C lift must be verified against the emulator with random-input tests before being marked verified; update c/verified_addrs.txt.
- Never commit unless the user asks. Leave repo as found otherwise.
- `verify_emu.py` is the quick cross-check (currently 5/5 OK).

## 10. Final status (post-release)

This section is a closing addendum to the historical handoff above — it does not
rewrite any of it.

- **Release completed 2026.** The deliverable is this repository root
  (743 files) at the project root: byte-exact ROM rebuild pipeline, annotated
  sources, verified C lifts, tests, tools, docs, and ROMs.
- **9/9 public stock ROMs byte-exact** (10/10 incl. private [REDACTED]): `make verify-all` rebuilds all 9 public stock ROMs
  with `sha256(rebuilt) == sha256(source)` (`cmp == 0`); modded images are private.

- **Instruction-lift coverage 93.5–93.8%** in the code window `0x800..0x60000`
  (~93.6% average), up from the 84.x% numbers recorded in the sections above,
  thanks to the `disasm_sh2e.py` SH-2E fallback.
- **Tests green**: 100/100 Python per-function suites, `make c-test` 21/21 C
  host suites, `verify_emu.py` 5/5 emulator cross-checks, and the disassembler /
  emulator family regressions (38,008 / 69 checks, 0 failures).
- **~97 verified addresses** in `c/verified_addrs.txt`; **149 C lifts** in
  `c/*.c`.
- **Historical note**: the 84.x% coverage figures and the "84 PASS / 2 FAIL
  across 86" test tally quoted in sections 4–5 and 8 above are HISTORICAL —
  they describe the state at the time of that handoff and no longer reflect
  the released tree, which is this repository root as described here.
