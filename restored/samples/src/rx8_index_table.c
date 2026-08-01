/*
 * =============================================================================
 * rx8_index_table.c  —  BYTE-INDEXED RAM SLOT-TABLE HELPERS
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Addresses   : 0x68780 (clear) / 0x6879C (step) / 0x687C8 (step2) /
 *               0x687F4 (dec)   — four packed leaves in one region
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               restored/samples/tests/harness_idx_table.py (host-gcc +
 *               mmap vs tools/sh2emu.py over random slot states), in
 *               addition to the existing emulator + host tests
 *               c/tests/test_idx_table_helpers_68780.{py,c}.
 * Lift (truth): c/idx_table_helpers_68780.c (IDA-ai names the leaves
 *               `obd_service_handler_68780/…` — unconfirmed; the leaf
 *               convention in this project names them by behaviour).
 *
 * WHAT THIS IS
 * ------------
 * A table of RAM slots at RX8_IDX_TABLE_BASE (0xFFFFD998), each
 * RX8_IDX_TABLE_STRIDE (0x46C) bytes apart, selected by a byte index.  Only
 * the first three 16-bit words of each slot are touched by this family; the
 * rest of the stride is used by other, not-yet-restored code.  The four
 * leaves implement a small counter protocol:
 *
 *     clear (0x68780)  word0 = word2 = word4 = 0
 *     step  (0x6879C)  word0 = (word4 >= 0x0464) ? 0 : word4 + 1
 *     step2 (0x687C8)  separate ROM copy of `step` (identical logic)
 *     dec   (0x687F4)  word4 = (word0 == 0) ? 0x0464 : word0 - 1
 *
 * `step` copies a count-up of word4 into word0 (resetting at the 0x0464
 * threshold); `dec` copies a count-down of word0 into word4, reloading from
 * 0x0464 when it hits zero.  The two together form a rolling counter pair —
 * the 0x0464 (1124) reload value and the purpose of the table are NOT
 * documented: *unknown, matches ROM*.  The leaves are invoked through the
 * 0x68776 wrapper (`clear(0)`) and through function-pointer tables (literal
 * pools at 0x68CE0 / 0x695C0 / 0x695D0).
 *
 * CALLER-FACING CAVEAT (matches the ROM, not a defect of this model):
 * the slot address is computed in 32-bit arithmetic, so indices >= 9 wrap
 * the pointer to low addresses entirely outside the 4 KB RAM bank
 * 0xFFFFD000..0xFFFFDFFF.  Realistic firmware use is indices 0..8; the
 * harness pins the wrap behaviour on the emulator side.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* One table slot: only the first three words are managed by this family. */
typedef struct {
    uint16_t counter;   /* +0  count-up accumulator (written by step)     */
    uint16_t reserved;  /* +2  untouched by these leaves (unknown role)   */
    uint16_t limit;     /* +4  count-down/reload word (written by dec)    */
} rx8_index_slot_t;

/* The slot pointer is deliberately computed in 32-bit arithmetic exactly
 * like the ROM's `mov` + `mulu.w` + `add` sequence, so indices 9..255 wrap
 * identically. */
static rx8_index_slot_t *rx8_index_slot_ptr(uint32_t idx)
{
    uint32_t addr = RX8_IDX_TABLE_BASE
                  + (uint32_t)(idx & 0xFFu) * RX8_IDX_TABLE_STRIDE;
    return (rx8_index_slot_t *)(uintptr_t)addr;
}

/* 0x68780 — zero the slot's three words. */
void rx8_index_table_clear(uint32_t idx)
{
    rx8_index_slot_t *s = rx8_index_slot_ptr(idx);
    s->counter = 0;
    s->reserved = 0;
    s->limit = 0;
}

/* 0x6879C — count-up step: copy (limit + 1) into counter, resetting to 0
 * once the limit word reaches RX8_IDX_TABLE_LIMIT (0x0464).
 * (cmp/ge with the 0x0464 literal: T = (word4 >= 0x0464), bt -> clear.) */
void rx8_index_table_step(uint32_t idx)
{
    rx8_index_slot_t *s = rx8_index_slot_ptr(idx);
    s->counter = (s->limit >= RX8_IDX_TABLE_LIMIT) ? 0
                 : (uint16_t)(s->limit + 1u);
}

/* 0x687C8 — byte-identical second ROM copy of `step`. */
void rx8_index_table_step2(uint32_t idx)
{
    rx8_index_slot_t *s = rx8_index_slot_ptr(idx);
    s->counter = (s->limit >= RX8_IDX_TABLE_LIMIT) ? 0
                 : (uint16_t)(s->limit + 1u);
}

/* 0x687F4 — count-down step: copy (counter - 1) into limit, reloading from
 * RX8_IDX_TABLE_LIMIT when the counter is zero. */
void rx8_index_table_dec(uint32_t idx)
{
    rx8_index_slot_t *s = rx8_index_slot_ptr(idx);
    s->limit = (s->counter == 0) ? RX8_IDX_TABLE_LIMIT
              : (uint16_t)(s->counter - 1u);
}
