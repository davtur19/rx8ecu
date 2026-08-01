/* obd_dtc_find_0x643D4.c
 *
 * ROM: 60E1D400  |  Address: 0x643D4  |  Size: 66 bytes (to 0x64418)
 *
 * OBD DTC-table search leaf, takes r4 (16-bit key).  Scans the 21 rows of
 * the DTC table (base 0xFFFF8930, stride 0x34) for the first row whose
 * 16-bit word@row matches (r4 & 0xFFFF) AND whose index differs from the
 * active row index (word@0xFFFF8D74); returns byte@row+0x06 sign-extended,
 * or 0 if no such row:
 *
 *   for i in 0..0x14:
 *     p = 0xFFFF8930 + i * 0x34
 *     if word@p == (r4 & 0xFFFF) and i != word@0xFFFF8D74:
 *         return s8(byte@p+0x06)
 *   return 0
 *
 * (Word and byte-0x06 reads sign/zero-extend exactly per the ROM: word via
 * mov.w @Rm,Rn (s16 then extu.w → unsigned), byte06 via mov.b (s8).)
 *
 * Verified against ROM emulator: c/tests/test_obd_dtc_find_0x643D4.py
 * Host C companion:             c/tests/test_obd_dtc_find_0x643D4.c
 */
#include <stdint.h>

#define DTC_BASE 0xFFFF8930u
#define DTC_STRIDE 0x34u
#define DTC_ROWS 0x15u
#define DTC_CURROW 0xFFFF8D74u

/* 0x643D4 — find table row matching r4 and return its byte-0x06 (s8) */
int32_t obd_dtc_find_0x643D4(uint32_t r4)
{
    uint16_t key = r4 & 0xFFFF;
    uint16_t currow = *(volatile uint16_t *)DTC_CURROW;
    for (uint32_t i = 0; i < DTC_ROWS; i++) {
        uint8_t *p = (uint8_t *)(DTC_BASE + i * DTC_STRIDE);
        if (*(volatile uint16_t *)p == key && i != currow) {
            return (int32_t)(int8_t)p[0x06];
        }
    }
    return 0;
}
