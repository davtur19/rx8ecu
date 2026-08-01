/* req_queue_69602.c
 *
 * ROM: 60E1D400  |  Region: 0x69602..0x69624 + 0x69694..0x6969E
 *
 * Two packed request-queue leaves over the byte-flag array at 0xFFFFDE38
 * and the parallel 32-bit value array at 0xFFFFDE40 (indexed by byte r4):
 *
 *   0x69602  store(r4, r5):
 *            b = r4 & 0xFF
 *            long@(0xFFFFDE40 + b*4) = (uint32)(r5 * 0x0FA0) + long@0xFFFFF430
 *            byte@(0xFFFFDE38 + b)   = 1
 *
 *   0x69694  clear(r4):
 *            byte@(0xFFFFDE38 + (r4 & 0xFF)) = 0
 *
 * Both are invoked via function-pointer tables (e.g. pool at 0x68CF4, and
 * 0x69694 from 0x68A74/0x68BA0/0x68E38/0x68F6C/0x690BC/0x69310/0x69458/0x695A8).
 * Note the 0x69624..0x69692 dispatcher between them (7-entry loop calling
 * 0x3920, the 0x69918 dispatch table, and setSR 0x3934) is NOT lifted — it is
 * a caller of three external subsystems.
 *
 * Verified against ROM emulator: c/tests/test_req_queue_69602.py
 * Host C companion:             c/tests/test_req_queue_69602.c
 */
#include <stdint.h>

#define REQ_FLAGS 0xFFFFDE38u
#define REQ_VALUES 0xFFFFDE40u
#define REQ_BASE 0xFFFFF430u   /* 32-bit base value added to each stored entry */

/* 0x69602 — store one entry + set its flag */
void req_queue_store_69602(uint32_t r4, uint32_t r5)
{
    uint32_t b = r4 & 0xFF;
    uint32_t v = ((uint32_t)r5 * 0x0FA0u) + *(volatile uint32_t *)REQ_BASE;
    *(volatile uint32_t *)(REQ_VALUES + b * 4) = v;
    *(volatile uint8_t *)(REQ_FLAGS + b) = 1;
}

/* 0x69694 — clear one entry's flag */
void req_queue_clear_69694(uint32_t r4)
{
    *(volatile uint8_t *)(REQ_FLAGS + (r4 & 0xFF)) = 0;
}
