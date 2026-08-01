/*
 * =============================================================================
 * rx8_samples.h  —  public API of the reconstructed-source samples
 * =============================================================================
 * Each declaration maps a readable "reconstructed" name to a ROM function whose
 * behaviour has been verified against the real ROM bytes (tools/sh2emu.py).
 * The authoritative lift (instruction-for-instruction C, c/) is always cited
 * in the .c file header.
 *
 *   reconstructed name            | ROM @ 60E1D400 | verified lift (c/)
 *   -------------------------+----------------+---------------------------
 *   rx8_add_s32_saturate     | 0x2304         | addS32Saturate.c
 *   rx8_immo_seed_mixer      | 0x366B8        | seed_mixer.c
 *   rx8_index_table_clear    | 0x68780        | idx_table_helpers_68780.c
 *   rx8_index_table_step     | 0x6879C        | idx_table_helpers_68780.c
 *   rx8_index_table_step2    | 0x687C8        | idx_table_helpers_68780.c
 *   rx8_index_table_dec      | 0x687F4        | idx_table_helpers_68780.c
 * =============================================================================
 */
#ifndef RX8_SAMPLES_H
#define RX8_SAMPLES_H

#include <stdint.h>

/* 0x2304 — saturating signed 32-bit add (SH-2 `addv`); the O2/wideband and
 * knock-trim pipelines use it wherever a sum must never wrap. */
int32_t rx8_add_s32_saturate(int32_t a, int32_t b);

/* 0x366B8 — immobilizer key-mixing primitive (seed_mixer lift).  Pure
 * function of the two 32-bit key words; see rx8_immo_seed_mixer.c. */
uint32_t rx8_immo_seed_mixer(uint32_t key_word, uint32_t rolling_word);

/* 0x68780 family — byte-indexed RAM slot-table helpers.  `idx` is masked to
 * 8 bits; slots 0..8 live in the on-chip RAM window, 9..255 wrap the pointer
 * through 32-bit arithmetic (matches the ROM; see rx8_index_table.c). */
void     rx8_index_table_clear(uint32_t idx);     /* 0x68780 */
void     rx8_index_table_step(uint32_t idx);      /* 0x6879C */
void     rx8_index_table_step2(uint32_t idx);     /* 0x687C8 (separate ROM copy) */
void     rx8_index_table_dec(uint32_t idx);       /* 0x687F4 */

#endif /* RX8_SAMPLES_H */
