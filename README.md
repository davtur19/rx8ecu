# Mazda RX-8 PCM Reverse Engineering

> ⚠️ AI-generated content. Unverified = hypothesis, not ground truth. Only explicit machine-checked claims below are verified.

Byte-exact RE of the **Mazda RX-8 PCM firmware** — Denso **279700-3313**, Renesas **SH-2E
(SH7055/HD64F7055)** 32-bit, big-endian, **512 KB** program flash. Ships tools, annotated
assembly, verified C lifts, analysis, docs, stock ROMs — each ROM rebuilds **byte-identical**.

## Verification methodology

Cascade L1→L6; each claim is machine-checked or tagged `AI draft` / `unverified` / `DRAFT` / `TBD`.

- **L1 — Byte-exact.** Disassemble → one reassemblable GNU-as source → reassemble (`sh-elf`)
  → `sha256sum` must equal ROM. **9/9 byte-exact** (`make verify-all`; single: `make verify ROM=roms/stock/<id>.bin`). [VERIFICATION.md](VERIFICATION.md) §1.
- **L2 — Formal cert.** `tools/verify_formal.py`: 524288/524288 bytes, CFG (18,088 branches,
  18 jump tables, LIVE=0), XREF closure, gap audit. **9/9 CERTIFIED**, deterministic, CI-gated
  (`make cert`). [FORMAL_CERT_60E1D400.md](docs/notes/FORMAL_CERT_60E1D400.md).
- **L3 — Determinism.** Master catalog/CSVs derived from scripts; drift breaks CI.
- **L4 — Differential/emulator.** 1915 py + 26 C suites; each lift vs ROM bytes on
  `tools/sh2emu.py` — **295 emulator-verified** add, 100k+ random inputs/lift. [VERIFICATION.md](VERIFICATION.md) §3–4.
- **L5 — Cross-validation.** Seed/key bit-identical to ConnorRigby (100k clock random +
  400 random seeds + 3 ROM-verified vectors, 0 divergences). Tables vs RomRaider/GROM.
  [test_cross_seedkey.py](tools/tests/test_cross_seedkey.py), [UDS_SECURITY_MAPPING.md](docs/notes/UDS_SECURITY_MAPPING.md) §7.2, [CREDITS.md](CREDITS.md).
- **L6 — Honesty.** Everything else tagged `AI draft` / `unverified` / `DRAFT` / `TBD`.

Hard gates (each with a command):
- Determinism: `python3 tools/gen_manifest.py` — regen MANIFEST.md, no timestamps
- Host C equivalence: `make c-test`
- Emulator oracle: `make c-emu` (`python3 c/tests/verify_emu.py`, 5 lifts × 100k inputs)
- Soft-float sqrt @0x46CC: `python3 c/tests/test_check_float_validity_0x46CC.py`
- Python suites: `python3 tools/run_tests_parallel.py -j 4`; serial: `make test`
- Cross seed/key: `python3 tools/tests/test_cross_seedkey.py`
- Checksum Denso: `python3 tools/denso_ck.py roms/stock/60E1D400.bin` → 0x5AA5A55A
- CI: 4 jobs (`.github/workflows/ci.yml`): verify, tests, catalog, formal-cert

**Not (yet) proven:** semantic meaning of firmware; runtime on real hardware →
[RUNTIME_CERT_PLAN.md](docs/notes/RUNTIME_CERT_PLAN.md), [ECU_CAPTURE_PLAN.md](docs/notes/ECU_CAPTURE_PLAN.md).

## Quick reference

- **9/9 byte-exact + 9/9 formally certified**; code window 0x800..0x60000; SH-2 round-trip 93.46–93.8%.
- Symbols: 56,953 rows → 50,789 real-fnc estimate, 8,006 named, 6,082 categorized.
- 1587 C lifts / 1704 `c/*.c`; **295 emulator**-verified (`c/verified_addrs.txt`).
- Tables: 1,210 cal + 37,121 RomXR/GROM defs / 13 ROM codes; 6,953 call-graph edges; 18 jump tables.
- Docs: 191 function + 15 subsystem; **tests:** 1915 py + 26 C.
- _Counters are snapshot at commit `c12d8bb`; source of truth: `make catalog` / [MANIFEST.md](MANIFEST.md)._
- Links: [Explorer](https://davtur19.github.io/rx8ecu/) · [VERIFICATION.md](VERIFICATION.md)
  · [MANIFEST.md](MANIFEST.md) · [docs/README.md](docs/README.md)
  · [FORMAL_CERT](docs/notes/FORMAL_CERT_60E1D400.md) · [REPLICATION.md](REPLICATION.md).

## Quickstart

Prereqs: Python 3, `make`, C compiler (only `make c-test`), `capstone` (the **only** external dep):

```bash
python3 -m pip install capstone --break-system-packages
./tools/get_toolchain.sh      # one-time; sh-elf binutils into tools/toolchain/ (no root)
make verify-all               # 9/9 BYTE-EXACT
make cert                     # 9/9 CERTIFIED formal cert
make test                     # full regression gate (~21 s)
make c-test && make c-emu     # host C equivalence + emulator oracle
```

`tools/gen_c_lift.py` (and `gen_c_lift_v3.py`) — batch SH-2→C lift generator, emulator-verified.

Fresh clone: [REPLICATION.md](REPLICATION.md) · evidence: [VERIFICATION.md](VERIFICATION.md) · inventory: [MANIFEST.md](MANIFEST.md).

## Repository layout

| Path | Contents |
|------|----------|
| `roms/stock/` | 9 stock ROM images (512 KB each) + `roms/ROMS.md`; `src/` annotated reassemblable asm |
| `c/` | verified C lifts (1599 `c/*.c`), `eeprom_immo.h`, host test suites, `verified_addrs.txt` |
| `tools/` | disassembler, `sh2emu.py`, formal verifier, rebuild scripts, test suites |
| `symbols/` | per-ROM CSV, CATALOG_MASTER.csv, cal_tables.csv, romraider defs, callgraph |
| `analysis/` | data-region classification + formal-verifier ROM configs |
| `docs/` | functions/ subsystems/ notes/ hardware/ (plans + knowledge base) |
| `web/explorer/` | "RX-8 ECU Firmware Explorer" (GitHub Pages) |
| `hardware/` | `HARDWARE_NOTES.md` (board photos + refs in private storage) |

> `docs/maps/`, `docs/analysis/`, `docs/pseudocode/`, `docs/renesis/`, `security/` moved to private storage; `roms/stock/` ships the kept public CSVs.

## `make` targets

- `build` — rebuild `60E1D400.bin` → `build/out.bin` (default)
- `verify` — `cmp build/out.bin <ROM>`; any image via `make verify ROM=roms/stock/<id>.bin`
- `verify-all` — byte-exact check of all 9 ROMs (`./tools/verify_all.sh`)
- `cert` — formal certification of all 9 ROMs (hard gate, ~31 s)
- `all` — `catalog classify test`
- `catalog` — regen `CATALOG_MASTER.csv` + status
- `classify` — regen `FUNCTION_CATEGORIES.csv`
- `test` — Python regression suites (serial gate, ~21 s)
- `test-fast` — same suites via parallel runner
- `c-test` — host-compiled C behavior-equivalence suites
- `c-emu` — C lifts vs `tools/sh2emu.py` on real ROM bytes
- `src` — regenerate `60E1D400` annotated source into `src/`
- `clean` — remove `build/` / artifacts

## Project status

| State | Item | Source of truth |
|---|---|---|
| **Done** | 9/9 byte-exact; 9/9 formal cert (P1–P5 zero LIVE); seed/key bit-identical | VERIFICATION.md; FORMAL_CERT_60E1D400.md; UDS_SECURITY_MAPPING.md |
| **Done** | catalog + named/categorized functions, cal tables, explorer | `CATALOG_MASTER.csv`, `FUNCTION_CATEGORIES.csv`, `cal_tables.csv` |
| **In progress** | naming of ~50,789 est. fns (8,006 named); more lifts + certs | NAMES_STATUS.md, `c/verified_addrs.txt` |
| **Open** | semantic meaning; runtime on real hardware | RUNTIME_CERT_PLAN.md, ECU_CAPTURE_PLAN.md |

## Legal

Firmware © **Mazda/Denso**; stock images + byte-exact `src/*_annotated.s` not AGPL-covered
(unmodified, research only; all rights reserved; already-public stock dumps). Tuned images /
personal dumps **not** included. Unofficial, not affiliated. **AGPL-3.0** ([LICENSE](LICENSE));
repo must remain **public under AGPL-3.0** indefinitely.

## Credits & origins

Refactor + continuation of community RX-8 S1 RE (equinox311, equinox92, connor/rx8-ecu-dump,
rx8defs). Full attribution: [CREDITS.md](CREDITS.md) · methodology: [PLANS.md](PLANS.md).