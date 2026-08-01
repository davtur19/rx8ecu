# `tools/` — reverse-engineering & byte-exact rebuild tooling

Self-contained home for **rebuilding and documenting** the RX-8 ECU firmware.
Everything needed to regenerate a ROM from source lives here (plus the shared
data and general tooling at the repo root: `roms/`, `src/`, `symbols/`,
`analysis/`, `c/`, `docs/`).

## Contents

| File | Purpose |
|------|---------|
| `rom_rebuild.py` | Whole-ROM asm-first rebuild: capstone → single `.s` → `sh-elf-as` → **byte-exact** ROM |
| `rom2asm.py` | Per-range reassemblable `.s` + round-trip proof (for lifting individual functions) |
| `organize_src.py` | Emit the **organized, annotated** reassemblable source (`src/*_annotated.s`) |
| `disasm_sh2e.py` | SH-2E decode-gap fallback disassembler (FPU, fpul/fpscr, `mov.l @(disp,Rm)`, SSR/SPC) |
| `sh2emu.py` | SH-2E emulator (integer + single-precision FPU) — Track A oracle |
| `verify_all.sh` | Bulk byte-exact verifier: rebuild + compare **all 9 public stock ROMs** (`make verify-all`) |
| `get_toolchain.sh` | Fetch `sh-elf` binutils without root (apt download + unpack into `./toolchain/usr`; idempotent) |
| `xmap_names.py` | Transfer equinox hand-names across ROMs by content signature |
| `idamap.py` | IDA symbol-map ingestion/derivation helper |
| `mapscan.py` | Scan ROM for calibration tables / data regions |
| `callgraph.py` | Build the call graph (`symbols/callgraph.csv`) |
| `extract_func.py` | Extract a function's bytes/listing for lifting |
| `func_dump.py` | Dump a function's disassembly — moved to private storage (not shipped) |
| `analyze_eeprom.py` | EEPROM data analysis (immobilizer / key material) — moved to private storage (not shipped) |
| `denso_ck.py` | Denso additive checksum verifier |
| `mazda_security.py` | SecurityAccess / immobilizer seed-key primitives |
| `README.md` | This file |
| `ASM_BASELINE.md` | Method, byte-exact proof, coverage, limits, next steps |
| `tests/` | SH-2E family regression tests (`test_decode_families.py`, `test_emulator_families.py`) |
| `toolchain/` | Local `sh-elf` binutils (git-ignored) |

## Quickstart — fresh clone, no hidden environment magic

The toolchain is installed locally and the Makefile/`verify_all.sh` resolve it
themselves, so **no `~/.bashrc` exports are needed**:

```bash
python3 -m pip install capstone --break-system-packages
./tools/get_toolchain.sh        # installs sh-elf binutils locally
make verify-all                 # rebuilds + verifies all 9 public stock ROMs byte-exact
make ROM=roms/stock/60E1D400.bin verify   # single ROM
```

Regenerate the annotated baseline source (equinox + IDA names):

```bash
make src        # 60E1D400 baseline
```

## What this gives you

A byte-exact, rebuildable copy of the stock ROM **without** the original
Renesas/Hitachi SHC compiler — the Track-B reference **oracle** from
[../PLANS.md](../PLANS.md). Edit the `.s`, rebuild, and every change is
regression-diffed against known-good firmware. Details in
[`ASM_BASELINE.md`](ASM_BASELINE.md).

## Related (repo root)

`../PLANS.md` (master plan — single source of truth) · `../roms/ROMS.md` (ROM
catalog) · `../docs/notes/` (KNOWLEDGE / FINDINGS / RESUME) ·
`../c/` (verified C lifts + test suites). Security knowledge now lives in
`../tools/mazda_security.py` and `../c/security_access.c` (the legacy
`../security/` directory was moved to private storage).
