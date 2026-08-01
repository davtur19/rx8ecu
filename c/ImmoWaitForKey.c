/*
 * ImmoWaitForKey_35F92  —  RX-8 PCM @ ROM 0x35F92 (60E1D400.bin)
 *
 * "Waiting for key" state handler (state == 3: challenge sent; state == 4:
 * key received, verifying against the expected values).
 *
 * state == 3:
 *   - E2[0x0A] (0xFFFFC2E4) == 1 (paired): request a fresh challenge from
 *     slot 0xFF: 0xFFFFC290 = 0xFF, send CAN id 0x09, result code 0.
 *   - else (first contact): ImmoKeyExpander_365D6() derives the four
 *     expected key values, 0xFFFFC290 = 1, send CAN id 0x09, and arm the
 *     keygen countdown 0xFFFFC27E = 0x01F4.
 *
 * state == 4: compares the received key (0xFFFFC25C) against the expected
 *   slot value (0xFFFFC260/264/268/26C for slot 1..4):
 *   - match on slot 1/2/3: advance 0xFFFFC290 (2/3/4), send CAN id 0x09
 *     (next challenge).
 *   - match on slot 4: 0xFFFFC27C = 0x01F4, send CAN id 0xC6 (done),
 *     result code 0.
 *   - no match: send CAN id 0x09 again (stay on the same slot).
 *
 * any other state: state = 5, countdown 0xFFFFC27E (1..0x7FFF only) --
 *   when it hits 0: ImmoBadStateSet(), 0xFFFFC294 = 0, send CAN id 0x01,
 *   0xFFFFC29A = 1.
 */
#include "eeprom_immo.h"

void ImmoWaitForKey_35F92(void)
{
    uint8_t *state = (uint8_t *)0xFFFFC28E;

    if (*state == 3) {
        if (E2_WORK_INDEX10 == 1) {            /* 0xFFFFC2E4 (paired) */
            IMMO_WAIT_STATE = 0xFF;            /* 0x35FCC */
            message_queue_state_dispatcher_369B8(0x09);
            IMMO_STATE_CODE = 0;
        } else {
            ImmoKeyExpander_365D6();           /* 0x365D6 */
            IMMO_WAIT_STATE = 1;               /* 0x35FBE */
            message_queue_state_dispatcher_369B8(0x09);
            *(volatile uint16_t *)0xFFFFC27E = 0x01F4;   /* 0x35FC8 */
        }
    } else if (*state == 4) {
        uint8_t  sel = IMMO_WAIT_STATE;        /* 0xFFFFC290 */
        uint32_t key = IMMO_RX_KEY_VALUE;      /* 0xFFFFC25C */
        switch (sel) {
        case 1:
            if (IMMO_EXPECTED1 == key)         /* 0xFFFFC260 */
                IMMO_WAIT_STATE = 2;
            message_queue_state_dispatcher_369B8(0x09);
            break;
        case 2:
            if (IMMO_EXPECTED2 == key)         /* 0xFFFFC264 */
                IMMO_WAIT_STATE = 3;
            message_queue_state_dispatcher_369B8(0x09);
            break;
        case 3:
            if (IMMO_EXPECTED3 == key)         /* 0xFFFFC268 */
                IMMO_WAIT_STATE = 4;
            message_queue_state_dispatcher_369B8(0x09);
            break;
        case 4:
            if (IMMO_EXPECTED4 == key) {       /* 0xFFFFC26C */
                IMMO_TIMER_27C = 0x01F4;       /* 0xFFFFC27C */
                message_queue_state_dispatcher_369B8(0xC6);
                IMMO_STATE_CODE = 0;
            } else {
                message_queue_state_dispatcher_369B8(0x09);
            }
            break;
        default:
            break;                             /* 0x36082: no message */
        }
    } else {
        *state = 5;
        {
            uint16_t cnt = *(volatile uint16_t *)0xFFFFC27E;
            if ((int16_t)cnt > 0)              /* 0x360B4 cmp/pl */
                *(volatile uint16_t *)0xFFFFC27E = (uint16_t)(cnt - 1);
        }
        if (*(volatile uint16_t *)0xFFFFC27E == 0) {
            ImmoBadStateSet();                 /* 0x365B8 */
            IMMO_RESP_BYTE = 0;                /* 0xFFFFC294 */
            message_queue_state_dispatcher_369B8(0x01);
            IMMO_GOODSTATE_FLAG = 1;           /* 0xFFFFC29A */
        }
    }
}
