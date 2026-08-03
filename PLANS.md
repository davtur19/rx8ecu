# RX-8 ECU Reverse Engineering — Master Plan

Single source of truth for the project: goal, tracks, current status, milestones,
and open items. Supporting detail lives in the docs linked throughout.

- Detail docs: `docs/subsystems/OVERVIEW.md`, `tools/ASM_BASELINE.md`,
  `tools/README.md`, `roms/ROMS.md`, `docs/notes/RESUME.md`,
  `docs/notes/KNOWLEDGE.md`, `docs/notes/FINDINGS.md`, session notes (kept in
  private storage, not shipped),
  subsystem docs in `docs/subsystems/*.md`, function docs in
  `docs/functions/*.md`.
- Reference hardware: Denso PCM 279700-3313, Renesas SH-2E (HD64F7055 / SH7055),
  512 KB ROM, big-endian. RX-8 Series 1 (Renesis 13B), 04-09 model years.

## Goal

Full **1:1 byte-exact firmware reverse engineering** of the Mazda RX-8 ECU, with
two deliverables that reinforce each other:

1. **Track B — byte-exact ROM rebuild**: a buildable, editable source (`.s`) that
   re-assembles into the *identical ROM bytes* (byte-for-byte, `cmp == 0`) for all
   stock ROMs in the dataset (10 verified; 9 shipped publicly — the 10th,
   `[REDACTED]`, the owner's personal live-ECU dump, is kept private) — without the
   original Renesas/Hitachi SHC compiler.
2. **Track A — verified C lifts**: readable, behavior-equivalent C reimplementations
   (`c/*.c`) proven against the *actual ROM bytes* executing on the custom SH-2E
   emulator (`tools/sh2emu.py`), then documented.

Track B is the reference/oracle baseline; Track A lifts functions to C on top of it
one at a time, and the baseline always rebuilds.

## Tracks

### Track A — verified C lifts (`c/`, `tools/sh2emu.py`, `tools/disasm_sh2e.py`)

- Write readable behavior-equivalent C for ROM functions in `c/*.c`.
- Prove correctness by executing the **actual ROM bytes** in `tools/sh2emu.py` over
  tens of thousands of randomized RAM states; the C model must match every state.
- Recorded in `c/verified_addrs.txt`; documented in `docs/notes/FINDINGS.md` +
  `docs/functions/`.
- Host-compile test suite in `c/tests/` (194 Python + 26 C standalone
  suites); emulator cross-check: `make c-emu` (`c/tests/verify_emu.py`).

### Track B — byte-exact ROM rebuild (`tools/rom_rebuild.py`, `Makefile`, `tools/verify_all.sh`)

- **Method (byte-exact by construction):** SH-2 instructions are all 2 bytes, so
  every even offset in the code window `0x800..0x60000` is decoded independently —
  instruction if it re-encodes to the same 2 bytes, else raw `.word`. Everything
  outside the window (vectors, strings, Hitachi-OS data, calibration) is emitted as
  `.word`, so it round-trips verbatim. Branch/PC-relative operands become
  `L_xxxxxx` labels; the whole ROM is linked at VMA 0, so displacements/ranges are
  the originals. A self-correcting loop forces any as-rejected or mis-encoding word
  back to raw `.word` and converges to `cmp == 0`.
- The 5-10 raw fallbacks per ROM are data words capstone over-decodes as extended-SuperH
  ops (`ldc.l @rn+,tbr`, `stc.l tbr,@-rn`, `synco`) which `sh-elf-as` rejects —
  confirmation the real code is plain SH-2 (SH-2E core). Emitted verbatim, so byte-exactness holds.
- **Toolchain (self-contained, no root):** capstone ≥ 5.0 (SH) + GNU binutils-sh-elf
  fetched by `tools/get_toolchain.sh` into `tools/toolchain/usr/bin`. The Makefile and
  `verify_all.sh` resolve that path themselves — **no `~/.bashrc` exports needed**,
  a fresh clone can reproduce byte-perfect ROMs with `make verify-all`.
- Verify a single ROM: `make ROM=roms/stock/<id>.bin verify`.
- Verify all 9 public stock ROMs: `make verify-all`.

## Current status

- **Track B: all 9 shipped stock ROMs (and the private [REDACTED]) are byte-exact
  rebuilds** (enforced by `make verify-all`): 512 KB each, `cmp == 0` against
  source. Instruction-lift coverage in the code window `0x800..0x60000` is
  **93.46–93.8%** per ROM (60E1D400 93.63%, 60E0FC00 93.56%, 60E1C500 93.48%,
  60E32000 93.80%), remainder is byte-exact `.word` data.
- **Track A: 97 verified addresses** (`c/verified_addrs.txt`) and **177 C
  lifts** (`c/*.c`): math/lookup primitives, RTOS (scheduler/context switch),
  security & immobilizer, PID dispatch, DTC/fault handling, sensors, boot, OMP
  chain (all 0 mismatches over 20k-60k inputs each).
- **Test suite: 194 Python suites green + `make c-test` 26/26** (was
  "100/100 + 21/21"; before that "84 PASS / 2 FAIL across 86"; the old harness
  failures were fixed, and `test_security_access.py` now imports
  `tools/mazda_security.py` instead of the legacy `security/` directory (moved
  to private storage), so it runs in a fresh copy of the repo).
- **Emulator cross-check:** 5/5 OK (100k random inputs each): add16bitSaturate
  @0x2460, addSaturate8Bit @0x2478, addS32Saturate @0x2304, seed_mixer @0x366B8,
  calculateImmoSeed @0x3675C.

### Key numbers (reference)

| Item | Value |
|------|-------|
| Stock ROMs (dataset) | 10, all 512 KB, valid Denso checksum; **9 shipped publicly** in `roms/stock/*.bin`, `[REDACTED]` (owner's live ECU) kept private; modded [REDACTED]/[REDACTED] images exist privately |
| Baseline ROM | `60E1D400` (`SW-N3J1EM000.HEX`, `N3J1E_3W.T50`) |
| Hand-annotated reference | `60E0FC00` (931 equinox names) |
| User's live ECU | `[REDACTED]` (`[REDACTED]`, `[REDACTED]`) — PRIVATE |
| Functions (symbol table) | 3459 total; 931 equinox-named + 2528 Ghidra-auto |
| Call edges resolved | 6953 (758 bsr-direct, 6195 pooled jsr) |
| Symbol coverage (baseline) | `symbols/symbols_60E1D400_merged.csv`: 2789 named functions |
| Calibration tables | `symbols/cal_tables.csv`: 1210 tables |
| Emulator | `tools/sh2emu.py` (SH-2E, cooperative RTOS semantics) |

## Reproducing everything (fresh clone)

```bash
python3 -m pip install capstone --break-system-packages
./tools/get_toolchain.sh      # installs sh-elf binutils locally (idempotent)
make verify-all               # rebuilds + verifies all 9 public stock ROMs byte-exact
make ROM=roms/stock/60E1D400.bin verify   # single ROM
make src                      # annotated source (60E1D400 baseline)
make c-test                   # Track A host-compile tests
make c-emu                    # Track A emulator cross-checks
```

## Milestones

### Done
- Asm-first byte-exact rebuild pipeline (Track B oracle) without SHC —
  `tools/rom_rebuild.py` converges to `cmp == 0` (DoD: "`make` reproduces the stock
  ROM byte-for-byte").
- 10-ROM stock dataset assembled and cataloged (`roms/ROMS.md`), all checksums
  valid; 9 shipped publicly, `[REDACTED]` kept private.
- Symbol/name transfer across ROMs (`tools/xmap_names.py`), annotated sources
  (`tools/organize_src.py`, `make src`).
- Track A verification harness: emulator + 100-suite test harness, 97 verified
  functions, subsystem docs.
- **Decode-coverage sprint (DONE)**: instruction-lift coverage raised from
  ~84.6% to **93.46–93.8%** in-window (~93.6% average) by decoding the SH-2E
  families capstone misses (FPU, fpul/fpscr, `0x82nn/0x86nn` mov.l disp,
  SSR/SPC) through the `disasm_sh2e.py` fallback instead of emitting `.word`.

### In progress / planned
- **All shipped stock ROMs byte-exact (verified)**: `tools/verify_all.sh` +
  `make verify-all` enforce this from a clean clone (this hardening pass).
- **Track A completion**: verify remaining named functions down the callgraph
  (≥ 2 callers first). OBD/UDS service handlers sono **COMPLETI** (item 1
  sotto); i residui Track A (security_access DRAFT, exhaust windows) sono in
  **Next** sotto.
- **Release packaging**: clean-room reproduction kit — README quickstart, pinned
  toolchain fetch, bulk verifier, no hidden environment magic (this pass).
- **BOOT-mode debug**: item hardware-only (pratica su CN400 jig + FDT
  handshake) — **non eseguibile in questo ambiente software**, resta aperto.

## Open items

1. ~~**Track A — remaining function verification**: OBD/UDS service handlers~~ **COMPLETO 2026-08-03** — tutti ✓ verified (emulator + host-C, 0 mismatch):
   - OBD/UDS service handlers: **0x64258** (`c/obd_dtc_row_update_0x64258.c`, 22048 host tests), **0x64418** (`c/obd_dtc_row_update_0x64418.c`, 22560 host tests), **0x62ABC**, **0x648B4**, **0x63312**, **0x632D6**, **0x63834**, **0x63B46** — ✓ verified emulator+host-C, 0 mismatch (commit e8192e7).
   - **FreezeFrame 0x467D0** e **UDSMode01 0x66258** — ✓ verified (dedicato `c/tests/test_obd_freezeframe_uds01.py`, commit f7f6424).
   - **OBD PID**: i 9 getter `obd_pid` — 0x4C8C2/0x4C9C0 (getOBDCANTXVars1/2, buffer 8-byte 0xFFFFCEAC/0xFFFFCEC0, pipeline delay-slot, `test_obd_vars_vector.py`), 0x55D9A/0x55E18/0x55F7A (`test_obd_pid_getters3.py`), 0x55E66/0x55E7C/0x55EA2/0x55EEA/0x55F02 (`test_obd_pid_getters.py`), 0x55F64 (`test_obd_pid_getters2.py`) + **Vector 0x670B4** (bitmap 0x5F6D8, `test_obd_vars_vector.py`) — tutti ✓ verified.
   - **can_uds** (`c/can_uds_subsystem.c`): tutti i 12 packer/dispatcher coperti via `c/tests/test_can_packers.py` (commit a7fc6d5, 3013 vectors, 0 mismatch — incl. can203TX 0x29D24, can251TX 0x2AAB6, dispatcher 0x2D402/0x33942 con catena pinnata); **0x11540 = dispatch TABLE** (24 fptr BE), non funzione (chiusa come data).
   - Work down the callgraph (≥2 callers next) → vedi sezione **Next**.
2. **Hardware BOOT-mode debug**: practice ECU (live [REDACTED]) never entered Renesas
   BOOT mode via CN400 jig; FDT Error 15024; needs an active RESET pulse (not just
   power-on) — trace CN430/RST-OPEN, find RESET pin, get FDT handshake
   (`docs/notes/BOOT_RECOVERY.md`). **Hardware-only** (ECU + jig CN400 + FDT
   handshake): non eseguibile in questo ambiente software, resta aperto.
3. ~~**LFSR security mismatch**~~ **RESOLVED 2026-08-01** (commit `a84eaba`,
   emulator-verified against `SeedKeyRelated` @0x56ADA): the stock SecurityAccess
   LFSR **is** the ECOMcat/Craig-Smith 24-bit Galois algorithm (init `0xC541A9`,
   taps `0x909028` hardcoded in the ROM at 0x56C1E-0x56C38) with a per-level init
   table @0x5FAC5 (3 bytes/level). ROM-verified vector: seed `0x45820A` /
   `"MazdA"` / level 1 → **0xA07258** (legacy vector 0x3B15E1 was wrong).
   ✓ rimanenza CHIUSA (docs/notes/UDS_SECURITY_MAPPING.md, 2026-08-03): SID 0x27 →
   handler 0x584A0 (tabella 0x5F57C), solo livello 1 (subfunc 0x01/0x02, parità
   seleziona op); seed_gen 0x5699A level≠3 = entropia counter 0xFFFFF430 +
   XOR-mix (55 AA 55 se stato==4, fallback FF FF FF dopo 16 retry); key_validate
   0x56928 tabella 0x5FAA2, b1 = b0 duplicato = SECURITY_STATE_2 @0xFFFFD20C,
   b2 = position_check; LFSR (init per-level @0x5FAC5, taps 0x909028) solo nella
   key transform 0x56ADA.

## Next (Track A residual leaves, post item-1 COMPLETO)

- **`c/security_access.c` — STATUS: DRAFT / UNVERIFIED** structural
  reconstruction: LFSR core (#2 della seed/key) allineato alla ROM, ma ci sono
  discrepanze documentate vs ROM da NON correggere finché non confermate
  (`docs/notes/UDS_SECURITY_MAPPING.md`, §"Discrepanze C c/security_access.c vs
  ROM"); obiettivo: portarlo a differential-verified con l'emulatore.
- **Exhaust windows / residui exhaust-O2 restanti**: verificate
  `exhaust_oxygen_control_19480` e le 6 leaf O2/lambda (item 1); restano le
  foglie exhaust del callgraph (es. `exhaust_control` @0x43F56, citato da
  `c/engineControlCalculateTiming.c`) con ≥2 callers da verificare a scalare
  dalla cima della catena.

## Workflow rules (from AGENTS.md)

- Work from confirmed evidence; confirmed facts → `docs/notes/FINDINGS.md`.
- Every C lift must be verified against the emulator with random-input tests before
  being marked verified; update `c/verified_addrs.txt`.
- Before editing any binary: verify checksum, assert expected bytes, write to `tmp/`
  first.
- Update the session notes (kept in private storage, not shipped) at end of each
  session (current task, last state, next step, open questions ≤ 3).
- Never commit unless asked; leave the repo as found otherwise.
- `verify_emu.py` is the quick Track A cross-check (`make c-emu`).
