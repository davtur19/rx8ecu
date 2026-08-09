# Track A — functional (behavior-equivalent) C

Track A is readable C. It reproduces each function's **behavior**, not its
bytes. It complements the byte-exact asm oracle (`src/*.s`). The oracle
guarantees the rebuild. Track A makes the firmware understandable and moddable.

## Method (per function)

1. Take the function name and behavior from **equinox** (hand-annotated Ghidra)
   if available. Confirm them against the disassembly.
2. Write clean C in `c/<name>.c`. Put the original SH-2 listing in the header.
3. **Verify behavior**: `c/tests/test_<name>.c` holds `ref()` — a *mechanical
   transcription of the ROM instructions* (register by register) — and asserts
   the lift `== ref` over edge cases + many random inputs. The **host** compiler
   builds it, so you do not need an SH toolchain:

   ```bash
   make c-test
   ```

4. **Target build** (`sh-elf-gcc -m2 -mb -O2 -c`) happens in the build
   environment. You do not need it to validate behavior. Note:
   Debian/Ubuntu's `sh4-linux-gnu` GCC is SH4-only and rejects `-m2`. Use the
   Renesas SH GNU toolchain or a source-built `sh-elf-gcc`.

## Verification tooling

Besides the per-function transcription tests, a reusable **SH-2E emulator**
exists: `tools/sh2emu.py` (integer **+ single-precision FPU**). It executes the
*actual ROM bytes* of a function. `make c-emu` compiles each lift and compares
it to the emulated ROM over random inputs. This is the strongest check. It also
covers functions that read memory, call helpers, and do float math. Add a row
per function to `c/tests/verify_emu.py`.

FPU validated: `fadd/fsub/fmul/fdiv/fmac/fmov(.s)/float/ftrc/fsts/flds` on
assembled SH bytes match expected math over 30k+ random inputs each.

## Done

- **add16bitSaturate** (0x2460) — adds two u16 values with saturation:
  `min(add1+add2, 0xFFFF)`. Verified: transcription (65536×8 edges + 20M random)
  + emulated ROM.
- **addSaturate8Bit** (0x2478) — adds two u8 values with saturation:
  `min(add1+add2, 255)`. Verified against the emulated ROM (100k random).
- **2DLookup / TwoDLookup** (0x2068) — a 1-D interpolated **calibration-map
  read**: axis search → typed-cell linear interp → optional scale/offset.
  Verified against the emulated ROM: axis helper 0x2624 = 20000/20000; full
  lookup (type=16 s16) = 15000/15000. It uses the FPU and is the primitive
  behind every 1-D map (RPM→timing, temp→enrichment).
- **3dLookup / ThreeDLookup** (0x20DC) — a 2-D **bilinear** calibration-map
  read. Verified against the emulated ROM (type=16 s16): 10000/10000. It is the
  primitive behind the main **fuel & ignition maps** (RPM × load).
- **firstOrderFilter** (0x23B0) — a first-order IIR with a not-finite bootstrap
  and a minimum-change deadband: `filtered = ff*sig + (1-ff)*sigprev`. It snaps
  to `sig` on tiny change. It returns `sig` if `sigprev` is inf/NaN. Verified:
  30004/30004 including inf/NaN edges.
- **knockSensorADCFault** (0xC290) — it range-checks the knock-sensor ADC
  against two ROM thresholds. Fault byte: 1=open/over-range, 2=short/under-
  range, 0=ok. Verified against the emulated ROM across **all 65536** ADC
  values: 65536/65536. Test: `c/tests/test_knockSensorADCFault.py`.
- **math_primitives.c** — the 10 most-called scalar leaf helpers
  (0x23B0–0x2510): `subtractAbsolute`, `saturateLow`, `minValue`, `saturate`,
  `encode` (value/complement checksum), `isNotZero_wDivideByZeroProtect`,
  `floatToFP_16bit`, `floatToInt` (float→u8), `fixedPointToFloat_16bit`,
  `fixedPointToFloat_8bit`. **Hundreds** of sites call them. They pin the
  scalar-math layer under fueling/ignition/sensors. Each verified against the
  emulated ROM over 30000 single-precision inputs: 0 mismatches. Test:
  `c/tests/test_math_primitives.py` (required us to add `cmp/pz`/`cmp/pl` to
  `tools/sh2emu.py`).
- **mem_accessors.c** — a redundant RAM accessor layer (`readValue_8bit`
  0x3E0DC, `readValue_16bit` 0x3E11C, `updateMemoryAtAddress_8bit` 0x3E1F8,
  `updateMemoryAtAddress_16bit` 0x3E208). It stores a value and its bitwise-
  complement. The reads validate; on corruption they fall back to the caller
  default. Foundational (read_8bit ~129x, update_8bit ~145x callers). Verified
  against the emulated ROM: 20000 inputs each (valid + corrupted), 0 mismatches;
  getSR/setSR/error-flag wrappers stubbed. Test:
  `c/tests/test_mem_accessors.py` (required fixing sh2emu's
  `mov.b/w @(disp,Rm),R0` mask 0xF00F→0xFF00).
- **mem_accessors.c (32-bit/float + validate-only variants)** —
  `readValue_32bit_ADDRESS_VAL` (0x3E15C), `readValue_float_DEFAULTVAL_ADDRESS`
  (0x3E1AA), `updateMemoryAtAddress_32bit_ADDR_VAL` (0x3E218). They use a
  different redundant scheme. Each cell is 8 bytes: a 4-byte value + a 16-bit
  checksum `~(hi16+lo16)` stored **twice** (addr+4, addr+6). The cell is valid
  if *either* copy matches. Float arg order: address=r4 (int), dflt=fr4 (float).
  Also `validateAddressCopy_8bit_ADDRESS` (0x3E29E) /
  `validateAddressCopy_16bit_ADDRESS` (0x3E2DA): validate-only, return error
  code (0=intact, 1=corrupted), no value. `validateAddressCopy_float_ADDRESS`
  (0x3E38A): same scheme + **self-heal** (rewrites both checksum copies on the
  valid path). Verified against the emulated ROM: 25000 inputs each (valid +
  corrupted, including scrub/no-scrub RAM side effect), 0 mismatches. Test:
  `c/tests/test_mem_accessors.py`. Error-flag setters `setMemInsideFUNCto1`
  (0x3E3F0, sets 0xFFFFC638=1) and `SetMemoryNotValid2` (0x3E5A8, sets
  0xFFFFC639=1): structural/unverified, in `docs/functions/`.
- **invertAndReturn_8bit_ADDR** (0x2044, in `math_primitives.c`) — reads a
  16-bit BE (value,complement) cell. It returns the ones'-complement residual
  `~(hi8+lo8)`: 0 iff self-consistent (same convention as
  `encode()`/`mem_accessors.c`). Verified: 30000 random (full uint8 domain) +
  37 exact-complement edge pairs, 0 mismatches.
- **multiply32Bit_saturating** (0x231C, in `math_primitives.c`) — Q16.16
  fixed-point multiply with 32-bit saturation:
  `saturate32((int64_t)a * b >> 16)`. Verified over the full int32 domain
  (30000 random including forced-saturation edges), 0 mismatches. It required
  us to add `dmuls.l` and `rotcr` to the sh2emu subclass.
- **fixedPointScaling** (0x2510, in `math_primitives.c`) — despite the
  Ghidra-hand name, NOT a unit conversion: an inverse-weighted blend,
  `a + (int)trunc((b-a) * (1 - frac/256))` (frac==0 → b, frac==256 → a).
  Verified over the full int32 domain (30000 random), 0 mismatches. To match
  the hardware's per-operand int→float32 rounding (each of a,b cast to float32
  before the subtraction) was necessary for 0 mismatches at extreme magnitudes.
- **TwoDLookup_FP_16bit** (0x20C4, in `2DLookup.c`) — a leaner sibling of
  `TwoDLookup`: same axis search (0x2624), jumps straight to the u16-cell
  handler (0x26D0), never reads type/scale/offset. It returns the raw
  interpolated u16 truncated to `uint16_t`. Verified against the emulated ROM
  with a REAL map descriptor (60E0FC00.bin @0x67870, 16-point table found by
  `tools/mapscan.py`) over 20000+ random/edge inputs, 0 mismatches. Test:
  `c/tests/test_2DLookup_FP_16bit.py`.
- **TwoDLookup_FP_8bit** (0x20AC, in `2DLookup.c`) — u8-cell sibling: axis
  search (0x2624), u8 leaf (0x26B0), no scale/offset. The combine is a genuine
  `fmac` (`fmaf()` in C) — plain `v0+t*(v1-v0)` double-rounds and mismatches.
  Verified against the emulated ROM with a REAL map descriptor
  (60E0FC00.bin @0x677E8, 16-point RPM-indexed table) over 10000+ random/edge
  inputs, 0 mismatches. Test: `c/tests/test_2DLookup_FP_8bit.py`.
- **dataLookup** (0x2624, in `2DLookup.c`) — the 1-D axis-search LEAF called
  through `bsr` by every lookup above and in `3dLookup.c`. Non-ABI leaf: in
  r0=count/r1=axis ptr/fr0=x, out r0=index/fr0=t. ROM does a BACKWARD linear
  search; the C lift keeps the forward form already used/verified in this file
  (provably equivalent for a monotonic ascending axis). First verified
  standalone (previously only through callers). Verified against the emulated
  ROM (`call_leaf`) on the real 60E0FC00.bin @0x67870 axis over 40000+
  random/edge inputs (including NaN), 0 mismatches. Test:
  `c/tests/test_dataLookup.py`.
- **ThreeDLookup_FP_8bit** (0x2120, in `3dLookup.c`) — u8-cell FP-input
  sibling of `ThreeDLookup`: 2-axis search through `indexLookupSomething`
  (0x2658), row-bilinear helper 0x25C8, no scale/offset; each combine is `fmac`
  (`fmaf()` in C). Verified against the emulated ROM with a REAL Map2D
  descriptor (60E0FC00.bin @0x67898, 16x6 u8 surface, X=temp -40..110, Y=1..6)
  over 10000+ (x,y) pairs, 0 mismatches. Test: `c/tests/test_3DLookup_FP.py`.
- **ThreeDLookup_FP_16bit** (0x213C, in `3dLookup.c`) — u16-cell sibling, row
  helper 0x25F4 (u16 leaf 0x26D0). Verified against the emulated ROM using a
  REAL Map2D descriptor (60E0FC00.bin @0x68114, 13x7 u16 surface) over 10000+
  (x,y) pairs, 0 mismatches. Test: `c/tests/test_3DLookup_FP.py`.
- **indexLookupSomething** (0x2658, in `3dLookup.c`) — the 2-axis search
  helper the FP variants dispatch through. It runs the 1-D leaf (0x2624 =
  `dataLookup`) once per axis. Non-standard return (r2=ix, r3=iy, fr0=tx,
  fr1=ty), modeled through out-parameters. Verified against the emulated ROM on
  real Map2D axes (60E0FC00.bin @0x67898) over 10000+ (x,y) pairs, 0
  mismatches. Test: `c/tests/test_interp_leaves.py`.
- **interpolate_uint8Table / interpolate_uint16Table** (0x26B0/0x26D0, in
  `interp_leaves.c`) — the 1-D interpolation LEAVES that `TwoDLookup`'s type
  jump table and the row-bilinear helpers (0x25C8/0x25F4) dispatch to. Non-ABI
  leaf: in r0=index/r1=cell ptr/fr0=t, out fr2=result (NOT fr0 — left untouched
  for 2-D tx reuse). Reads `cell[i]` unconditionally (delay slot), skips
  `cell[i+1]` when t==0.0 (safe for clamp-high). Combine is `fmac` (`fmaf()`,
  single rounding; two-step add/mul mismatches at few-ULP). Verified against
  the emulated ROM (`call_leaf`) on real arrays (60E0FC00.bin @0x677E8 u8,
  @0x67870 u16) over 10000+ inputs each (every index, t=0.0, random t), 0
  mismatches. Test: `c/tests/test_interp_leaves.py`.
- **validateAddressCopy_32bit_ADDRESS** (0x3E330, in `mem_accessors.c`) —
  validate-only sibling of `validateAddressCopy_float_ADDRESS` over a raw
  32-bit VALUE; same self-heal. Returns 0=intact, 1=corrupted. Verified against
  the emulated ROM, 25000+ inputs (valid1/valid2/invalid checksum-pair modes,
  including scrub/no-scrub RAM side effect), 0 mismatches. Test:
  `c/tests/test_mem_accessors.py`.
- **output_spark2_0x8E20** (0x8E20, 60E1D400.bin; CSV/xmap "outputSpark2") —
  the TRAIL-spark per-channel output driver, twin of `output_spark_0x8DE6`
  (lead, outputSpark1). getSR(16)/setSR wrap, then GATES write+arm on the
  channel enable byte ch[4]==2 (a trail event only fires on a channel the lead
  side armed): `*(f32*)ch = value`, ch[6]=0, calls the shared arming helper
  0x91FE (ignitonSomethingCalc; 60E0FC00 instance 0x91C6). It differs from
  lead: unconditional vs gated write. It clears ch[6] (fired); it does not arm
  ch[5]/ch[4]. Dispatcher (0x10F84/0x10FF0, site 0x11050) computes fr4 from the
  split block A9A0/A9A4/A9A8/A9AC. Verified against the emulated ROM: 500000
  random inputs (5 seeds), 0 mismatches. Test:
  `c/tests/test_output_spark2_0x8E20.py`.

## Next

- Fueling/ignition helpers and CAN handlers — equinox-named on the reliable
  reference; lifts not yet started.
