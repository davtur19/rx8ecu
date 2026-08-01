/* obd_dtc_find_0x6443E.c
 *
 * ROM: 60E1D400  |  Address: 0x6443E  |  Size: 82 bytes (to 0x64490)
 *
 * OBD DTC-table search leaf, takes r4 (byte key).  Scans the 21 rows of the
 * DTC table (base 0xFFFF8930, stride 0x34) for the first row whose byte
 * @row+0x06 equals (r4 & 0xFF) AND whose index differs from the active row
 * index (word@0xFFFF8D74); returns byte@row+0x08 sign-extended, or the
 * default 0x08 if no such row:
 *
 *   for i in 0..0x14:
 *     p = 0xFFFF8930 + i * 0x34
 *     if byte@p+0x06 == (r4 & 0xFF) and i != word@0xFFFF8D74:
 *         return s8(byte@p+0x08)
 *   return 0x08
 *
 * (r14 is preloaded with 0x08 and only overwritten on a hit.)
 *
 * Verified against ROM emulator: c/tests/test_obd_dtc_find_0x6443E.py
 * Host C companion:             c/tests/test_obd_dtc_find_0x6443E.c
 */
#include <stdint.h>

#define DTC_BASE 0xFFFF8930u
#define DTC_STRIDE 0x34u
#define DTC_ROWS 0x15u
#define DTC_CURROW 0xFFFF8D74u

/* 0x6443E — find table row matching r4 and return its byte-0x08 (s8) */
int32_t obd_dtc_find_0x6443E(uint32_t r4)
{
    uint8_t key = r4 & 0xFF;
    uint16_t currow = *(volatile uint16_t *)DTC_CURROW;
    for (uint32_t i = 0; i < DTC_ROWS; i++) {
        uint8_t *p = (uint8_t *)(DTC_BASE + i * DTC_STRIDE);
        if (p[0x06] == key && i != currow) {
            return (int32_t)(int8_t)p[0x08];
        }
    }
    return 0x08;
}
