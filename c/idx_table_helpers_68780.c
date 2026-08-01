/* idx_table_helpers_68780.c
 *
 * ROM: 60E1D400  |  Region: 0x68780..0x6881E  |  4 packed sub-functions
 *
 * Indexed table helpers over a RAM table at 0xFFFFD998 with stride 0x46C
 * (1132), indexed by byte r4.  All four share the same prologue:
 *   p = 0xFFFFD998 + (r4 & 0xFF) * 0x46C        (32-bit wrap)
 *
 *   0x68780  clear:  word@p = word@p+2 = word@p+4 = 0
 *   0x6879C  step:   word@p = (word@p+4 >= 0x0464) ? 0 : word@p+4 + 1
 *                     (count-up counter; resets once the +4 word reaches the
 *                     0x0464 threshold; cmp/ge r1,r0 with r1=0x0464,
 *                     r0=word@p+4 → T = (r0 >= r1))
 *   0x687C8  step2:  byte-identical logic to 0x6879C (separate ROM copy)
 *   0x687F4  dec:    word@p+4 = (word@p == 0) ? 0x0464 : word@p - 1
 *
 * Callers: 0x68780 is bsr'd from 0x68776 (wrapper calling clear(0));
 * 0x6879C/0x687C8/0x687F4 are invoked via function-pointer tables
 * (pools at 0x68CE0 / 0x695C0 / 0x695D0).
 *
 * Verified against ROM emulator: c/tests/test_idx_table_helpers_68780.py
 * Host C companion:             c/tests/test_idx_table_helpers_68780.c
 */
#include <stdint.h>

#define IDX_BASE 0xFFFFD998u
#define IDX_STRIDE 0x46Cu
#define IDX_THRESH 0x0464u

static uint8_t *idx_p(uint32_t r4)
{
    return (uint8_t *)(IDX_BASE + (uint32_t)(r4 & 0xFF) * IDX_STRIDE);
}

/* 0x68780 — zero the table entry's three words */
void idx_table_clear_68780(uint32_t r4)
{
    uint8_t *p = idx_p(r4);
    *(volatile uint16_t *)p = 0;
    *(volatile uint16_t *)(p + 2) = 0;
    *(volatile uint16_t *)(p + 4) = 0;
}

/* 0x6879C — step: count-up counter, resets to 0 once the +4 word reaches 0x0464 */
void idx_table_step_6879C(uint32_t r4)
{
    uint8_t *p = idx_p(r4);
    uint16_t w4 = *(volatile uint16_t *)(p + 4);
    *(volatile uint16_t *)p = (w4 >= IDX_THRESH) ? 0 : (uint16_t)(w4 + 1);
}

/* 0x687C8 — separate ROM copy of 0x6879C (identical logic) */
void idx_table_step2_687C8(uint32_t r4)
{
    uint8_t *p = idx_p(r4);
    uint16_t w4 = *(volatile uint16_t *)(p + 4);
    *(volatile uint16_t *)p = (w4 >= IDX_THRESH) ? 0 : (uint16_t)(w4 + 1);
}

/* 0x687F4 — dec: count down; wrap from 0 back to 0x0464 */
void idx_table_dec_687F4(uint32_t r4)
{
    uint8_t *p = idx_p(r4);
    uint16_t w = *(volatile uint16_t *)p;
    *(volatile uint16_t *)(p + 4) = (w == 0) ? IDX_THRESH : (uint16_t)(w - 1);
}
