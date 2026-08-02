/*
 * ImmoStateMachine_360E8  —  RX-8 PCM @ ROM 0x360E8 (60E1D400.bin)
 *
 * Immobilizer state-machine dispatcher (state byte 0xFFFFC28E).
 *
 * state == 1 (challenge phase):
 *   substate (0xFFFFC291) dispatch:
 *     - 1: ImmoBadStateSet(), 0xFFFFC294 = 0, send CAN id 0x01,
 *          0xFFFFC29A = 1 (bad-key flash).
 *     - 3: 0xFFFFC28D = 0 (result code 0).
 *     - 2: if E2_WORK_INDEX30 (0xFFFFC2F2) is 1 or 2: decrement it,
 *          0xFFFFC29F = 1 (seed active), setImmoLight(1),
 *          CAN_TX_DATA (0xC240) = 1, 0xFFFFC298 = 0; else setImmoLight(0),
 *          CAN_TX_DATA = 0.
 *          Then IMMO_SEED_TIMER (0xFFFFC286) = 0x02EE, ImmoGetSeed_3664E(),
 *          send CAN id 0x07 (keygen out), 0xFFFFC28D = 2.
 *
 * state == 3: tail-jump ImmoWaitForKey_35F92 (key verification).
 * any other state: 0xFFFFC28E = 5.
 */
#include "eeprom_immo.h"

void ImmoStateMachine_360E8(void)
{
    uint8_t state = IMMO_STATE_BYTE;             /* 0xFFFFC28E */

    if (state == 1) {
        uint8_t sub = IMMO_SUBSTATE;             /* 0xFFFFC291 */
        if (sub == 1) {
            ImmoBadStateSet();                   /* 0x365B8 */
            IMMO_RESP_BYTE = 0;                  /* 0xFFFFC294 */
            setImmoCANTXData_369B8(0x01);
            IMMO_GOODSTATE_FLAG = 1;             /* 0xFFFFC29A */
        } else if (sub == 3) {
            IMMO_STATE_CODE = 0;                 /* 0xFFFFC28D */
        } else if (sub == 2) {
            uint8_t v = E2_WORK_INDEX30;         /* 0xFFFFC2F2 */
            if (v > 0 && v <= 2) {               /* 0x3615C cmp/pl, 0x36164 cmp/gt */
                E2_WORK_INDEX30 = (uint8_t)(v - 1);
                IMMO_SEED_ACTIVE = 1;            /* 0xFFFFC29F */
                setImmoLight(1);                 /* 0x263C8 */
                CAN_TX_DATA = 1;                 /* 0xC240 */
                IMMO_GOODSTATE_CTR = 0;          /* 0xFFFFC298 */
            } else {
                setImmoLight(0);
                CAN_TX_DATA = 0;
            }
            IMMO_SEED_TIMER = 0x02EE;            /* 0xFFFFC286 */
            ImmoGetSeed_3664E();                 /* 0x3664E */
            setImmoCANTXData_369B8(0x07);
            IMMO_STATE_CODE = 2;                 /* 0xFFFFC28D */
        }
    } else if (state == 3) {
        ImmoWaitForKey_35F92();                  /* tail call 0x35F92 */
    } else {
        IMMO_STATE_BYTE = 5;                     /* 0x361B8 */
    }
}
