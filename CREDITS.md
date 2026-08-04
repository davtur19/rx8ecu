# Credits

This project builds on prior reverse-engineering work. Full credit and thanks to:

## equinox311

- **The original RX-8 PCM reverse-engineering effort and its public repository:**
  <https://github.com/equinox311/Mazda_RX8_PCM_ReverseEngineering>

  What this project takes from it:

  - **Community stock-ROM collection** — the 9 public ROM images in `roms/stock/`
    were sourced from that repository's `Stock_ROMs/` and verified **byte-for-byte
    identical** to it (see `roms/ROMS.md` for the provenance statement).
  - **931 hand-annotated function names** — equinox's hand-done Ghidra work on the
    US 6-port `60E0FC00` ROM (revised 1000+ times): 3,459 functions, of which 931
    carry real hand-written names. They are exported to
    `symbols/symbols_60E0FC00_ghidra.csv` (source column `ghidra-hand`) and
    cross-mapped into the per-ROM `symbols/symbols_*.csv` tables and
    `src/*_annotated.s` sources shipped here.
  - **The equinox reference guide** (see below; same person posting as
    "equinox92") — used for ROM-ID → market/spec variant mapping, hardware
    identification (Renesas HD64F7055 / SH-2E, Denso N3J1-18-881L), the
    ignition/fueling strategy formulas, and Renesas BOOT-mode recovery. A capture
    lives in this project's private reference notes (not shipped in the public
    repo).
  - **Hardware reference photos** of the ECU board (kept in private storage,
    not shipped in the public repo).

- **The equinox reference guide** — "Open Source S1 RX-8 ECU RE, Data Logging &
  Tuning" by **equinox92** (the person behind the RE this repo builds on),
  published on rx8club.com on 2025-01-12. The thread is Cloudflare-gated, so it
  was captured offline for reference:
  <https://www.rx8club.com/series-i-engine-tuning-forum-63/open-source-s1-rx-8-ecu-reverse-engineering-data-logging-tuning-users-guide-276137/>

- License: **verified 2026-08-01 via the GitHub API** — all three upstream
  repositories (`equinox311/Mazda_RX8_PCM_ReverseEngineering`,
  `equinox311/RX8Defs` — a fork of `Rx8Man/RX8Defs` — and `Rx8Man/Rx8Man`)
  return `license: null`, i.e. **no license = all rights reserved**. Treat the
  upstream content per its own terms; this project's derivative work carries
  its own AGPL license but the upstream material itself is not licensed for
  reuse.

## RX8Man / equinox311 (rx8defs)

- **The rx8defs XML definition files** — the calibration-table definitions behind
  `symbols/cal_tables.csv` (1,210 tables):
  - `ECUFlash/RX8BASE.xml` (ECUFlash format)
  - `RomRaider/rx8_defs.xml` + `logger_rx8_defs.xml` (RomRaider editor/logger format)

- Provenance found in the local reference material (GitHub not reachable to
  re-verify live URLs):
  - The defs folder's own `README.md` is titled **"RX8 Man - RX8 ECU
    Definitions"** — "open source ROM definitions for the Series 1 Mazda RX8" —
    and credits the author as **RX8Man**, with support links to
    <https://www.buymeacoffee.com/RX8Man> (project: <https://github.com/Rx8Man/Rx8Man>).
  - This project's internal RE notes (not shipped in the public repo) record that
    `cal_tables.csv` was derived from **equinox311/RX8Defs**
    (<https://github.com/equinox311/RX8Defs>), ECUFlash defs (+ base),
    and the equinox guide likewise points at `equinox311/RX8Defs` for the RomRaider
    editor/logger defs. The mirror in this project was therefore sourced from
    **equinox311's fork** of **RX8Man's** definitions.

- What this project takes from it: the **names and addresses** behind
  `symbols/cal_tables.csv` and the calibration cross-references in the docs
  (`docs/.../CALIBRATION_TABLES_CROSS_REFERENCE.md`). The research effort that
  located those tables is theirs; the credit is for that effort.

- **License: none stated.** The rx8defs mirror contains no LICENSE file and the
  XMLs carry no license header (the RomRaider files carry only the generic
  RomRaider boilerplate). The README offers only donation links. If you
  redistribute defs-derived tables, verify the current terms upstream.

## Other

- **capstone** (SH-2 disassembly engine) — BSD-3-Clause
- **GNU binutils** (sh-elf assembler/linker/objcopy) — GPL-3.0-or-later
- **Ghidra** (NSA) — the analysis tool used to produce the hand-annotated
  reference names; Apache-2.0. **IDA** — used here only for low-confidence
  AI-generated name scaffolding (tagged `ida-ai` in `symbols_60E1D400_ida.csv`); proprietary.
- **RomRaider / ECUFlash** — the defs-driven tuning tools whose XML formats the
  rx8defs files target.
- The **rx8club.com** community forum thread (equinox's guide) as reference
  material.

---

*If any attribution above is wrong or incomplete, please open an issue — credit
where credit is due is the whole point of this file.*
