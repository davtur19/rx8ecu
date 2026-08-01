# Firmware function reference (RX-8 PCM, SH-2E)

Per-function reverse engineering, in two tiers:

- **Verified lifts** — `c/*.c` — exact, readable C **checked against the emulated ROM**
  (`tools/sh2emu.py`). Trusted. Most lifts carry a verified-address header; see
  `c/README.md` for the method and the per-function verification notes.
- **AI drafts** — the `*.md` files in this folder — structural analysis + draft C produced
  by **Haiku sub-agents** at low cost. Scaffolding, **unverified**; promote to a verified
  lift before trusting the exact math.

### Status legend — verified vs draft

- **Verified:** the function has a matching C lift in `c/` (same name or same ROM
  address) that is checked against the emulated ROM, and/or an entry in
  `c/verified_addrs.txt`. Trust the behavior and the addresses.
- **Draft:** only an AI-generated `*.md` exists here, with no lift in `c/`. Use for
  orientation only — treat every number, address, and code sample as unverified until
  it is promoted to a verified lift.

## Pipeline (how a function gets analyzed)

1. `python tools/extract_func.py roms/stock/60E0FC00.bin <addr> --syms symbols/symbols_60E0FC00.csv`
   → FPU-decoded SH-2E assembly with literal-pool loads resolved (`= value`) and call
   targets named (from equinox's symbols + the known primitives).
2. A Haiku sub-agent reads that dump and writes `<name>.md` here: purpose / inputs / outputs /
   calls / behavior / draft C / confidence.
3. For pure or important functions: exact-lift to `c/<name>.c` and verify vs the emulator
   (`c/tests/`), then move it to the "verified" tier.

Names come from **equinox311's hand Ghidra RE** (program 60E0FC00) — reliable. This is a
**rotary** engine (no cams/poppet valves/VVT); watch for AI piston-engine assumptions.
AI drafts are usually tagged `AI (Haiku) draft, unverified` (older drafts may not be).

> **ROM bank note:** doc addresses are mostly written against the **60E0FC00** ROM
> bank (the equinox hand-RE that names the functions), while the C lifts and `src/`
> annotation target **60E1D400**. The two banks are sibling images with the **same
> function names but no constant address offset** — the per-function shift varies
> (e.g. `knockFunctionInit` 0xC14C→0xC31C, `engineControlCalculateTiming`
> 0x141FC→0x14584). A few newer docs are already 60E1D400-based (their header says
> so). Always resolve a doc address in the bank the doc states before cross-checking
> it against a lift or a `src/` listing — this is the single biggest cross-ROM
> confusion.
