/* obd_dtc_row_update_0x64418.c
 *
 * ROM: 60E1D400  |  Address: 0x64418  |  Size: 38 bytes (to 0x6443E)
 *
 * OBD DTC-table row update leaf (side-effect only), takes r4 (byte value).
 * Active row index = 16-bit word at 0xFFFF8D74; table base 0xFFFF8930,
 * stride 0x34:
 *
 *   row = word@0xFFFF8D74
 *   p   = 0xFFFF8930 + row * 0x34
 *   byte@p+0x32 = (s8(byte@p+0x32) + s8(byte@p+0x08) - r4) & 0xFF
 *   byte@p+0x08 = r4 & 0xFF
 *
 * (byte reads are sign-extended mov.b; the 32-bit sum is stored low-byte.)
 * Return r0 = r4 — not meaningful as a real return; lift returns void.
 *
 * Verified against ROM emulator: c/tests/test_obd_dtc_row_update_0x64418.py
 * Host C companion:             c/tests/test_obd_dtc_row_update_0x64418.c
 */
#include <stdint.h>

/* 0x64418 — fold r4 into the active row's delta counter */
void obd_dtc_row_update_0x64418(uint32_t r4)
{
    uint16_t row = *(volatile uint16_t *)0xFFFF8D74;
    uint8_t *p = (uint8_t *)(0xFFFF8930 + (uint32_t)row * 0x34);
    p[0x32] = (uint8_t)((int32_t)(int8_t)p[0x32] + (int32_t)(int8_t)p[0x08]
                        - (int32_t)r4);
    p[0x08] = (uint8_t)r4;
}
