# VERIFY_SUMMARY — Meta-run COMPLETA harness gcc 3.4.6

Generato da `tests/run_all_verify.py` (meta-runner) con dati reali di esecuzione (subprocess python3, exit code, wall-time, riga finale). Run finale in modalità COMPLETA: include `verify_immo_exhaustive.py` (--with-slow), nessun harness escluso. Questo run è stato eseguito **dopo l'applicazione del fix `xtrct`** in `tools/sh2emu.py` (registri invertiti corretti) e l'aggiornamento di `tools/tests/test_emulator_families.py:348` (0xCCDD1234 → 0x5678AABB); i monkeypatch `xtrct` negli harness risultano ridondanti ma innocui.

| | |
|---|---|
| Data/ora (locale) | 2026-08-03 01:54:03 CEST |
| Data/ora (UTC, JSON) | 2026-08-02T23:54:03+00:00 |
| Macchina | `Linux opencode 7.0.14-6-pve #1 SMP PREEMPT_DYNAMIC PMX 7.0.14-6 (2026-07-20T14:45Z) x86_64 GNU/Linux` |
| Invocazione | `cd reconstructed/samples && python3 tests/run_all_verify.py --with-slow --json tests/_verify_aggregate.json` |
| Esito globale | **ALL OK** (exit 0) — 31 harness, 0 falliti, 0 mismatch |

---

## 1. Harness invocati (31 — TUTTI, nessuno escluso)

| Harness | Exit | Tempo (s) | Mismatch |
|---|---|---:|---:|
| `fuzz_14funcs.py` | 0 | 54.25 | 0 |
| `fuzz_l2.py` | 0 | 224.57 | 0 |
| `verify_10A88.py` | 0 | 0.07 | 0 |
| `verify_bitfield.py` | 0 | 0.18 | 0 |
| `verify_bytepack.py` | 0 | 0.31 | 0 |
| `verify_checksum.py` | 0 | 0.15 | 0 |
| `verify_complement_exhaustive.py` | 0 | 1.66 | 0 |
| `verify_cross_rom.py` | 0 | 3.06 | 0 |
| `verify_datalookup.py` | 0 | 0.16 | 0 |
| `verify_delayloop.py` | 0 | 35.64 | 0 |
| `verify_firstorder.py` | 0 | 0.18 | 0 |
| `verify_float_a.py` | 0 | 0.14 | 0 |
| `verify_float_b.py` | 0 | 0.35 | 0 |
| `verify_float_fp16.py` | 0 | 3.61 | 0 |
| `verify_gcc346.py` | 0 | 3.99 | 0 |
| `verify_gcc346_fast.py` | 0 | 2.02 | 0 |
| `verify_idxtable_all.py` | 0 | 0.53 | 0 |
| `verify_immo_exhaustive.py` | 0 | **285.00** | 0 |
| `verify_interp16.py` | 0 | 0.14 | 0 |
| `verify_interp8.py` | 0 | 0.12 | 0 |
| `verify_interp_f32.py` | 0 | 0.11 | 0 |
| `verify_interp_s16.py` | 0 | 0.15 | 0 |
| `verify_interp_s8.py` | 0 | 0.12 | 0 |
| `verify_invert8.py` | 0 | 0.13 | 0 |
| `verify_mathprims.py` | 0 | 0.37 | 0 |
| `verify_memcpy.py` | 0 | 0.73 | 0 |
| `verify_mod32.py` | 0 | 0.77 | 0 |
| `verify_q4740.py` | 0 | 0.46 | 0 |
| `verify_saturates2.py` | 0 | 0.59 | 0 |
| `verify_setregbit.py` | 0 | 0.18 | 0 |
| `verify_shifts2.py` | 0 | 0.07 | 0 |

---

## 2. Copertura funzioni (48 uniche, dedupe per nome+addr)

| Addr | Funzione | n_test | Mismatch | Harness (primo passante) |
|---|---|---:|---:|---|
| `0x2034` | `rx8_checksum_complement_add` | 4000 | 0 | verify_checksum.py |
| `0x2044` | `rx8_invert_and_return_8bit` | 50000 | 0 | fuzz_l2.py |
| `0x2304` | `rx8_add_s32_saturate` | 4000 | 0 | fuzz_14funcs.py |
| `0x231C` | `rx8_multiply32_saturating` | 20000 | 0 | fuzz_14funcs.py |
| `0x239C` | `rx8_delay_loop_n8` | 50000 | 0 | fuzz_l2.py |
| `0x23B0` | `rx8_first_order_filter` | 3000 | 0 | verify_firstorder.py |
| `0x23DC` | `rx8_subtract_absolute` | 3000 | 0 | verify_float_b.py |
| `0x23E4` | `rx8_saturate_low` | 3000 | 0 | verify_float_b.py |
| `0x23F4` | `rx8_min_value` | 4000 | 0 | verify_float_a.py |
| `0x2404` | `rx8_saturate` | 4000 | 0 | verify_float_a.py |
| `0x2420` | `rx8_complement_shift_u8` | 65536 | 0 | verify_complement_exhaustive.py |
| `0x2430` | `rx8_complement_shift_u16` | 4000 | 0 | fuzz_14funcs.py |
| `0x2440` | `rx8_complement_shift_u32` | 4000 | 0 | fuzz_14funcs.py |
| `0x2460` | `rx8_add16bit_saturate` | 4000 | 0 | fuzz_14funcs.py |
| `0x2478` | `rx8_add_saturate_8bit` | 4000 | 0 | fuzz_14funcs.py |
| `0x2490` | `rx8_float_to_fixed_16bit` | 4000 | 0 | verify_mathprims.py |
| `0x24C0` | `rx8_fixed_point_to_float_16bit` | 20000 | 0 | verify_float_fp16.py |
| `0x24D0` | `rx8_float_to_int` | 3000 | 0 | verify_float_b.py |
| `0x2500` | `rx8_fixed_point_to_float_8bit` | 4000 | 0 | verify_mathprims.py |
| `0x2510` | `rx8_fixed_point_scaling` | 4000 | 0 | verify_mathprims.py |
| `0x2624` | `rx8_data_lookup` | 50000 | 0 | fuzz_l2.py |
| `0x2678` | `rx8_interpolate_f32_table` | 3000 | 0 | verify_interp_f32.py |
| `0x2690` | `rx8_interpolate_s16_table` | 3000 | 0 | verify_interp_s16.py |
| `0x26B0` | `rx8_interpolate_u8_table` | 3000 | 0 | verify_interp8.py |
| `0x26D0` | `rx8_interpolate_u16_table` | 50000 | 0 | fuzz_l2.py |
| `0x26F4` | `rx8_interpolate_s8_table` | 3000 | 0 | verify_interp_s8.py |
| `0x3FE8` | `rx8_div32_signed` | 4000 | 0 | fuzz_14funcs.py |
| `0x409C` | `rx8_div32_unsigned` | 4000 | 0 | fuzz_14funcs.py |
| `0x4144` | `rx8_mod32_signed` | 50000 | 0 | fuzz_l2.py |
| `0x42B0` | `rx8_memcpy_bytewise` | 3000 | 0 | verify_memcpy.py |
| `0x4308` | `rx8_shift_left_logical` | 4000 | 0 | fuzz_14funcs.py |
| `0x43C8` | `rx8_shift_right_arithmetic` | 4000 | 0 | fuzz_14funcs.py |
| `0x44E0` | `rx8_shift_right_logical` | 4000 | 0 | fuzz_14funcs.py |
| `0x467A` | `rx8_shift_right_8` | 4000 | 0 | fuzz_14funcs.py |
| `0x4740` | `softfloat_sqrt_normaliser_4740` | 3000 | 0 | verify_q4740.py |
| `0x48C8` | `rx8_bitfield_extract_merge` | 3000 | 0 | verify_bitfield.py |
| `0x4BBC` | `rx8_set_register_reg_bit_val` | 50000 | 0 | fuzz_l2.py |
| `0x10A88` | `calc_manifold_pressure_error_diff_10A88` | 4000 | 0 | verify_10A88.py |
| `0x366B8` | `rx8_immo_seed_mixer` | 4194304 | 0 | verify_immo_exhaustive.py |
| `0x49ED0` | `rx8_math_min_max_49ed0` | 4000 | 0 | verify_saturates2.py |
| `0x552FE` | `rx8_bytepack8` | 3000 | 0 | verify_bytepack.py |
| `0x5530C` | `rx8_bytepack16` | 3000 | 0 | verify_bytepack.py |
| `0x68774` | `rx8_index_table_clear0_wrapper` | 5000 | 0 | verify_idxtable_all.py |
| `0x68780` | `rx8_index_table_clear` | 5000 | 0 | fuzz_14funcs.py |
| `0x6879C` | `rx8_index_table_step` | 5000 | 0 | fuzz_14funcs.py |
| `0x687C8` | `rx8_index_table_step2` | 5000 | 0 | fuzz_14funcs.py |
| `0x687F4` | `rx8_index_table_dec` | 5000 | 0 | fuzz_14funcs.py |
| `0x68820` | `rx8_index_table_step3` | 5000 | 0 | verify_idxtable_all.py |

---

## 3. TOTALI

- **Harness eseguiti**: **31 su 31** scoperti (0 esclusi)
- **Funzioni coperte** (uniche): **48**
- **Vettori cumulati** (somma n_test, incl. 4.194.304 di `verify_immo_exhaustive`): **4.744.840**
- **Mismatch totali**: **0**

## 4. Note

- **Fix `xtrct` applicato** (`tools/sh2emu.py:274`): `R[n] = (R[m]<<16) | (R[n]>>16)`, ripristina i ruoli dei registri secondo il Renesas SH-2E Software Manual §7.2.68. `tools/tests/test_emulator_families.py:348` aggiornato da `0xCCDD1234` a `0x5678AABB`: `test_emulator_families.py` → **83 checks, 0 failures, exit 0**. I monkeypatch `xtrct` (in `verify_gcc346[,_fast]`, `fuzz_14funcs`, `verify_bitfield`, `verify_bytepack`, `verify_cross_rom`, `verify_float_a`, `verify_idxtable_all`) sono rimasti sugli harness: implementano tutti la semantica **corretta** (identica al fix), quindi sono innocui/ridondanti — nessun harness ha richiesto correzione. Tutta la suite **ALL OK** (31 harness, 0 mismatch).
- **`verify_immo_exhaustive.py` incluso** (run COMPLETA): sweep esaustiva su `rx8_immo_seed_mixer` @0x366B8 — primo input **0..0xFFFF esaustivo** × **64 rolling seed** = **4.194.304 coppie**. Durata reale: **285.00 s** (~4,8 min, sotto i 7 min stimati). Esito: **0 mismatch** (ROM vs blob gcc-3.4.6, per-coppia bit-exact su r0). Ora NON c'è alcun harness escluso.
- **`verify_q4740.py`** (@0x4740): helper soft-float sqrt/normaliser — label disassembler ("q15 saturating mul") errato; validato bit-exact contro un modello Python, **3000 random + 32 edge, 0 mismatch**. Nessun C-lift in `src/` (chiuso vs modello, non ROM-vs-C).
- Discrepanza note sul JSON grezzo: la dedupe di `run_all_verify.py` tiene la **prima** occorrenza per chiave `(name,addr)`, quindi `rx8_immo_seed_mixer` risulta `n=4000` (da `fuzz_14funcs.py`) e `verify_q4740` esce come stub (`addr=null,n=0`); il `total_vectors` grezzo del JSON è pertanto 551.536. Il **totale di questa summary (4.744.840) è quello corretto**, calcolato sommando `n_test` di immo_exhaustive (4.194.304) e di q4740 (3.000). Nessun harness è stato modificato.
- Run eseguito senza modifiche agli harness: `run_all_verify.py` assegna già a `verify_immo_exhaustive` un timeout dedicato (slow-timeout 900 s) — il run è terminato senza bisogno di rilancio singolo né di fix.
- Harness lenti del run: `verify_immo_exhaustive.py` (~285 s), `fuzz_l2.py` (~225 s), `fuzz_14funcs.py` (~54 s), `verify_delayloop.py` (~36 s). Tutti gli altri < 4 s.