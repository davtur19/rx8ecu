/* obd_dtc_row_update_0x64490.c
 *
 * ROM: 60E1D400  |  Address: 0x64490  |  Size: 52 bytes (to 0x644C4)
 *
 * OBD DTC-table row update leaf (side-effect only), takes r4 (16-bit value).
 * Active row index = 16-bit word at 0xFFFF8D74; table base 0xFFFF8930,
 * stride 0x34.  Folds a word-delta into the row's delta counter:
 *
 *   row = word@0xFFFF8D74
 *   p   = 0xFFFF8930 + row * 0x34
 *   w   = word@p+0x02
 *   delta = (s16(w) + ((w >> 8) & 0xFF)) - (r4 + ((r4 & 0xFFFF) >> 8))
 *   byte@p+0x32 = (s8(byte@p+0x32) + delta) & 0xFF
 *   word@p+0x02 = r4 & 0xFFFF
 *
 * Verified against ROM emulator: c/tests/test_obd_dtc_row_update_0x64490.py
 * Host C companion:             c/tests/test_obd_dtc_row_update_0x64490.c
 */
#include <stdint.h>

/* 0x64490 — fold the r4 delta word into the active row's counter */
void obd_dtc_row_update_0x64490(uint32_t r4)
{
    uint16_t row = *(volatile uint16_t *)0xFFFF8D74;
    uint8_t *p = (uint8_t *)(0xFFFF8930 + (uint32_t)row * 0x34);
    uint16_t w = *(volatile uint16_t *)(p + 0x02);
    int32_t delta = (int32_t)(int16_t)w + (int32_t)((w >> 8) & 0xFF)
                    - (int32_t)r4 - (int32_t)((r4 & 0xFFFF) >> 8);
    p[0x32] = (uint8_t)((int32_t)(int8_t)p[0x32] + delta);
    *(volatile uint16_t *)(p + 0x02) = (uint16_t)r4;
}
