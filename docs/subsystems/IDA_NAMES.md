# IDA (AI) names — captured + cross-mapped for comparison

The 60E1D400 image was RE'd in IDA with AI assistance (less reliable than equinox's hand Ghidra work, but a plausible name beats `FUN_*`). Names lined up against equinox on the working ROM (60E0FC00).

## Artifacts

- **`symbols_60E1D400_ida.csv`** — full IDA dump, 2789 functions (addr 0x40–0x6C166). ~1105 descriptive, ~1684 generic/address-suffixed (`obd_service_handler_*`, `sub_*`, `nullsub_*`).
- **`symbols_60E0FC00_idamap.csv`** (moved to private storage, not shipped) — 60E0FC00 symbols augmented: equinox `ghidra-hand` kept as-is; **381** previously-unnamed `FUN_*` filled with a *descriptive* IDA name matching uniquely by instruction signature, tagged **`ida-ai-xmap` / DUBIOUS**. Generic IDA names not transferred (add nothing over `FUN_*`).
- **`analysis/compare_equinox_vs_ida.csv`** (private storage, not shipped) — the **132** functions named by *both* equinox and IDA, side by side (reliability check).

Regenerate (inputs are the shipped public CSVs; `_idamap` output + comparison report stay in private storage):
`python tools/idamap.py --src-rom roms/stock/60E1D400.bin --src-syms symbols/symbols_60E1D400_ida.csv --dst-rom roms/stock/60E0FC00.bin --dst-syms symbols/symbols_60E0FC00.csv --out <private-storage>/symbols_60E0FC00_idamap.csv --report <private-storage>/compare_equinox_vs_ida.csv`

## How the two sources compare (132 overlap + verified lifts)

Signature: mnemonics + operands with absolute addresses masked, unique 1:1 only. Read the word-overlap % as noise (different vocabularies). By inspection:

- **Agree on scalar/utility primitives** (IDA often *more* descriptive): `add16bitSaturate` = `saturated_add_u16`; `addSaturate8Bit` = `saturated_add_u8`; `encode` = `complement_shift_u8` (matches verified `(x<<8)|~x`); `multiply32Bit` = `mul32_saturated`; `setRegister_REG_BIT_VAL` = `bitfield_set_or_clear`; watchdog/reset routines line up (`wdt_*`).
- **IDA hallucinates `fpu_*` on non-FP functions** (known failure mode): `setSR_PARAM` (0x2054, integer status-register write) → IDA `fpu_load_zero`; `3dLookup` (0x20DC, verified 10000/10000) → IDA `fpu_div_float`. Both wrong; equinox + verification win. Rare: only 2 of 132 overlaps, 4 of 381 fills.
- **IDA sometimes gives a sharper lead where equinox was unsure**: `mod32_signed` (0x4144, formerly `engineSomethingConditonCheckAndSet?`) → IDA `div32_signed_modulo`; `setRegisters` (0x4D2E) → IDA `atu_timer_full_init` (ATU = Advanced Timer Unit). Worth following up when reversing those.

## Confidence order (unchanged)

`ghidra-hand` (equinox, verified where lifted) **>** `ida-ai-xmap` (DUBIOUS, candidate) **>** `FUN_*`. IDA layer kept in a separate file so it never pollutes the equinox-primary symbol set; use as hints + cross-check, not ground truth.
