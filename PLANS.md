# RX-8 ECU Reverse Engineering — Master Plan

Single source of truth for goal, tracks, status, milestones, open items.

- Detail docs: `docs/subsystems/OVERVIEW.md`, `tools/ASM_BASELINE.md`,
  `tools/README.md`, `roms/ROMS.md`, `docs/notes/RESUME.md`,
  `docs/notes/KNOWLEDGE.md`, `docs/notes/FINDINGS.md`; session notes (private
  storage, not shipped); `docs/subsystems/*.md`, `docs/functions/*.md`.
- Reference hardware: Denso PCM 279700-3313, Renesas SH-2E (HD64F7055 / SH7055),
  512 KB ROM, big-endian. RX-8 Series 1 (Renesis 13B), 04-09 model years.

## Goal

Full **1:1 byte-exact firmware reverse engineering** of the Mazda RX-8 ECU. It
has two reinforcing deliverables: **Track B** — a buildable `.s` source that
re-assembles to the *identical ROM bytes* (`cmp == 0`) for all stock ROMs in the
dataset (9 shipped publicly) without the original Renesas/Hitachi SHC compiler —
and **Track A** — readable, behavior-equivalent C lifts (`c/*.c`) proven against
the *actual ROM bytes* on the SH-2E emulator (`tools/sh2emu.py`). Track B is the
oracle baseline. Track A lifts functions to C on top of it, one at a time. The
baseline always rebuilds.

## Tracks

### Track A — verified C lifts (`c/`, `tools/sh2emu.py`, `tools/disasm_sh2e.py`)

- Write behavior-equivalent C for ROM functions in `c/*.c`. Prove it by running
  the **actual ROM bytes** in `tools/sh2emu.py` over tens of thousands of
  randomized RAM states. The C model must match every state.
- Record results in `c/verified_addrs.txt`. Document them in `docs/notes/FINDINGS.md` +
  `docs/functions/`.
- Host test suite in `c/tests/` (194 Python + 26 C). Emulator cross-check:
  `make c-emu` (`c/tests/verify_emu.py`).

### Track B — byte-exact ROM rebuild (`tools/rom_rebuild.py`, `Makefile`, `tools/verify_all.sh`)

- **Method (byte-exact by construction):** SH-2 instructions are all 2 bytes.
  Every even offset in the code window `0x800..0x60000` is decoded independently —
  instruction if it re-encodes to the same 2 bytes, else raw `.word`. Everything
  outside the window (vectors, strings, Hitachi-OS data, calibration) is emitted
  as `.word`. Therefore it round-trips verbatim. Branch/PC-relative operands
  become `L_xxxxxx` labels. The ROM is linked at VMA 0, therefore
  displacements/ranges are the originals. A self-correcting loop forces any
  as-rejected or mis-encoding word back to raw `.word`. It converges to
  `cmp == 0`.
- The 5-10 raw fallbacks per ROM are data words capstone over-decodes as
  extended-SuperH ops (`ldc.l @rn+,tbr`, `stc.l tbr,@-rn`, `synco`) that
  `sh-elf-as` rejects. This confirms the real code is plain SH-2 (SH-2E core).
  They are emitted verbatim. Therefore byte-exactness holds.
- **Toolchain (self-contained, no root):** capstone ≥ 5.0 (SH) + GNU binutils-sh-elf
  fetched by `tools/get_toolchain.sh` into `tools/toolchain/usr/bin`. The Makefile
  and `verify_all.sh` resolve that path themselves — **no `~/.bashrc` exports
  needed**; a fresh clone reproduces byte-perfect ROMs with `make verify-all`.
- Verify a single ROM: `make ROM=roms/stock/<id>.bin verify`.
- Verify all 9 public stock ROMs: `make verify-all`.

## Current status

- **Track B: all 9 shipped stock ROMs are byte-exact rebuilds** (enforced by
  `make verify-all`): 512 KB each, `cmp == 0` against source. Instruction-lift
  coverage in the code window `0x800..0x60000` is **93.46–93.8%** per ROM
  (60E1D400 93.63%, 60E0FC00 93.56%, 60E1C500 93.48%, 60E32000 93.80%).
  The remainder is byte-exact `.word` data.
- **Track A: 266 verified addresses** (`c/verified_addrs.txt`) and **177 C
  lifts** (`c/*.c`): math/lookup primitives, RTOS (scheduler/context switch),
  security & immobilizer, PID dispatch, DTC/fault handling, sensors, boot, OMP
  chain (all 0 mismatches over 20k-60k inputs each).
- **Test suite: 194 Python suites green + `make c-test` 26/26** (fresh-copy
  clean after `test_security_access.py` switched to `tools/mazda_security.py`;
  legacy `security/` dir moved to private storage).
- **Emulator cross-check:** 5/5 OK (100k random inputs each): add16bitSaturate
  @0x2460, addSaturate8Bit @0x2478, addS32Saturate @0x2304, seed_mixer @0x366B8,
  calculateImmoSeed @0x3675C.

### Key numbers (reference)

| Item | Value |
|------|-------|
| Stock ROMs (dataset) | 9 shipped publicly, all 512 KB, valid Denso checksum, in `roms/stock/*.bin` |
| Baseline ROM | `60E1D400` (`SW-N3J1EM000.HEX`, `N3J1E_3W.T50`) |
| Hand-annotated reference | `60E0FC00` (931 equinox names) |
| Functions (symbol table) | 3459 total; 931 equinox-named + 2528 Ghidra-auto |
| Call edges resolved | 6953 (758 bsr-direct, 6195 pooled jsr) |
| Symbol coverage (baseline) | `symbols/symbols_60E1D400_merged.csv`: 2789 named functions |
| Calibration tables | `symbols/cal_tables.csv`: 1210 tables |
| Emulator | `tools/sh2emu.py` (SH-2E, cooperative RTOS semantics) |

## Reproducing everything (fresh clone)

Full walkthrough: [REPLICATION.md](REPLICATION.md). Quick reference:
`make verify-all` (9/9 byte-exact), `make ROM=roms/stock/60E1D400.bin verify`,
`make src`, `make c-test`, `make c-emu` (after `pip install capstone` and
`./tools/get_toolchain.sh`).

## Milestones

### Done
- Byte-exact rebuild pipeline without SHC (`tools/rom_rebuild.py` → `cmp == 0`;
  DoD: "`make` reproduces the stock ROM byte-for-byte").
- 10-ROM dataset assembled and cataloged (`roms/ROMS.md`), all checksums valid;
  9 shipped publicly.
- Symbol/name transfer across ROMs (`tools/xmap_names.py`); annotated sources
  (`tools/organize_src.py`, `make src`).
- Track A verification harness: emulator + 194-suite tests, 266 verified
  functions, subsystem docs.
- **Decode-coverage sprint**: coverage raised ~84.6% → **93.46–93.8%** in-window
  (~93.6% avg) by decoding the SH-2E families capstone misses (FPU, fpul/fpscr,
  `0x82nn/0x86nn` mov.l disp, SSR/SPC) with the `disasm_sh2e.py` fallback.

### In progress / planned
- **All shipped stock ROMs byte-exact (verified)**: `tools/verify_all.sh` +
  `make verify-all` enforce this from a clean clone.
- **Track A completion**: verify remaining named functions down the callgraph
  (≥ 2 callers first). OBD/UDS handlers **COMPLETE** (item 1). Residuals
  (security_access DRAFT, exhaust windows) are in **Next**.
- **Release packaging**: clean-room reproduction kit — README quickstart, pinned
  toolchain fetch, bulk verifier, no hidden environment magic.
- **BOOT-mode debug**: hardware-only (CN400 jig + FDT handshake) — not
  executable in this software environment; remains open.

## Open items

1. ~~**Track A — remaining function verification**: OBD/UDS service handlers~~ **COMPLETE 2026-08-03** — all verified (emulator + host-C, 0 mismatch):
   - OBD/UDS handlers: **0x64258** (`c/obd_dtc_row_update_0x64258.c`, 22048 host tests), **0x64418** (`c/obd_dtc_row_update_0x64418.c`, 22560 host tests), **0x62ABC**, **0x648B4**, **0x63312**, **0x632D6**, **0x63834**, **0x63B46** (commit e8192e7).
   - **FreezeFrame 0x467D0**, **UDSMode01 0x66258** — verified (`c/tests/test_obd_freezeframe_uds01.py`, commit f7f6424).
   - **OBD PID**: 9 `obd_pid` getters — 0x4C8C2/0x4C9C0 (getOBDCANTXVars1/2, 8-byte buffer 0xFFFFCEAC/0xFFFFCEC0, pipeline delay-slot, `test_obd_vars_vector.py`), 0x55D9A/0x55E18/0x55F7A (`test_obd_pid_getters3.py`), 0x55E66/0x55E7C/0x55EA2/0x55EEA/0x55F02 (`test_obd_pid_getters.py`), 0x55F64 (`test_obd_pid_getters2.py`), **Vector 0x670B4** (bitmap 0x5F6D8, `test_obd_vars_vector.py`).
   - **can_uds** (`c/can_uds_subsystem.c`): 12 packer/dispatcher with `c/tests/test_can_packers.py` (commit a7fc6d5, 3013 vectors, 0 mismatch — can203TX 0x29D24, can251TX 0x2AAB6, dispatcher 0x2D402/0x33942); **0x11540 = dispatch TABLE** (24 fptr BE), not a function (closed as data).
   - Work down the callgraph (≥2 callers next) → **Next**.
2. **Hardware BOOT-mode debug**: practice ECU never entered Renesas BOOT mode with
   the CN400 jig; FDT Error 15024; needs an active RESET pulse (not just power-on) —
   trace CN430/RST-OPEN, find RESET pin, get FDT handshake
   (`docs/notes/BOOT_RECOVERY.md`). **Hardware-only** — not executable in this
   software environment; remains open.
3. ~~**LFSR security mismatch**~~ **RESOLVED 2026-08-01** (commit `a84eaba`,
   emulator-verified against `SeedKeyRelated` @0x56ADA): the stock SecurityAccess
   LFSR **is** the ECOMcat/Craig-Smith 24-bit Galois algorithm (init `0xC541A9`,
   taps `0x909028` hardcoded at 0x56C1E-0x56C38) with a per-level init table
   @0x5FAC5 (3 bytes/level). ROM-verified vector: seed `0x45820A` / `"MazdA"` /
   level 1 → **0xA07258** (legacy vector 0x3B15E1 was wrong). Closed
   (docs/notes/UDS_SECURITY_MAPPING.md, 2026-08-03): SID 0x27 → handler 0x584A0
   (table 0x5F57C), only level 1 (subfunc 0x01/0x02, parity selects op).
   seed_gen 0x5699A level≠3 = entropy counter 0xFFFFF430 + XOR-mix (55 AA 55 if
   state==4, fallback FF FF FF after 16 retry). key_validate 0x56928 table
   0x5FAA2, b1 = b0 duplicated = SECURITY_STATE_2 @0xFFFFD20C, b2 =
   position_check. LFSR (per-level init @0x5FAC5, taps 0x909028) only in key
   transform 0x56ADA.

## Next (Track A residual leaves, after item-1 COMPLETE)

- **`c/security_access.c` — DRAFT / UNVERIFIED** structural reconstruction: LFSR
  core aligned to ROM, but documented discrepancies vs ROM must NOT be corrected
  until confirmed (`docs/notes/UDS_SECURITY_MAPPING.md`, §"Discrepanze C
  c/security_access.c vs ROM"). Goal: differential-verified with the emulator.
- **Exhaust / O2 residual leaves**: `exhaust_oxygen_control_19480` and the 6 O2/
  lambda leaves verified (item 1). Remaining exhaust callgraph leaves (for example
  `exhaust_control` @0x43F56, called from `c/engineControlCalculateTiming.c`)
  with ≥2 callers to verify top-down.

## Workflow rules

See [AGENTS.md](AGENTS.md). Track A addition: every C lift must be
emulator-verified with random-input tests before being marked verified
(`verify_emu.py`, `make c-emu`). Update `c/verified_addrs.txt`.
