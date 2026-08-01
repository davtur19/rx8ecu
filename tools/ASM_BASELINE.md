# Asm-first baseline — byte-exact reassembly of the stock ROM

**Goal:** turn the read-only disassembly (IDA/Ghidra view) into *buildable* `.s`
source that `sh-elf-as` re-assembles into the **identical ROM bytes**. This gives a
byte-exact, editable, rebuildable baseline **without** the original Renesas/Hitachi
SHC compiler. Functions are then lifted to C one at a time (Track A) while the
baseline always rebuilds.

This is the concrete first step of `../PLANS.md` Track B and de-risks the whole
effort: the byte-exact oracle does not require finding SHC — reassembling the
existing instructions reproduces the bytes by construction. SHC is only needed
later if we want the *C itself* to compile back 1:1 (pure Track B).

## Toolchain (self-contained, no root)

- Disassembler: `capstone` 5.0.x with SH support (`CS_ARCH_SH | CS_MODE_SH2 | CS_MODE_BIG_ENDIAN`)
  + the `disasm_sh2e.py` fallback for the SH-2E decode-gap families.
- Assembler/linker: GNU **binutils-sh-elf** 2.46 (`sh-elf-as -big`, `sh-elf-ld -Ttext=0`, `sh-elf-objcopy -O binary`).
- Fetch without root: `./tools/get_toolchain.sh` (apt-get download + dpkg-deb -x into `tools/toolchain/usr`, idempotent on re-run).
- Encoding sanity (big-endian) verified: `add r5,r4 / extu.w r4,r4 / rts / nop` → `34 5c 64 4d 00 0b 00 09`.

## Whole-ROM rebuild — byte-exact

`tools/rom_rebuild.py` + the `Makefile` reproduce the **entire 512 KB ROM
byte-for-byte** from a single reassembled `.s`:

```bash
./tools/get_toolchain.sh     # one-time
make verify                  # 60E1D400 -> build/out.bin, then cmp
```

Final results (this repo, sh-elf binutils 2.46, ~1.5 s per ROM): **all 9
public stock ROMs byte-exact** (93.5–93.8% in-window instruction lift), see
`../VERIFICATION.md` for the full table; the 10th dataset ROM ([REDACTED]) is
byte-exact verified too but kept private.

Historical development figures (older toolchain, lower coverage) for reference:

| ROM      | Code lifted to instructions | Raw fallbacks | cmp   |
|----------|-----------------------------|---------------|-------|
| 60E1D400 | 165385/195584 words (84.6%) | 5             | MATCH |
| [REDACTED] | 165289/195584 words (84.5%) | 7             | MATCH |
| 60E1C500 | 165434/195584 words (84.6%) | 10            | MATCH |
| 60E32000 | 164858/195584 words (84.3%) | 8             | MATCH |

Method: SH-2 instructions are all 2 bytes, so every even offset in the code window
`0x800..0x60000` is decoded independently — instruction if it re-encodes to the same
2 bytes, else raw `.word`. Everything outside the window (vectors, strings, Hitachi-OS
data, calibration) is `.word` data. Branch/PC-relative operands become `L_xxxxxx`
labels; the whole ROM is one unit linked at VMA 0, so ranges are original. A
self-correcting loop forces any as-rejected or mis-encoding word back to raw,
converging to `cmp == 0`.

The 5–10 raw fallbacks are DATA words capstone over-decodes as extended-SuperH ops
(`ldc.l @rn+,tbr`, `stc.l tbr,@-rn`, `synco`) which sh-elf-as rejects — extra
confirmation the real code is plain SH-2 (SH-2E core). Emitted verbatim, so byte-exactness holds.

This delivers the `../PLANS.md` Track-B **oracle** (and the DoD "`make` reproduces the
stock ROM byte-for-byte") without the original SHC compiler: any future edit is
regression-diffed against this known-good rebuild.

## Per-range prover

`tools/rom2asm.py` emits a reassemblable `.s` for a single range and proves the
round-trip — useful when lifting one function at a time:

```bash
export PATH="$PWD/tools/toolchain/usr/bin:$PATH"
python3 tools/rom2asm.py roms/stock/60E1D400.bin 0x2460 0x2478 --verify   # [OK] MATCH 24 bytes
```

Proven self-contained round-trips on `60E1D400` (byte-exact): 0x2460–0x2478 (24 B),
up to the 200-byte multi-function span 0x23B0–0x2478 (2 pools), and the IPL primitive
0x2054–0x2064.

## Known limits (resolved at whole-program scale)

- **Isolated slices** whose branches/pools point *outside* the slice can't assemble:
  SH short branches (8/12-bit) cannot target undefined externals. The whole-ROM path
  (`tools/rom_rebuild.py`) avoids this by assembling everything as one unit.
- **Code/data classification** currently recovers only *literal pools* (PC-relative
  refs). Jump tables and computed-address data come from the IDA/Ghidra maps — that
  is what the `symbols/` tables and `analysis/data_regions_60E1D400.csv` encode.

## Next steps

All three original next steps (IDA/Ghidra symbol-map ingest, cross-ROM diffing,
Track-A C lifts) are **completed** — see `../VERIFICATION.md` and the `c/` tree.
