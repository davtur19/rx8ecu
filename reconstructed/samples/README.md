# Reconstructed Source Samples — RX-8 PCM (SH7055)

This project is a demonstration sample of "reconstructed source". The C code is abstract, idiomatic, and readable. It would have been the original source of the Mazda/Denso firmware. We reconstructed it from the verified lifts of the `rx8ecu` project. It is proven equivalent to the ROM, function by function.

It is not instruction-by-instruction decompilation. That is `c/`. It is not byte-exact assembly. That is `src/`. It is a readable C model. It uses meaningful names, named constants, data structures, and a shared register map. It must keep the same behavior as the ROM for every possible input.

```
src/  (assembly annotato, byte-exact, rebuild con rom_rebuild.py)   ← LA VERITÀ
c/    (decompilazione C istruzione-per-istruzione, verificata con sh2emu.py)
reconstructed/samples/  (C astratto "come il vero sorgente", verificato  ← QUESTO
                    con lo stesso emulatore sui lift di c/)
```

---

## 1. Relation to the Byte-Exact Build

| Level | What it is | Role |
|---|---|---|
| `src/60E1D400_annotated.s` | ROM assembly, reassembled byte-exact by `tools/rom_rebuild.py` | **Reference truth**. If a C model diverges, the assembly wins. |
| `c/` | C lift, instruction by instruction (track A/B), verified against the ROM with `tools/sh2emu.py` | **Source of derivation** for this project. |
| `reconstructed/samples/` | Abstract and readable C, derived from the lifts, same behavior | **Verified readable model** — not byte-identical. |

The "match-and-compile" step makes this C byte-identical to the ROM. You compile it with an SH-2E compiler. This step is the future evolution. Its outline already exists in `reconstructed/experiments/match/`. It fingerprints the compiler on the prologue/epilogue and on the distinctive ROM instructions. The work in this subproject is the prerequisite. Before you ask a compiler to reproduce a firmware piece byte-identical, that piece must exist as clean and behaviorally correct C.

---

## 2. Included Samples

| Reconstructed name | ROM @ `60E1D400` | Source lift (`c/`) | Harness |
|---|---|---|---|
| `rx8_add_s32_saturate` | `0x2304` | `addS32Saturate.c` (IDA mislabeled `fpu_compare_float`) | `tests/harness_add_s32.py` |
| `rx8_immo_seed_mixer` | `0x366B8` | `seed_mixer.c` (IDA-ai `bitwise_field_encoder_366B8`) | `tests/harness_seed_mixer.py` |
| `rx8_index_table_clear/step/step2/dec` | `0x68780` / `0x6879C` / `0x687C8` / `0x687F4` | `idx_table_helpers_68780.c` | `tests/harness_idx_table.py` |

Why these three:

- **`rx8_add_s32_saturate` (0x2304)** — the classic saturating arithmetic helper. It shows how an SH-2 instruction (`addv`) becomes a portable and well-defined C idiom. The two saturation clauses replicate the ROM overflow branch exactly.
- **`rx8_immo_seed_mixer` (0x366B8)** — cryptographic primitive of the immobilizer. It shows how a "magic" bit-twiddling sequence organizes into named steps, constants (`MIX_SWAP_LO`, `MIX_SWAP_HI`, `MIX_KEEP`, `MIX_FOLD_*`), and comments on the *why* (anti-replay). It keeps every single ROM operation intact.
- **`rx8_index_table` (0x68780 family)** — family of helpers for an indexed RAM table. It shows the use of a **data structure** (`rx8_index_slot_t`), the shared register map, and the honest documentation of an unexplained magic value (`0x0464`, *unknown, matches ROM*). It also shows the real caveat of the 32-bit pointer arithmetic that wraps for indices ≥ 9.

---

## 3. Adopted Style Criteria

1. **Header of each function/file** with: name, ROM address, source ROM, state (`VERIFIED — behavioural equivalence …`), and the link to the lift in `c/` that is the source of truth.
2. **Meaningful names** and named constants. No magic number appears in the body. When the documentation does not explain a value, the value remains a constant with the note `unknown, matches ROM`.
3. **Typed register map** in `include/rx8_hw.h` — *only* documented addresses (with the cited source). What is not documented remains an explicit pointer in the sample code with a note.
4. **Data structures** where needed (`rx8_index_slot_t`, explicit types `int32_t`/`uint16_t`/… to replicate the SH-2 semantics).
5. **No `goto`** except where semantically necessary. None exists in the samples. Loops and `if` statements are natural.
6. **Behavioral equivalence as law**: we do not "fix" the semantics to make them more elegant. Real example: step 4 of `seed_mixer` is `(y << 21) | (y >> 3)`. It is a *fold*, not a standard rotation. The code preserved it verbatim and documented it.
7. **Explicit bit-width arithmetic**: unsigned operands of 32/16/8 bits, explicit casts. This replicates the SH-2E core behavior (wrap, zero/sign extension) also on a 64-bit little-endian host.

---

## 4. How to Run or Regenerate the Verification

Prerequisites: `python3` with `tools/sh2emu.py` (in the repo, already in `sys.path`), system `cc` (host, no cross for the equivalence), ROM `roms/stock/60E1D400.bin` (read only).

```sh
# dall'interno di reconstructed/samples/
make build        # compila i sorgenti + l'oracolo host in /tmp/opencode
make test         # esegue i tre harness di equivalenza
make verify       # alias di test
make clean        # rimuove gli artefatti in /tmp/opencode
```

Alternatively, run them one by one, with N configurable (default: 100000 / 20000):

```sh
python3 tests/harness_add_s32.py 100000
python3 tests/harness_seed_mixer.py 100000
python3 tests/harness_idx_table.py 20000
```

### How a Harness Works (Track-A pattern, identical to `c/tests/verify_emu.py`)

1. compile the reconstructed sources + `tests/host_oracle.c` with the system `gcc`;
2. generate **N random inputs** (fixed seed, reproducible) + edge vectors;
3. **simulate the function on the ROM** with `tools/sh2emu.py` (`cpu.call(entry, …)`) on the same inputs;
4. **execute the abstract C** on the same inputs with the host oracle;
5. **compare the results** — 100% correspondence is required.

For the RAM functions (`rx8_index_table`), the harness compares the **side effects** (the three slot words) instead of the return value. It seeds the RAM in the emulator sparse dict and maps it with `mmap(MAP_FIXED)` on the host. This is the same trick as the companion `c/tests/test_*_49ED0.c` tests.

### Registered Result (2026-08-01)

```
OK  addS32Saturate         host-C == emulated ROM @0x2304  (100000 random + 13 edge)
OK  seed_mixer             host-C == emulated ROM @0x366B8  (100000 random + 12 edge)
OK  idx_table family @0x68780 (clear/step/step2/dec)  (20000 random + 87 edge)
        + wrap pins (indici 9/0x7F/0xFF) verificati emulator-only
```

---

## 5. Era-ROM Toolchain Validation (gcc 3.4.6)

This closes the loop "ROM → abstract C → era-ROM toolchain (sh-elf **gcc 3.4.6**)" on the **behavioral plane**. We do not claim byte identity. We demonstrate that the **same** abstract C, compiled with the period compiler (`-m2e -O1 -fomit-frame-pointer`, `/home/davide/gcc346-build/gcc/xgcc`, system binutils `/usr/bin/sh-elf-*`), behaves **identically** to the ROM bytes function by function, in the **same** emulator `tools/sh2emu.py`.

### Method

For each function of `tests/verify_gcc346.py::FUNCS`:

1. create the minimal stubs `stdint.h` / `math.h` once in `/tmp/verify_gcc346/inc` (gcc 3.4.6 is configured with `--without-headers`);
2. compile the source `src/rx8_*.c` with the recipe `-m2e -O1 -fomit-frame-pointer` (`-m2e` for the single-precision FPU);
3. link at fixed base `0x4000` with a simple linker script. Pull in the 3.4.6 `libgcc.a` helpers (`___sdivsi3`/`___udivsi3`/`___ashlsi3`/`___lshrsi3`/`___ashrsi3`/`___ashiftrt_r4_8`). The L-2 integer families (div/shift) compile to these helpers. The SH-2E core has no hardware division and no variable-count shift;
4. `sh-elf-objcopy --only-section=.text` extracts a code-only blob;
5. load the blob in the emulator sparse `ram` dict at `0x4000`;
6. generate **N seeded vectors** (yielded by `make_rng`) + a small edge set for the saturation/boundary functions;
7. execute the **real ROM** at `ADDR_ROM` and the **gcc-3.4.6 blob** at `0x4000` on the same vectors. Compare `r0` (for `float`, also the `fr` registers; for the RAM family, the slot side effects);
8. where a host oracle is available (`tests/oracle_*.c`, `host_oracle.c`), also compare **host-C vs blob**.

### Command

```sh
cd reconstructed/samples
python3 tests/verify_gcc346.py          # N default per funzione
make verify-gcc346                       # target Makefile (stesso runner)
```

### Result (2026-08-03) — Complete Pure-Math Set

We verified the Lot 1 rows (the 13 Lot 1 leaf + the `index_table` family) with `verify_gcc346.py` / `verify_gcc346_fast.py`. We re-fuzzed them with `fuzz_14funcs.py` (TARGET_N `100000`/function). The exhaustive sweeps `verify_complement_exhaustive.py` also cover them (~all the `u16` values for the complement routines). The Lot 2 rows cover all the new float/interp/memcpy/div-mod/fixed-point functions registered by the `verify_*.py` in `tests/` (each with simple edges + seeded random). **0 mismatch on all.**

| Function | ROM @ | type | harness | n_test | mismatch |
|---|---|---|---|---|---|
| `rx8_add_s32_saturate` | 0x2304 | int32×2→r0 | verify_gcc346 / fuzz_14funcs | 4000 | 0 |
| `rx8_immo_seed_mixer` | 0x366B8 | uint32×2→r0 | verify_gcc346 / verify_immo_exhaustive | 4000 | 0 |
| `rx8_add16bit_saturate` | 0x2460 | u16×2→r0 | verify_gcc346 | 4000 | 0 |
| `rx8_add_saturate_8bit` | 0x2478 | u8×2→r0 | verify_gcc346 | 4000 | 0 |
| `rx8_multiply32_saturating` | 0x231C | int32×2→r0 | verify_gcc346 | 20000 | 0 |
| `rx8_complement_shift_u16` | 0x2430 | u16→r0 | verify_gcc346 / complement_exhaustive | 4000 | 0 |
| `rx8_complement_shift_u32` | 0x2440 | fr4/fr5/fr6→r0 | verify_gcc346 / complement_exhaustive | 4000 | 0 |
| `rx8_complement_shift_u8` | 0x2420 | u8→r0 | verify_complement_exhaustive | 4000 | 0 |
| `rx8_index_table` (clear/step/step2/dec) | 0x68780 | family RAM (idx→slot) | verify_gcc346 / verify_idxtable_all | 5000 | 0 |
| `rx8_div32_signed` | 0x3FE8 | r0/r1→r0 (div, wrap su INT32_MIN/-1) | verify_gcc346 | 4000 | 0 |
| `rx8_div32_unsigned` | 0x409C | r0/r1→r0 (div) | verify_gcc346 | 4000 | 0 |
| `rx8_shift_left_logical` | 0x4308 | r0/r1→r0 (shl, cnt clamp) | verify_gcc346 | 4000 | 0 |
| `rx8_shift_right_arithmetic` | 0x43C8 | r0/r1→r0 (sra, cnt clamp) | verify_gcc346 | 4000 | 0 |
| `rx8_shift_right_logical` | 0x44E0 | r0/r1→r0 (srl, cnt clamp) | verify_gcc346 | 4000 | 0 |
| `rx8_shift_right_8` | 0x467A | r0→r0 (sra 8) | verify_gcc346 | 4000 | 0 |
| `rx8_manifold_pressure_error_10A88` | 0x10A88 | int Q16.16→r0 | verify_10A88 | 4000 | 0 |
| `rx8_set_register_reg_bit_val` | 0x4BBC | ptr RAM-cell→r0 | verify_setregbit | 3000 | 0 |
| `rx8_memcpy_bytewise` | 0x42B0 | ptr (void, non-ABI)→dst | verify_memcpy | 3000 | 0 |
| `rx8_checksum_complement_add` | 0x2034 | ptr (u16)→r0 | verify_checksum | 4000 | 0 |
| `rx8_invert_and_return_8bit` | 0x2044 | ptr (u8)→r0 | verify_invert8 | 3000 | 0 |
| `rx8_bytepack8` (converter) | 0x552FE | ptr (u8)→r0 | verify_bytepack | 3000 | 0 |
| `rx8_bytepack16` (inverter) | 0x5530C | ptr (u16)→r0 | verify_bytepack | 3000 | 0 |
| `rx8_delay_loop_n8` | 0x239C | int (u16)→r0=0 | verify_delayloop | 3000 | 0 |
| `rx8_first_order_filter` | 0x23B0 | float (IIR+deadband)→fr0 | verify_firstorder | 4000 | 0 |
| `rx8_min_value` | 0x23F4 | float→fr0 | verify_float_a / verify_saturates2 | 4000 | 0 |
| `rx8_saturate` | 0x2404 | float→fr0 | verify_float_a / verify_saturates2 | 4000 | 0 |
| `rx8_saturate_low` | 0x23E4 | float→fr0 | verify_float_b / verify_saturates2 | 3000 | 0 |
| `rx8_subtract_absolute` | 0x23DC | float→fr0 | verify_float_b / verify_saturates2 | 3000 | 0 |
| `rx8_float_to_int` | 0x24D0 | float (ftrc)→r0 | verify_float_b | 3000 | 0 |
| `rx8_float_to_fp_16bit` (fp16) | 0x24C0 | float (esaustivo u16×4)→fr0 | verify_float_fp16 | 20000 | 0 |
| `rx8_interpolate_u8` | 0x26B0 | table u8 (i,t)→fr | verify_interp8 | 3000 | 0 |
| `rx8_interpolate_u16` | 0x26D0 | table u16 (i,t)→fr | verify_interp16 | 3000 | 0 |
| `rx8_interpolate_s8` | 0x26F4 | table s8 (i,t)→fr | verify_interp_s8 | 3000 | 0 |
| `rx8_interpolate_s16` | 0x2690 | table s16 (i,t)→fr | verify_interp_s16 | 3000 | 0 |
| `rx8_interpolate_f32` | 0x2678 | table f32 (i,t)→fr | verify_interp_f32 | 3000 | 0 |
| `rx8_data_lookup` | 0x2624 | table f32 (i,t)→r0/fr0 | verify_datalookup | ~1000 | 0 |
| `rx8_bitfield_extract_merge` | 0x48C8 | float→r0 + RAM buf | verify_bitfield | 3000 | 0 |
| `rx8_float_to_fixed_16bit` | 0x2490 | float→fixed16 | verify_mathprims | 4000 | 0 |
| `rx8_fixed_point_to_float_8bit` | 0x2500 | fixed8→float | verify_mathprims | 4000 | 0 |
| `rx8_fixed_point_scaling` | 0x2510 | int (frac) | verify_mathprims | 4000 | 0 |
| `rx8_math_min_max_49ed0` | 0x49ED0 | RAM (flag)→r0 | verify_saturates2 | 4000 | 0 |

**Note**: `verify_gcc346_fast.py` is the same Lot 1 set in parallel (multiprocessing). `verify_idxtable_all.py` covers the whole `0x68774..0x68820` family (wrapper `clr`, `clear/step/step2/dec` + extra `step3`). `verify_cross_rom.py` re-verifies `immo_seed_mixer` and `idx_table` on other ROMs (prologue-shifted) — 0 mismatch.

**Totals**: **44 distinct validated functions** (17 Lot 1 leaf — incl. the 4 leaf `index_table` — + 27 Lot 2). The vector sum (default of `n_test`, only the `verify_*`) is **≈179k comparisons**, `0 mismatch` on all. With the exhaustive sweeps (`u16` reverse/complement, `raw` u16 ×4 for fp16, `immo` on 2^16 key_word × specific seeds) and the fuzz (`fuzz_14funcs` 100k/function, `fuzz_l2` 50k/function), the real volume exceeds half a million by far — **claim: complete pure-math set at 0 mismatch.**

### Documented Semantics (summary notes)

- **`0x10A88` Q16.16**: `d = b-a; return d > -0x1E0000 ? d : d+0x01680000` (deadband -30°..360° of the MAP error diff, fixed point at 16 fractional bits).
- **Complement**: 8/16/32-bit "value+ones-complement" pack families; 0x2440 uses the float convention `fr4/fr5/fr6`→`r0`.
- **`rx8_data_lookup` (i,t)**: 2D lookup with interpolation on an f32 array in RAM; non-ABI signature `r0=n, r1=axis, fr0=x`→`r0=idx, fr0=t`.
- **`rx8_memcpy_bytewise`**: non-ABI `void` (bytewise copy, src/dst on internal reglist, exactly as the ROM `0x44B0` calls it inline).
- **`rx8_first_order_filter` (0x23B0)**: 1-pole IIR + single-precision deadband, `flds/sts/and` comparison on the `0x7F800000` pattern (with robustness to finites).
- **`fp16` (0x24C0)**: `raw & 0xFFFF → (float)raw` then `fmac = mult*raw+off`; exhaustive harness on **all the 65536 `u16` values of `raw` × 4 pairs (mult,off)** (~262k sweep vectors) + canonical edges and seeded random.
- **div/mod**: `div32_signed` wraps on `INT32_MIN/-1`→INT32_MIN; `mod32_signed` `B==0` → diag `0x44E` on `0xFFFF7304`; `INT_MIN % −1 → 0` (wrap, like the ROM).

### Note: non-ABI convention of the L-2 functions (r0/r1)

The ROM calls the new functions (`rx8_div32_*`, `rx8_shift_*`) with a **non-standard convention**: operands in `r0`/`r1`, result in `r0` (they are leaf code; the convention is documented in `docs/functions/*.md`). The ROM side uses a dedicated driver (`call_regs` in the harness, the same stub already used by `harness_div32_signed.py` / `harness_shift_right_8.py`). The **gcc-3.4.6 blob** of the same C uses the standard ABI `r4/r5` and runs with `cpu.call(r4=, r5=)`: two different input conventions, same semantic inputs, comparison on `r0`.

### Note: workaround for an emulator gap (`xtrct`)

During the validation, a **bug of `tools/sh2emu.py`** emerged in the `xtrct` instruction. The two shifts have the roles of the source/destination registers inverted. The ROM paths of *these* functions never execute `xtrct`. But gcc 3.4.6 emits it for the 64-bit right shift / extraction of `rx8_multiply32_saturating`. So the blob side needs it. The harness **monkeypatches** the `SH2._exec` method (applies it once, before any call, on both sides) with the correct semantics from the Renesas SH-2 reference manual (`0010nnnnmmmm1101`, destination n = bits 11-8):

```
R[n] = ((R[m] << 16) & 0xFFFF0000) | ((R[n] >> 16) & 0x0000FFFF)
```

The fix must be **promoted to `tools/sh2emu.py`** (outside the scope of this file). This avoids the dependency on the harness patch.

### Limits

- The validated set is **a composition of pure functions** (leaf + a few routines with deterministic RAM side effects: `index_table`, `setregbit`, `math_min_max`, `memcpy`, `bytepack`, `checksum`/`invert` on buffers). The functions with **state/MMIO/long loop** (check `float_validity` @0x46CC, delayloop on extreme domains `n→0xFFFF`) are covered only within the emulator limits. For `delay_loop_n8`, the `.eff` domain is `0..0xFFFF`; values `≥0x10000` would be runaway (the blob truncates, the ROM runs forever) → handled only emulator-side with a step budget.
- The `float` signature uses the ROM convention `fr4/fr5/fr6`; the value comparison is on `r0` (int/uint return of the validated functions) or on the `fr` registers for the leaf that return float (`first_order_filter`, `min_value`, `saturate`, `interp_*`, `fixed_point_to_float`).
- The builder artifacts (`blob bin`, `.o/.elf`, host oracles) go to `/tmp` and are **not** committed.

---

## 6. Open Problems and Known Limits

- **`rx8_index_table`: unknown purpose of the table and unknown threshold `0x0464`** (ROM match). Stride `0x46C` suggests large slots used by other code not yet reconstructed.
- **`rx8_immo_seed_mixer` step 4**: the *fold* `(y << 21) | (y >> 3)` is not a standard rotation; the reason is unknown (ROM match). The function is verified as a pure function; the whole immobilizer flow (`ImmoKeyExpander_365D6`, `ImmoGetSeed_3664E`) is not re-simulated here.
- **Indices `≥ 9` in the table**: the 32-bit pointer arithmetic wraps below `mmap_min_addr` on the host → verified only emulator-side. Realistic use: indices 0..8 (match of the FINDINGS note).
- **Endianness**: the target is big-endian, the host is little-endian. The harnesses compare *numeric values* (they write/read the words with the same layout), so the equivalence is demonstrated; a future byte-exact build must handle the explicit BE access.
- **IDA-ai names** (`fpu_compare_float`, `bitwise_field_encoder_366B8`, `obd_service_handler_68780`) are auto-generated labels, often misleading; in the samples, the reconstructed names + the ROM addresses count.

## 7. Next Step — State Closed

The **behavioral loop** of the era-ROM toolchain is **closed** for the whole pure-math set (section 5). The abstract C, compiled with `gcc 3.4.6` (`-m2e -O1 -fomit-frame-pointer`), is equivalent to the ROM bytes in the same emulator for **44 distinct functions, ≈179k default comparisons, 0 mismatch** (claim §5). These are on board: the float/saturate leaf (saturates2, float_ab), the u8/u16/s8/s16/f32 interpolations, the fixed-point family `0x2490/0x2500/0x2510`, `fp16` 0x24C0 (exhaustive), `data_lookup`, `memcpy`, signed div/mod, and the pointer/RAM routines (`bytepack`, `checksum`, `invert`, `setregbit`, `bitfield`, `math_min_max`, `index_table` at Lot 1).

Known residual points (open state):

1. **`xtrct` fix (emulator) APPLIED (commit `099bf8b`)**: the inverted-roles bug in `tools/sh2emu.py` is fixed (`R[n] = (R[m]<<16) | (R[n]>>16)`). `tools/tests/test_emulator_families.py:348` is updated (83 checks, 0 failure). The remaining `xtrct` monkeypatches on the harnesses are redundant but harmless.
2. **Stability of the ROM at 9 multi-step**: the 9 multi-step still needs stabilization (notes in `docs/`). It is outside the scope of this README.
3. **`rx8_check_float_validity` @0x46CC remains excluded** from the set: the ROM is not a leaf. Before the check, it runs the float→fixed pipeline 0x48C8→0x4740→0x481C and writes RAM at 0xFFFF768C. The C is a pure branch-through (divergence documented by `harness_check_float_validity.py`).
4. **Integrate the CI**: put `make verify-gcc346` in the regression gate (requires the `gcc 3.4.6` binaries and the `sh-elf` binutils on the host).
5. Close the **byte-exact match-and-compile**: use the fingerprinting (`reconstructed/experiments/match/scripts/fingerprint.py`) to tune a `sh-elf-gcc` that produces the same byte sequences as the ROM (`0x2304`, `0x366B8`, `0x68780` family). Now that the behavioral correctness is demonstrated on this chain, the exact byte differences become the next list to refine.
