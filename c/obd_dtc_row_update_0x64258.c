/* obd_dtc_row_update_0x64258.c
 *
 * ROM: 60E1D400  |  Address: 0x64258  |  Size: 70 bytes (to 0x6429E)
 *
 * OBD DTC-table row update leaf (side-effect only).  The DTC table lives
 * at 0xFFFF8930 with 0x34-byte rows; the active row index is the 16-bit
 * word at 0xFFFF8D74.  This function updates the active row twice:
 *
 *   row = word@0xFFFF8D74
 *   p   = 0xFFFF8930 + (row & 0xFFFF) * 0x34      (mulu.w + add, 32-bit wrap)
 *   byte@p+0x32 = (byte@p+0x32 + byte@p+0x07 + 0xFF) & 0xFF   ; +255 == -1
 *   byte@p+0x07 = 1
 *   byte@p+0x32 = (byte@p+0x32 + byte@p+0x08 + 0xF9) & 0xFF   ; +249 == -7
 *   byte@p+0x08 = 7
 *
 * (The second half re-loads the row index and re-derives p — same row.)
 * Return r0 not meaningful — lift returns void.
 *
 * Verified against ROM emulator: c/tests/test_obd_dtc_row_update_0x64258.py
 * Host C companion:             c/tests/test_obd_dtc_row_update_0x64258.c
 */
#include <stdint.h>

/* 0x64258 — update the active DTC-table row's counters */
void obd_dtc_row_update_0x64258(void)
{
    uint16_t row = *(volatile uint16_t *)0xFFFF8D74;
    uint8_t *p = (uint8_t *)(0xFFFF8930 + (uint32_t)row * 0x34);
    p[0x32] = (uint8_t)(p[0x32] + p[0x07] + 0xFF);
    p[0x07] = 1;
    p[0x32] = (uint8_t)(p[0x32] + p[0x08] + 0xF9);
    p[0x08] = 7;
}
