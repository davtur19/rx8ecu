/* bitfield_flag_selector_33A98.c
 *
 * ROM: 60E1D400  |  Address: 0x33A98  |  Size: 82 bytes (to 0x33AEA)
 *
 * Flag-selector leaf (side-effect only): reads a status byte at 0xFFFFCD4E
 * and writes a select code into the top nibble of byte@0xFFFFC05C:
 *
 *   b = byte@0xFFFFCD4E
 *   v = (b & 0x40) ? 0 : (b & 0x20) ? 1 : (b & 0x80) ? 2 : 3
 *   byte@0xFFFFC05C = v << 4        (shll2 r4; shll2 r4 in delay of rts)
 *
 * Priority: 0x40 → 0, 0x20 → 1, 0x80 → 2, else 3 (checked in that order).
 * Return r0 is the last-loaded input byte (sign-extended), not meaningful
 * — lift returns void.
 *
 * NOTE: mov.w sign-extends 0xCD4E → input is 0xFFFFCD4E; the output
 * 0xFFFFC05C comes from a mov.l literal (already full address).
 *
 * Verified against ROM emulator: c/tests/test_bitfield_flag_selector_33A98.py
 * Host C companion:             c/tests/test_bitfield_flag_selector_33A98.c
 */
#include <stdint.h>

/* 0x33A98 — select flag code and pack into top nibble */
void bitfield_flag_selector_33A98(void)
{
    uint8_t b = *(volatile uint8_t *)0xFFFFCD4E;
    uint8_t v = (b & 0x40) ? 0 : (b & 0x20) ? 1 : (b & 0x80) ? 2 : 3;
    *(volatile uint8_t *)0xFFFFC05C = (uint8_t)(v << 4);
}
