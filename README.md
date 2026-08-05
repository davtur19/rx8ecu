# Mazda RX-8 PCM Reverse Engineering

> ⚠️ **AI-Generated Content — Feasibility Experiment**
> Everything in this repository is AI-generated unless explicitly stated otherwise (e.g., the community contributions credited below). Content without an explicit verification marker is a hypothesis to be confirmed, not ground truth.

Complete, byte-exact reverse engineering of the **Mazda RX-8 PCM firmware** —
Denso **279700-3313**, Renesas **SH-2E** (**SH7055 / HD64F7055**) 32-bit CPU,
**512 KB** program flash, big-endian. Ships tools, annotated assembly, verified
C reimplementations, analysis, docs, and the stock firmware images — every
shipped ROM rebuilds to **byte-identical** output.

## Verification methodology

The model proposes; every claim below is **machine-checked or explicitly
tagged**. Verification is a cascade (L1→L6); anything not yet through it is
labeled `AI draft` / `unverified` / `DRAFT` / `TBD`.

- **L1 — Byte-exact reassembly.** Disassemble → one reassemblable GNU-as
  source → reassemble with `sh-elf` binutils → `sha256sum` must equal the
  source ROM. **9/9 shipped ROMs byte-exact** (`make verify-all`; single ROM:
  `make verify ROM=roms/stock/<id>.bin`). Evidence: [VERIFICATION.md](VERIFICATION.md) §1.
- **L2 — Formal syntactic certificate.** `tools/verify_formal.py` (per-ROM
  declared configs) checks the annotated source against the ROM bytes:
  partition **524288/524288 bytes covered**, CFG consistency (18,088 branches,
  18 jump tables, LIVE=0), XREF closure (unreferenced data = 0 after declared
  regions), gap audit (9,239 gaps, no hidden code). **9/9 CERTIFIED**,
  deterministic (two runs → byte-identical output), CI-gated via `make cert`.
  Evidence: [FORMAL_CERT_60E1D400.md](docs/notes/FORMAL_CERT_60E1D400.md).
- **L3 — Determinism gates.** Master catalog and category CSVs are derived
  from live repo data by scripts; drift breaks CI.
- **L4 — Differential & emulator tests.** 203 Python + 26 C host suites; every
  C lift is proven against the *actual ROM bytes* on `tools/sh2emu.py`
  (SH-2E integer + single-precision FPU emulator), **270 emulator-verified
  addresses**, 100k+ randomized inputs per key function (add16bitSaturate,
  addS32Saturate, addSaturate8Bit, seed_mixer, calculateImmoSeed).
  Evidence: [VERIFICATION.md](VERIFICATION.md) §3–4.
- **L5 — Cross-validation vs community work.** The seed/key transform is
  **bit-identical** to the independent ConnorRigby implementation — 0
  divergences over 100,000 + 400 + 3 + 1 vectors; real captured seed
  **0x464E7F → key 0xFAFDD8** (both agree). Calibration tables cross-checked
  against RomRaider/GROM defs; names credited (equinox311, connor).
  Evidence: [CROSS_VALIDATION_SEEDKEY.md](docs/notes/CROSS_VALIDATION_SEEDKEY.md),
  [CREDITS.md](CREDITS.md).
- **L6 — Honesty layer.** Everything else is tagged `AI draft` / `unverified`
  / `DRAFT` / `TBD`, and the top banner applies.

**Not (yet) proven:** the *semantic meaning* of the firmware, and runtime
behavior on real hardware. Plans: [RUNTIME_CERT_PLAN.md](docs/notes/RUNTIME_CERT_PLAN.md)
(emulator-based semantic verification without hardware) and
[ECU_CAPTURE_PLAN.md](docs/notes/ECU_CAPTURE_PLAN.md) (live-capture
end-to-end validation).

## Quick reference

- **9/9 ROMs byte-exact + 9/9 formally certified** (`make verify-all`, `make cert`) — code window 0x800..0x60000, SH-2 lift 93.46–93.8% round-trip (true code ≈88–91%).
- **Symbol catalog:** 56,952 deduped rows → **50,676 real-function estimate** (NOISE-filtered), **6,439 named**, **6,082 categorized** (`symbols/CATALOG_MASTER.csv`, `FUNCTION_CATEGORIES.csv`).
- **660 C lifts**, **746 emulator-verified addresses**, 100k+ random vectors per key function (`c/`, `c/verified_addrs.txt`).
- **Tables:** 1,210 calibration tables + 37,121 RomRaider/GROM defs across 13 ROM codes; 6,953 call-graph edges; 18 jump tables.
- **Docs:** 191 function + 15 subsystem docs; **tests:** 203 Python + 26 C suites, regressions 38,008 + 83 ✓.
- **Explore:** [RX-8 ECU Firmware Explorer](https://davtur19.github.io/rx8ecu/) · evidence [VERIFICATION.md](VERIFICATION.md) · inventory [MANIFEST.md](MANIFEST.md) · [docs/README.md](docs/README.md) · formal cert [FORMAL_CERT_60E1D400.md](docs/notes/FORMAL_CERT_60E1D400.md).

## Quickstart

Prerequisites: Python 3, `make`, a C compiler (only for `make c-test`), and the
`capstone` pip package — the **only** external dependency:

```bash
python3 -m pip install capstone --break-system-packages
./tools/get_toolchain.sh        # one-time, idempotent: installs sh-elf binutils into tools/toolchain/ (no root)
make verify-all                 # rebuild + byte-compare ALL 9 public stock ROMs -> 9/9 BYTE-EXACT
make cert                       # formal certification (verify_formal.py) of all 9 ROMs -> 9/9 CERTIFIED
```

`tools/gen_c_lift.py` — batch SH-2→C generator: pure-function lifts + mem mode (RAM-only: param/literal/stack bases), emulator-verified · v3: branch/delay-slot lifts (`tools/gen_c_lift_v3.py`), emulator-verified

Fresh-clone reproduction: **[REPLICATION.md](REPLICATION.md)**. Evidence
(hashes, test runs, coverage tables): **[VERIFICATION.md](VERIFICATION.md)**.
File inventory: **[MANIFEST.md](MANIFEST.md)**.

## Repository layout

| Path | Contents |
|------|----------|
| `roms/stock/` | 9 stock factory ROM images (512 KB each) + `roms/ROMS.md` catalog with sha256 |
| `src/` | Annotated, reassemblable assembly for each ROM (byte-exact rebuildable) |
| `c/` | 660 verified C lifts, `eeprom_immo.h`, host test suites (863 py + 26 c), `verified_addrs.txt` |
| `tools/` | SH-2E disassembler, emulator, formal verifier, ROM rebuild/annotation scripts, `verify_all.sh`, `get_toolchain.sh`, test suites |
| `symbols/` | Per-ROM symbol CSVs, CATALOG_MASTER.csv (56,952 rows), CATALOG_STATUS.md / NAMES_STATUS.md / TABLES_STATUS.md, cal_tables.csv (1,210), romraider_rx8_tables.csv (37,121 defs / 13 ROM codes), callgraph.csv |
| `analysis/` | Code-window data-region classification + per-ROM declared configs for the formal verifier |
| `docs/functions/` | 191 per-function documentation |
| `docs/subsystems/` | 15 subsystem docs + overview, boot sequence, IDA names, maps |
| `docs/notes/` | Knowledge base (FINDINGS, KNOWLEDGE, RESUME, ECU, HARDWARE, CAN_PROTOCOL, RUNTIME_CERT_PLAN, ECU_CAPTURE_PLAN, ...) |
| `docs/hardware/` | Legacy protocol / hardware reference texts |
| `web/explorer/` | Interactive "RX-8 ECU Firmware Explorer" website, deployed to GitHub Pages |
| `hardware/` | Hardware notes (`HARDWARE_NOTES.md`) — board photos & web refs moved to private storage |

> `docs/maps/`, `docs/analysis/`, `docs/pseudocode/`, `docs/renesis/` and `security/`
> were moved to private storage (not shipped); `symbols/` ships the kept CSVs only.

`make` targets: `verify-all` (9/9 byte-exact), `verify` (single ROM),
`cert` (9/9 formal cert), `all` (rebuild `build/out.bin`), `src` (regenerate
60E1D400 annotated source), `c-test` (host C suites), `c-emu` (emulator
cross-checks), `clean`.

## Project status

| State | Item | Source of truth |
|---|---|---|
| **Done** | 9/9 ROMs byte-exact rebuild; 9/9 formal certificates (P1–P5 zero LIVE); seed/key cross-validated bit-identical to community (0 divergences) | `VERIFICATION.md` §1; `FORMAL_CERT_60E1D400.md`; `CROSS_VALIDATION_SEEDKEY.md` |
| **Done** | Symbol catalog, named/categorized functions, cal tables, explorer site | `CATALOG_MASTER.csv`, `FUNCTION_CATEGORIES.csv`, `cal_tables.csv` |
| **In progress** | Naming / categorization of the ~50,676 real-function estimate (6,439 named, 6,082 categorized); function docs (191/…); more C lifts + emulator-verified addresses | `NAMES_STATUS.md`, `CATALOG_STATUS.md`, `c/verified_addrs.txt` |
| **Open** | Semantic meaning of the firmware; runtime on real hardware | `RUNTIME_CERT_PLAN.md`, `ECU_CAPTURE_PLAN.md` |

---

## Legal notice

The firmware is the intellectual property of **Mazda Motor Corporation** and
**Denso Corporation**. The ROM images in `roms/stock/` and the byte-exact
transcriptions in `src/*_annotated.s` are **NOT covered by this repo's AGPL
license**; included unmodified for research, interoperability, and preservation,
all rights reserved. The ROM images are **stock factory firmware already in
public circulation** (community stock-ROM collection, verified byte-identical
to the published dumps); **modified (tuned) images and personal ECU dumps are
intentionally NOT included**. Independent, unofficial research project, not
affiliated with or endorsed by Mazda or Denso. Licensed under AGPL v3 — see
[LICENSE](LICENSE). **Owner policy:** repository must remain **public under
AGPL-3.0** indefinitely — do not make it private or relicense it.

## Credits & origins

From-scratch refactor and continuation of the community RE of the RX-8 S1 PCM:
tooling, rebuild pipeline, and C lifts were written and verified here; function
naming and calibration-table knowledge build on the prior community work below.

- **equinox311** — the original RX-8 PCM RE effort:
  https://github.com/equinox311/Mazda_RX8_PCM_ReverseEngineering
  (community `Stock_ROMs/` collection — the 9 public ROMs here were verified
  byte-identical to it — and the **Ghidra project archives (4 snapshots
  2025–2026)**: 887 hand-annotated function names adopted for 60E0FC00 (1,518
  named in the catalog)).
- **equinox92** — same person; author of the "Open Source S1 RX-8 ECU RE, Data
  Logging & Tuning" guide (rx8club.com, 2025-01-12) used for ROM-variant mapping,
  hardware identification, and the ignition/fueling strategy.
- **rx8-ecu-dump (connor)** — bootloader & variant-ROM analysis
  (https://github.com/ConnorRigby/rx8-ecu-dump): bootloader.bin and EU N3K1EU000
  (HW ID 60E1A500) analysis; 32 boot/init function names (can_init, main_init,
  timer_init, ...) cross-mapped to all 9 banks via content-signature xmap
  (100 catalog rows, source connor-xmap).
- **RX8Man / equinox311 RX8Defs** — the rx8defs XML definition files behind
  `symbols/cal_tables.csv` (1,210 tables): the "RX8 Man - RX8 ECU Definitions"
  project (https://github.com/Rx8Man/Rx8Man), mirrored via
  https://github.com/equinox311/RX8Defs. Additional ROMRaider/GROM definition
  sets (GROM_RomRaider, fork_jfoster_RX8Defs) feed
  symbols/romraider_rx8_tables.csv (37,121 table/scalar defs across 13 ROM
  codes).
- **capstone** (SH-2 disassembly) — BSD-3-Clause; **GNU binutils** (sh-elf) —
  GPL-3.0-or-later; **Ghidra / IDA** — analysis tools.

See **[CREDITS.md](CREDITS.md)** for full attribution, sources, and evidence.
Methodology: [PLANS.md](PLANS.md).
