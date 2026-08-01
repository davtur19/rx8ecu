/*
 * ImmoUpdateRelated  —  RX-8 PCM @ ROM 0x37120 (60E1D400.bin)
 *
 * EEPROM write-queue driver for the immobilizer pairing data.
 *
 *   - If 0xFFFFC2D5 (init-done) is set: return.
 *   - If 0xFFFFC2D6 (armed) is clear:
 *        * if E2_WORK_INDEX0 (0xFFFFC2D8) != 0x5A: store 0x5A there, queue
 *          E2 code 0x0C at 0xFFFFC2D1, call updateE2RAMBasedOnInput(0x0C),
 *          then set 0xFFFFC2D7 (busy) and 0xFFFFC2D6 (armed).
 *        * else: mark init done (0xFFFFC2D5 = 1).
 *   - Else (armed): call 0x37000(pending code).  If E2 write-done flag
 *     0xC2F8 == 1:
 *        * busy (0xFFFFC2D7 == 1): clear 0xFFFFC2D2, 0xFFFFC2D7, queue
 *          code 3 at 0xFFFFC2D1 and tail-call updateE2RAMBasedOnInput(3).
 *        * not busy: clear 0xFFFFC2D2 and 0xFFFFC2D1, set init done
 *          (0xFFFFC2D5 = 1), disarm (0xFFFFC2D6 = 0).
 */
#include "eeprom_immo.h"

void ImmoUpdateRelated(void)
{
    if (E2_WQ_INIT_DONE != 0)          /* 0xFFFFC2D5 */
        return;

    if (E2_WQ_ARMED == 0) {            /* 0xFFFFC2D6 */
        if (E2_WORK_INDEX0 != 0x5A) {  /* 0xFFFFC2D8 */
            E2_WORK_INDEX0 = 0x5A;
            E2_WQ_PENDING_CODE = 0x0C; /* 0xFFFFC2D1 */
            updateE2RAMBasedOnInput(0x0C);
            E2_WQ_BUSY = 1;            /* 0xFFFFC2D7 */
            E2_WQ_ARMED = 1;           /* 0xFFFFC2D6 */
        } else {
            E2_WQ_INIT_DONE = 1;       /* 0xFFFFC2D5 */
        }
        return;
    }

    /* armed: drive the queued write */
    {
        uint8_t was_busy = E2_WQ_BUSY; /* 0xFFFFC2D7 */
        sub_37000(E2_WQ_PENDING_CODE); /* 0x37000(*0xFFFFC2D1) */
        if (E2_WRITE_COMPLETE == 1) {  /* 0xC2F8 */
            E2_WQ_FLAG_D2 = 0;         /* 0xFFFFC2D2 */
            if (was_busy) {
                E2_WQ_BUSY = 0;
                E2_WQ_PENDING_CODE = 3;
                updateE2RAMBasedOnInput(3);  /* tail jump 0x36D0C */
            } else {
                E2_WQ_PENDING_CODE = 0;
                E2_WQ_INIT_DONE = 1;   /* 0xFFFFC2D5 */
                E2_WQ_ARMED = 0;       /* 0xFFFFC2D6 */
            }
        }
    }
}
