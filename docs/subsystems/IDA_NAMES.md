# IDA (AI) names — captured + cross-mapped for comparison

The 60E1D400 image was reverse-engineered in IDA with AI assistance (less reliable than
equinox's hand Ghidra work, but real effort — a plausible name beats `FUN_*`). This captures
those names and lines them up against equinox on the working ROM (60E0FC00).

## Artifacts

- **`symbols_60E1D400_ida.csv`** — the full IDA dump, 2789 functions (pulled live from the
  open IDB, addr 0x40–0x6C166). ~1105 descriptive, ~1684 generic/address-suffixed
  (`obd_service_handler_*`, `sub_*`, `nullsub_*`).
- **`symbols_60E0FC00_idamap.csv`** (moved to private storage, not shipped — the public repo ships only
  `symbols_60E0FC00.csv`, `symbols_60E0FC00_ghidra.csv`, `symbols_60E1D400_ida.csv` and
  `symbols_60E1D400_merged.csv`) — 60E0FC00 symbols augmented: equinox `ghidra-hand`
  kept as-is; **381** previously-unnamed `FUN_*` slots filled with a *descriptive* IDA name
  that uniquely matches by instruction signature, tagged **`ida-ai-xmap` / DUBIOUS**. Generic
  IDA names are not transferred (they add nothing over `FUN_*`).
- **`analysis/compare_equinox_vs_ida.csv`** (moved to private storage, not shipped) — the **132**
  functions named by *both* equinox and IDA, side by side. This is the reliability check.

Regenerate (inputs are the shipped public CSVs; the `_idamap` output and comparison report are
kept in private storage, not shipped):
`python tools/idamap.py --src-rom roms/stock/60E1D400.bin --src-syms symbols/symbols_60E1D400_ida.csv
--dst-rom roms/stock/60E0FC00.bin --dst-syms symbols/symbols_60E0FC00.csv --out <private-storage>/symbols_60E0FC00_idamap.csv
--report <private-storage>/compare_equinox_vs_ida.csv`

## How the two sources compare (from the 132 overlap + the verified lifts)

Cross-matched by layout-invariant signature (mnemonics + operands with absolute addresses
masked), unique 1:1 only. Read the automated word-overlap % as noise — the two use different
vocabularies. By inspection:

- **Agree on the scalar/utility primitives** (often IDA is *more* descriptive):
  `add16bitSaturate` = IDA `saturated_add_u16`; `addSaturate8Bit` = `saturated_add_u8`;
  `encode` = `complement_shift_u8` (matches the verified `(x<<8)|~x`); `multiply32Bit` = `mul32_saturated`;
  `setRegister_REG_BIT_VAL` = `bitfield_set_or_clear`; watchdog/reset routines line up (`wdt_*`).
- **IDA hallucinates `fpu_*` on non-FP functions** — the known failure mode. `setSR_PARAM`
  (0x2054, integer status-register write) → IDA `fpu_load_zero`; `3dLookup` (0x20DC, a table
  lookup **verified** 10000/10000) → IDA `fpu_div_float`. Both wrong; equinox + our verification win.
  But this is rare: only 2 of 132 overlaps and 4 of 381 fills are `fpu_*`.
- **IDA sometimes gives a sharper lead where equinox was unsure**: `engineSomethingConditonCheckAndSet?`
  (0x4144) → IDA `div32_signed_modulo`; `setRegisters` (0x4D2E) → IDA `atu_timer_full_init` (ATU =
  Advanced Timer Unit). Worth following up when we reverse those.

## Confidence order (unchanged)

`ghidra-hand` (equinox, verified where lifted) **>** `ida-ai-xmap` (DUBIOUS, candidate) **>** `FUN_*`.
The IDA layer is kept in a separate file so it never pollutes the equinox-primary symbol set;
use it as hints and a cross-check, not ground truth.
