# Track A — functional (behavior-equivalent) C

Readable C that reproduces each function's **behavior**, not its bytes. This
complements the byte-exact asm oracle (`src/*.s`): the oracle guarantees the
rebuild; Track A makes the firmware understandable and moddable.

## Method (per function)

1. Take the name/behavior from **equinox** (hand-annotated Ghidra) where available,
   and confirm it against the disassembly.
2. Write clean C in `c/<name>.c`, with the original SH-2 listing in the header.
3. **Verify behavior**: `c/tests/test_<name>.c` holds `ref()` — a *mechanical
   transcription of the ROM instructions* (register by register) — and asserts the
   lift `== ref` over edge cases + many random inputs. Built with the **host**
   compiler, so no SH toolchain is needed to prove behavior:

   ```bash
   make c-test
   ```

4. **Target build** (compile to SH-2) is done in the build environment with an
   `sh-elf` GCC (`sh-elf-gcc -m2 -mb -O2 -c`). It is *not* required to validate
   behavior. Note: Debian/Ubuntu's `sh4-linux-gnu` GCC is SH4-only and rejects
   `-m2`; use the Renesas SH GNU toolchain or a source-built `sh-elf-gcc`.

## Verification tooling

Besides per-function transcription tests, there is a reusable **SH-2E emulator**
(`tools/sh2emu.py`, integer **+ single-precision FPU**) that executes the *actual ROM
bytes* of a function. `make c-emu` compiles each lift and compares it to the
emulated ROM over random inputs — the strongest check, and it also covers functions
that read memory / call helpers / do float math. Add a row per function to
`c/tests/verify_emu.py`.

FPU validated: `fadd/fsub/fmul/fdiv/fmac/fmov(.s)/float/ftrc/fsts/flds` executed on
assembled SH bytes match the expected math over 30k+ random inputs each.

## Done

- **add16bitSaturate** (0x2460) — saturating unsigned 16-bit add,
  `min(add1+add2, 0xFFFF)`. Verified: transcription (65536×8 edges + 20M random) **and**
  emulated ROM.
- **addSaturate8Bit** (0x2478) — saturating unsigned 8-bit add, `min(add1+add2, 255)`.
  Verified vs emulated ROM (100k random).
- **2DLookup / TwoDLookup** (0x2068) — the core 1-D interpolated **calibration-map read**
  (axis search → typed-cell linear interp → optional scale/offset). Verified vs emulated
  ROM: axis-search helper 0x2624 = 20000/20000; full lookup (type=16 s16) = 15000/15000.
  This is the FPU-using primitive behind every 1-D map (RPM→timing, temp→enrichment, …).
- **3dLookup / ThreeDLookup** (0x20DC) — the 2-D **bilinear** calibration-map read
  (search both axes → bilinear interp → optional scale/offset). Verified vs emulated ROM
  (type=16 s16): 10000/10000. This is the primitive behind the main **fuel & ignition
  maps** (RPM × load surfaces).
- **firstOrderFilter** (0x23B0) — first-order IIR filter with a not-finite bootstrap and a
  minimum-change deadband: `filtered = ff*sig + (1-ff)*sigprev`, snap to `sig` on tiny change,
  return `sig` if `sigprev` is inf/NaN. Verified vs emulated ROM: 30004/30004 incl. inf/NaN edges.
- **knockSensorADCFault** (0xC290) — range-checks the knock-sensor ADC against two ROM
  thresholds and writes a fault byte (1=open/over-range, 2=short/under-range, 0=ok). Verified vs
  emulated ROM across **all 65536** ADC values: 65536/65536. Test: `c/tests/test_knockSensorADCFault.py`.
- **math_primitives.c** — the 10 most-called scalar leaf helpers (0x23B0–0x2510 cluster):
  `subtractAbsolute`, `saturateLow`, `minValue`, `saturate`, `encode` (value/complement checksum),
  `isNotZero_wDivideByZeroProtect`, `floatToFP_16bit`, `floatToInt` (float→u8), `fixedPointToFloat_16bit`,
  `fixedPointToFloat_8bit`. Together called from **hundreds** of sites — this pins the scalar-math layer
  under fueling/ignition/sensors. Each verified vs emulated ROM over 30000 single-precision inputs:
  0 mismatches. Test: `c/tests/test_math_primitives.py`. (Required adding `cmp/pz`/`cmp/pl` to `tools/sh2emu.py`.)
- **mem_accessors.c** — the redundant RAM accessor layer (`readValue_8bit` 0x3E0DC, `readValue_16bit`
  0x3E11C, `updateMemoryAtAddress_8bit` 0x3E1F8, `updateMemoryAtAddress_16bit` 0x3E208): safety-critical
  variables stored as value + bitwise complement; reads validate and fall back to a caller default on
  corruption. Foundational (read_8bit ~129x, update_8bit ~145x callers). Verified vs emulated ROM 20000
  inputs each (valid + corrupted), 0 mismatches; getSR/setSR/error-flag wrappers stubbed. Test:
  `c/tests/test_mem_accessors.py`. (Required fixing sh2emu's `mov.b/w @(disp,Rm),R0` mask 0xF00F->0xFF00.)
- **mem_accessors.c (32-bit/float + validate-only variants)** — `readValue_32bit_ADDRESS_VAL` (0x3E15C),
  `readValue_float_DEFAULTVAL_ADDRESS` (0x3E1AA), `updateMemoryAtAddress_32bit_ADDR_VAL` (0x3E218):
  these use a *different* redundant scheme than the 8/16-bit cells above — an 8-byte cell of
  4-byte value + a 16-bit checksum `~(hi16+lo16)` stored **twice** (addr+4, addr+6), valid if the
  checksum matches *either* copy (confirmed from asm, not a full value complement). Float variant's
  register order is address=r4 (int), dflt=fr4 (float) — independent register files, so the Ghidra
  name's word order isn't the arg order. Also `validateAddressCopy_8bit_ADDRESS` (0x3E29E) and
  `validateAddressCopy_16bit_ADDRESS` (0x3E2DA): validate-only, return an **error code** (0=intact,
  1=corrupted — inverted vs a normal "is valid" bool), no value returned. And
  `validateAddressCopy_float_ADDRESS` (0x3E38A): same checksum scheme, **plus a self-heal side
  effect** — on the valid path it unconditionally rewrites both checksum copies with the freshly
  computed value, repairing whichever copy didn't individually match. Verified vs emulated ROM,
  25000 inputs each (valid + corrupted, incl. the scrub/no-scrub RAM side effect), 0 mismatches.
  Test: `c/tests/test_mem_accessors.py`. The paired error-flag setters `setMemInsideFUNCto1`
  (0x3E3F0, sets byte `0xFFFFC638`=1) and `SetMemoryNotValid2` (0x3E5A8, sets byte `0xFFFFC639`=1)
  are documented structurally (unverified, trivial 8-byte leaves) in
  `docs/functions/setMemInsideFUNCto1.md` and `docs/functions/SetMemoryNotValid2.md`.
- **invertAndReturn_8bit_ADDR** (0x2044, in `math_primitives.c`) — reads a 16-bit big-endian
  (value,complement) cell at a pointer and returns the ones'-complement residual `~(hi8+lo8)`:
  0 iff the pair is self-consistent (same convention as `encode()`/`mem_accessors.c`'s redundant
  cells), nonzero otherwise. Verified vs emulated ROM: 30000 random (full uint8 domain) + 37
  exact-complement edge pairs, 0 mismatches.
- **multiply32Bit_saturating** (0x231C, in `math_primitives.c`) — Q16.16 fixed-point multiply with
  32-bit saturation: `saturate32((int64_t)a * b >> 16)`. Verified vs emulated ROM over the full
  int32 domain (30000 random incl. forced-saturation edges), 0 mismatches. Required adding
  `dmuls.l` and `rotcr` to the sh2emu subclass (base emulator doesn't implement them).
- **fixedPointScaling** (0x2510, in `math_primitives.c`) — despite the ghidra-hand name, NOT a
  unit conversion: an inverse-weighted blend between two ints using an 8-bit fractional counter,
  `a + (int)trunc((b-a) * (1 - frac/256))` (frac==0 -> b, frac==256 -> a). Verified vs emulated
  ROM over the full int32 domain for a,b (30000 random), 0 mismatches — matching the hardware's
  per-operand single-precision int->float rounding (each of a,b cast to float32 individually
  before subtracting) was required to hit 0 mismatches at extreme magnitudes.
- **TwoDLookup_FP_16bit** (0x20C4, in `2DLookup.c`) — a leaner sibling of `TwoDLookup`: same axis
  search (0x2624) but jumps straight to the u16-cell handler (0x26D0), never reading the
  descriptor's type/scale/offset fields — returns the raw interpolated u16 cell value truncated
  to `uint16_t`, no scale/offset applied. Verified vs emulated ROM using a REAL map descriptor
  (60E0FC00.bin @0x67870, a 16-point table found by `tools/mapscan.py`) over 20000+ random/edge
  inputs, 0 mismatches. Test: `c/tests/test_2DLookup_FP_16bit.py`.
- **TwoDLookup_FP_8bit** (0x20AC, in `2DLookup.c`) — the u8-cell sibling of `TwoDLookup_FP_16bit`:
  same axis search (0x2624), jumps to the u8-cell leaf (0x26B0) instead, no scale/offset. Uses a
  genuine fused multiply-add (`fmac`, `fmaf()` in C) for the combine step — a plain `v0+t*(v1-v0)`
  double-rounds and measurably mismatches the ROM. Verified vs emulated ROM using a REAL map
  descriptor (60E0FC00.bin @0x677E8, a 16-point RPM-indexed table) over 10000+ random/edge
  inputs, 0 mismatches. Test: `c/tests/test_2DLookup_FP_8bit.py`.
- **dataLookup** (0x2624, in `2DLookup.c`) — the 1-D axis-search LEAF every lookup above and in
  `3dLookup.c` calls via `bsr` to turn an input into a breakpoint index + interpolation fraction.
  Non-ABI leaf convention: in r0=count/r1=axis ptr/fr0=x, out r0=index/fr0=t. ROM implements a
  BACKWARD linear search (from the last breakpoint down); the C lift keeps the forward-search
  form already used/verified elsewhere in this file since the two are provably equivalent for a
  monotonic ascending axis. First time verified as its OWN standalone function (previously only
  indirectly via its callers). Verified vs emulated ROM (leaf-level register injection via
  `call_leaf`) using the real 60E0FC00.bin @0x67870 axis array over 40000+ random/edge inputs
  (incl. NaN), 0 mismatches. Test: `c/tests/test_dataLookup.py`.
- **ThreeDLookup_FP_8bit** (0x2120, in `3dLookup.c`) — the u8-cell FP-input sibling of
  `ThreeDLookup`: 2-axis search via `indexLookupSomething` (0x2658), hardwired to u8 cells via the
  row-bilinear helper 0x25C8, no scale/offset. Each combine step is a genuine `fmac` (`fmaf()` in
  C). Verified vs emulated ROM using a REAL Map2D descriptor (60E0FC00.bin @0x67898, a 16x6 u8
  surface, X=temp -40..110, Y=1..6) over 10000+ random/edge (x,y) pairs, 0 mismatches. Test:
  `c/tests/test_3DLookup_FP.py`.
- **ThreeDLookup_FP_16bit** (0x213C, in `3dLookup.c`) — the u16-cell sibling of
  `ThreeDLookup_FP_8bit`, row helper 0x25F4 (u16 leaf 0x26D0). Verified vs emulated ROM using a
  REAL Map2D descriptor (60E0FC00.bin @0x68114, a 13x7 u16 surface) over 10000+ random/edge (x,y)
  pairs, 0 mismatches. Test: `c/tests/test_3DLookup_FP.py`.
- **indexLookupSomething** (0x2658, in `3dLookup.c`) — the 2-axis search helper `ThreeDLookup`'s
  FP-input variants dispatch through: runs the same 1-D axis-search leaf (0x2624 = `dataLookup`)
  once per axis. Non-standard multi-value register return (r2=ix, r3=iy, fr0=tx, fr1=ty), modeled
  in C via out-parameters. Verified vs emulated ROM using real Map2D axes (60E0FC00.bin @0x67898,
  16x6 u8 surface) over 10000+ random/edge (x,y) pairs, 0 mismatches. Test:
  `c/tests/test_interp_leaves.py`.
- **interpolate_uint8Table / interpolate_uint16Table** (0x26B0 / 0x26D0, in `interp_leaves.c`) —
  the typed-cell 1-D interpolation LEAVES `TwoDLookup`'s type jump table and the 2-D row-bilinear
  helpers (0x25C8/0x25F4) dispatch to. Non-ABI leaf convention: in r0=index/r1=cell-array
  ptr/fr0=t, out fr2=result (NOT fr0 — left untouched so 2-D callers can reuse it as tx). Reads
  `cell[i]` unconditionally (delay slot), skips reading `cell[i+1]` entirely when t==0.0 (safe for
  axis-search's clamp-high case). Combine step is a genuine `fmac` (`fmaf()` in C, single
  rounding — a plain two-step add/multiply measurably mismatches at the few-ULP level). Verified
  vs emulated ROM (leaf-level register injection via `call_leaf`) using real cell arrays
  (60E0FC00.bin @0x677E8 u8, @0x67870 u16) over 10000+ random/edge inputs each (every index,
  t=0.0 exactly, random t), 0 mismatches. Test: `c/tests/test_interp_leaves.py`.
- **validateAddressCopy_32bit_ADDRESS** (0x3E330, in `mem_accessors.c`) — validate-only sibling of
  `validateAddressCopy_float_ADDRESS` for the same 8-byte checksum-guarded cell, but over a raw
  32-bit VALUE instead of a float bit-pattern; same self-heal side effect (rewrites both checksum
  copies on the valid path). Returns 0=intact, 1=corrupted. Verified vs emulated ROM, 25000+
  inputs (valid1/valid2/invalid checksum-pair modes, incl. scrub/no-scrub RAM side effect), 0
  mismatches. Test: `c/tests/test_mem_accessors.py`.
- **output_spark2_0x8E20** (0x8E20, 60E1D400.bin; CSV/xmap "outputSpark2") — the TRAIL-spark
  per-channel output driver, twin of `output_spark_0x8DE6` (lead, outputSpark1). Wraps the call in
  getSR(16)/setSR, then GATES the whole write+arm on the channel enable byte ch[4]==2 (a trail event
  only fires on a channel the lead side already armed): `*(f32*)ch = value`, ch[6]=0, and calls the
  shared arming helper 0x91FE (ignitonSomethingCalc; the 60E0FC00 instance is 0x91C6). Differs from
  the lead sibling: unconditional vs gated write, clears ch[6] (fired) instead of arming ch[5]/ch[4].
  The dispatcher (0x10F84/0x10FF0, site 0x11050) computes the fr4 value from the split block
  A9A0/A9A4/A9A8/A9AC. Verified vs emulated ROM: 500000 random inputs (5 seeds), 0 mismatches.
  Test: `c/tests/test_output_spark2_0x8E20.py`.

## Next

- Fueling/ignition helpers and CAN handlers — equinox-named on the reliable
  reference; lifts not yet started.
