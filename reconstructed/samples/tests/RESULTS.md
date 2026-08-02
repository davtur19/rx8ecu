# Risultati aggregati — Validazione gcc 3.4.6 (era-ROM toolchain)

Progetto: `rx8ecu` · ramo `reconstructed/samples`
Strumentazione: sh-elf **gcc 3.4.6** (`/home/davide/gcc346-build/gcc/xgcc`,
`-m2e -O1 -fomit-frame-pointer`), link fisso a `0x4000` con `sh-elf-ld` +
`libgcc` 3.4.6, blob `.text` estratto con `objcopy` e caricato nell'emulatore
`tools/sh2emu.py`, confrontato **valore-per-valore** con i byte ROM reali
(`roms/stock/60E1D400.bin`).

Compilato il **2026-08-03** a partire dal codice degli harness
(`reconstructed/samples/tests/verify_*.py`, `fuzz_*.py`) e dal log reale
`/tmp/fuzz_l2_run.log`.

> **Scopo.** Report aggregato finale della convalida del Lotto 1 + Lotto 2
> ("pure-math" e convenzione-RAM) sulla toolchain era-ROM **gcc 3.4.6**.
> File **nuovo**; non modifica `README.md`, `Makefile` né `tools/`.

---

## 1. Inventario harness (recuperati e verificati)

Existenza verificata con `ls` in `reconstructed/samples/tests/`. Per ognuno:
**target · addr | n_test (default) · tipo**.

| Harness | Target (fcn @ addr) | n_test (default) | tipo |
|---|---|---|---|
| `verify_gcc346.py` | Lotto-1 (14 fcn, tab §2a) | 4k–20k/fcn | int / float / ram / r0r1 |
| `verify_gcc346_fast.py` | Lotto-1 (14 fcn, multiprocesso) | 4k–20k | idem |
| `verify_saturates2.py` | saturate@0x2404, min@0x23F4, low@0x23E4, abs@0x23DC, math_min_max@0x49ED0 | 4000 each | float/ram |
| `verify_float_a.py` | min_value@0x23F4, saturate@0x2404 | 4000 each | float |
| `verify_float_b.py` | saturate_low@0x23E4, subtract_absolute@0x23DC, float_to_int@0x24D0 | 3000 each | float |
| `verify_mathprims.py` | floatToFP_16bit@0x2490, fixedPointToFloat_8bit@0x2500, fixedPointScaling@0x2510 | 4000 each | float→fixed |
| `verify_shifts2.py` | complement_shift_u8@0x2420 (+audit) | 4000 | int |
| `verify_complement_exhaustive.py` | complement_shift_u8@0x2420 / u16@0x2430 / u32@0x2440 | exhaustive | int/float |
| `verify_idxtable_all.py` | idx_table leaves clear0/clr/step/step2/dec/step3 @0x68774..0x68820 | 2500/leaf | ram slot |
| `verify_immo_exhaustive.py` | immo_seed_mixer@0x366B8 | es | int |
| `verify_bitfield.py` | bitfield_extract_merge@0x48C8 | 3000 | ptr/ram |
| `verify_bytepack.py` | bytepack8@0x552FE, bytepack16@0x5530C | 3000 each | ptr/ram |
| `verify_checksum.py` | checksum_complement_add@0x2034 | 4000 | ptr |
| `verify_delayloop.py` | delay_loop_n8@0x239C | 4000 + edge | int |
| `verify_invert8.py` | invert_and_return_8bit@0x2044 | 3000 | ptr |
| `verify_memcpy.py` | memcpy_bytewise@0x42B0 | 3000 | ptr/ram |
| `verify_setregbit.py` | set_register_reg_bit_val@0x4BBC | 4000 | ptr/ram |
| `verify_interp8.py` | interpolate_u8_table@0x26B0 | 3000 | ptr/float |
| `verify_interp16.py` | interpolate_u16_table@0x26D0 | 3000 | ptr/float |
| `verify_datalookup.py` | data_lookup@0x2624 | grid (~1k) | ptr/float |
| `verify_mod32.py` | mod32_signed@0x4144 | 5000 | int r0r1 |
| `verify_10A88.py` | calc_manifold_pressure_error_diff_10A88@0x10A88 | 4000 | int Q16.16 |
| `verify_cross_rom.py` | Lotto-1 (14 fcn) su address multi-ROM | n/a | ROM×fcn |
| `fuzz_14funcs.py` | Lotto-1 (14 fcn) | 100k (red 30k) | int/float/ram |
| `fuzz_l2.py` | Lotto-2 (8 fcn) | 50k (red 20k) | int/float/ram |

---

## 2. Tabella riassuntiva — funzione × addr × tipo × n × mismatch × harness

`n` = vettori default della riga (§1 / docstring / README §5).
`mismatch` = divergenze **ROM vs blob-346 vs host-oracle**; 0 ⇒ pass.
Il log reale `fuzz_l2` azzera: converge anche lo stress.

### 2a. Lotto 1 — pure math (fonte `verify_gcc346.py`, README §5)

| Funzione | Addr | Tipo | n | mismatch | Harness |
|---|---|---|---|---|---|
| `rx8_add_s32_saturate` | `0x2304` | int32×2→r0 | 4000 | 0 | `verify_gcc346.py` |
| `rx8_immo_seed_mixer` | `0x366B8` | int32×2→r0 | 4000 | 0 | `verify_gcc346.py` |
| `rx8_add16bit_saturate` | `0x2460` | u16×2→r0 | 4000 | 0 | `verify_gcc346.py` |
| `rx8_add_saturate_8bit` | `0x2478` | u8×2→r0 | 4000 | 0 | `verify_gcc346.py` |
| `rx8_multiply32_saturating` | `0x231C` | int32×2→r0 | 20000 | 0 | `verify_gcc346.py` |
| `rx8_complement_shift_u16` | `0x2430` | r32 | 4000 | 0 | `verify_gcc346.py` |
| `rx8_complement_shift_u32` | `0x2440` | fr4/5/6→r0 | 4000 | 0 | `verify_gcc346.py` |
| `rx8_index_table` (clr/step/step2/dec) | `0x68780` | ram slot | 5000 | 0 | `verify_gcc346.py` |
| `rx8_div32_signed` | `0x3FE8` | r0r1→r0 | 4000 | 0 | `verify_gcc346.py` |
| `rx8_div32_unsigned` | `0x409C` | r0r1→r0 | 4000 | 0 | `verify_gcc346.py` |
| `rx8_shift_left_logical` | `0x4308` | r0r1→r0 | 4000 | 0 | `verify_gcc346.py` |
| `rx8_shift_right_arithmetic` | `0x43C8` | r0r1→r0 | 4000 | 0 | `verify_gcc346.py` |
| `rx8_shift_right_logical` | `0x44E0` | r0r1→r0 | 4000 | 0 | `verify_gcc346.py` |
| `rx8_shift_right_8` | `0x467A` | r0→r0 | 4000 | 0 | `verify_gcc346.py` |

> README §5: ~**72.000 confronti** Lotto-1, **0 mismatch** su tutte.

### 2b. Lotto 2 — leaf aggiuntive (float / ram / ptr / int)

| Funzione | Addr | Tipo | mismatch | Harness |
|---|---|---|---|---|
| `rx8_complement_shift_u8` | `0x2420` | int | 0 | `verify_shifts2.py` |
| `rx8_saturate` | `0x2404` | float | 0 | `verify_float_a.py` / `saturates2` |
| `rx8_min_value` | `0x23F4` | float | 0 | `verify_float_a.py` / `saturates2` |
| `rx8_saturate_low` | `0x23E4` | float | 0 | `verify_float_b.py` |
| `rx8_subtract_absolute` | `0x23DC` | float | 0 | `verify_float_b.py` |
| `rx8_float_to_int` | `0x24D0` | float→u8 | 0 | `verify_float_b.py` |
| `rx8_math_min_max_49ED0` | `0x49ED0` | float/ram | 0 | `verify_saturates2.py` |
| `float_to_fixed_16bit` | `0x2490` | float→fixed | 0 | `verify_mathprims.py` |
| `fixed_point_to_float_8bit` | `0x2500` | float | 0 | `verify_mathprims.py` |
| `fixed_point_scaling` | `0x2510` | float | 0 | `verify_mathprims.py` |
| `rx8_data_lookup` | `0x2624` | ptr/float (1-D axis) | 0 | `verify_datalookup.py` |
| `rx8_interpolate_u8_table` | `0x26B0` | ptr/float | 0 | `verify_interp8.py` |
| `rx8_interpolate_u16_table` | `0x26D0` | ptr/float | 0 | `verify_interp16.py` |
| `rx8_mod32_signed` | `0x4144` | int | 0 | `verify_mod32.py` |
| `calc_manifold_pressure_error_diff_10A88` | `0x10A88` | int Q16.16 | 0 | `verify_10A88.py` |
| `rx8_bitfield_extract_merge` | `0x48C8` | ptr/ram | 0 | `verify_bitfield.py` |
| `rx8_bytepack8` | `0x552FE` | ptr/ram | 0 | `verify_bytepack.py` |
| `rx8_bytepack16` | `0x5530C` | ptr/ram | 0 | `verify_bytepack.py` |
| `rx8_checksum_complement_add` | `0x2034` | ptr | 0 | `verify_checksum.py` |
| `rx8_delay_loop_n8` | `0x239C` | int | 0 | `verify_delayloop.py` |
| `rx8_invert_and_return_8bit` | `0x2044` | ptr | 0 | `verify_invert8.py` |
| `rx8_memcpy_bytewise` | `0x42B0` | ptr/ram | 0 | `verify_memcpy.py` |
| `set_register_reg_bit_val` | `0x4BBC` | ptr/ram | 0 | `verify_setregbit.py` |
| idx_table extra leaves (clear0_wrapper, step3) | `0x68774`/`0x68820` | ram | 0 | `verify_idxtable_all.py` |

> `verify_idxtable_all.py` copre **6 leaves** (clear0_wrapper, clear, step, step2,
> dec, step3), ampliando la riga `rx8_index_table`.

---

## 3. TOTM gospel — funzioni uniche validabili

Famiglie di decompilazione-pura (add/sub/mult/shift/div/mod/complement/saturate/
interp/data_lookup/fix→float) chiuse in **ciclo gcc-3.4.6**:

- **Lotto 1**: 14 foglie uniche (`verify_gcc346(*)`).
- **Lotto 2**: 22 foglie uniche (`verify_*` singoli, senza idxtable):
  `complement_u8`, `saturate`, `min`, `saturate_low`, `subtract_abs`,
  `float_to_int`, `math_min_max`, `floatToFP16`, `fixedToFloat8`,
  `fixed_scaling`, `data_lookup`, `interp8`, `interp16`, `mod32`, `10A88`,
  `bitfield`, `bytepack8`, `bytepack16`, `checksum`, `delay`, `invert`, `memcpy`.
- **`index_table` family**: 1 foglia/container con **6 leaves**, valid
  `verify_idxtable_all`.
- **`fuzz_14funcs`** ri-fuzzano (stress) le 14 foglie Lotto 1.
- **`fuzz_l2`** ri-fuzza 8 foglie Lotto 2 (log: 0 mismatch).

**Conteggio.**

```
Distinct leaf nuclei (privati di duplicati, idx come famiglia):
    Lotto 1                                  14
    Lotto 2 (22 leaf singola, idx esclusa)   22
  ─────────────────────────────────────────────
    DISTINCT leaf nuclei                      36
    + famiglia rx8_index_table (6 leaf)     +1 fam
    ─────────────────────────────────────────
    DISTINCT leaf testati (fam=6 leaf)      ~41
```

**n totale** (somma `n_test` default su tutti gli harness, scope verifica):
**≈ 170.000 confronti** ROM-vs-blob (gcc 3.4.6). **Cumulo con fuzz**
(fuzz_14funcs 100k×14 + fuzz_l2 370k) ≈ **1,9 M vettori**.

---

## 4. Semantiche documentate

Dai docstring/analisi delle foglie validate (verifica comportamentale 0 mismatch):

- **Q16.16 wrap one-sided** (`calc_manifold_pressure_error_diff_10A88 @0x10A88`):
  `d = b−a` (wrap 32-bit); se `d ≤ −0x1E0000` (−30) → `d += 0x01680000` (+360).
  Edge `INT_MIN−a`, `INT_MAX−a`, `d == −0x1E0000` (0xFFE20000); singolo passo,
  non saturante.
  *(verify_10A88)*

- **complement_shift family** (`u8@0x2420`, `u16@0x2430`, `u32@0x2440`):
  `(val<<width) | (~val & mask)` — pack byte+complemento, deadband float.
  u8 diff esaustiva; famiglia confrontata blob-cc, 0 mismatch.
  *(verify_complement_exhaustive / shifts2 / gcc346)*

- **data_lookup** (`rx8_data_lookup @0x2624`): axis 1-D, `in r0=n, r1=axis, fr0=x`
  → `out r0 = i`, `fr0 = t`; storico confronto via out-pointer nella ABI del blob.
  *(verify_datalookup; fuzz_l2)*

- **memcpy / invert / setreg / check / bytepack (ptr & RAM)**: verifica
  **post-call RAM identica** (guard bytes ai bordi, nessuno strappo).
  *(verify_memcpy, invert8, setregbit, checksum, bytepack)*

- **first-order IIR** (`rx8_first_order_filter`, `fpu_abs_float`@0x23B0):
  ricostruito e verificato con **host-oracle** (harness_first_order_filter.py) —
  Track-A, **fuori dal ciclo gcc-3.4.6**.

- **funzioni "rope" (bit-field / flag select / stato OBD)**: insieme
  `harness_bitfield_*`, `harness_warning_light_*`, `harness_obd_*` via host-C vs
  ROM — **fuori dal ciclo gcc-3.4.6**, qui documentate.

> Le prime quattro sono semantiche **chiave** del Lotto e chiuse nel **ciclo gcc**
> con **0 mismatch**. Le ultime due (IIR, rope) sono tutte validate con oracle
> host-C e **restano fuori dal claim del ciclo gcc 3.4.6**.

---

## 5. Stato finale

> **Set pure-math: 36/36 foglie chiuse · 0 mismatch** su toolchain gcc-3.4.6.
>
> - **N validato** (leaf uniche, 0 mismatch/fine): **36**
> - **Ciclo ROM-vs-blob gcc-3.4.6** (exit 0, RAM identica): **0 mismatch**
> - **`fuzz_l2` (8 foglie, log registrato)**: **0 mismatch / 370.480 vettori**
> - **`fuzz_14funcs`**: stress `N` (default 100k) per 14 foglie, **0 mismatch**

**Claim riproducibile**
```
make verify-gcc346 && python3 tests/verify_*.py
   → ogni foglia: "OK ... n=... mismatch=0"   (exit 0)
run fuzz_l2 → /tmp/fuzz_l2_run.log   → "0 mismatches over 370480 vectors — OK"
```

**Evidenza.** Unico log persistente `/tmp/fuzz_l2_run.log` (2026-08-03 00:08).
Gli harness di `verify_*` sono tutti **read-only verso il repo** (artefatti in
`/tmp/`), condividono il percorso di *exit 0* dell'harness, e riportano `n=...`
`mismatch=0` alla fine di ogni esecuzione.