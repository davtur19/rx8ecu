/*
 * ImmoGetCANData  —  RX-8 PCM @ ROM 0x36870 (60E1D400.bin)
 *
 * Consumes one CAN RX frame from the mailboxes 0xC529..0xC52F.  The entry
 * flag 0xC52F gates processing: when it is not 1 the state (0xFFFFC28E)
 * is forced to 5 and the function returns.  When it is 1, the mode byte
 * 0xC529 selects the action; 0xC52A..0xC52D carry the payload; the flag
 * 0xC52F is cleared on every exit.
 *
 * Verified dispatch (0x36882..0x369AE):
 *   0xC529 == 0x00 -> state = 0                     (idle)
 *   0xC529 == 0x06 -> state = 1; then look at 0xC52A:
 *                      0xC52A==0   && 0xC52B==0xFF -> 0xFFFFC291 = 1
 *                      0xC52A==1   && 0xC52B==0xFF -> 0xFFFFC291 = 3
 *                      0xC52A==0x7F                -> 0xFFFFC291 = 2
 *                      otherwise                   -> state = 6
 *   0xC529 == 0x08 -> state = 2; uint32 @0xFFFFC274 =
 *                      (0xC52A<<24)|(0xC52B<<16)|(0xC52C<<8)|0xC52D
 *   0xC529 == 0x90 -> if 0xC52A in {1,2,3,4}: state = 4; uint32 @0xFFFFC25C
 *                      = (0xC52A<<24)|(0xC52B<<16)|(0xC52C<<8)|0xC52D
 *                      else: state = 6
 *   0xC529 == 0xC9 -> state = 3
 *   other          -> state = 6
 *   0xC52F != 1    -> state = 5
 *
 * epilogue always: 0xC52F = 0.
 */
#include "eeprom_immo.h"

void ImmoGetCANData(void)
{
    uint8_t *state = (uint8_t *)0xFFFFC28E;

    if (CAN_RX_STATUS == 1) {
        uint8_t mode = CAN_RX_MODE;
        switch (mode) {
        case 0x00:
            *state = 0;
            break;
        case 0x06: {
            uint8_t a = CAN_RX_B1, b = CAN_RX_B2;
            *state = 1;
            if (a == 0x00 && b == 0xFF) {
                IMMO_SUBSTATE = 1;
            } else if (a == 0x01 && b == 0xFF) {
                IMMO_SUBSTATE = 3;
            } else if (a == 0x7F) {
                IMMO_SUBSTATE = 2;
            } else {
                *state = 6;
            }
            break;
        }
        case 0x08: {
            uint32_t v = ((uint32_t)CAN_RX_B1 << 24) |
                         ((uint32_t)CAN_RX_B2 << 16) |
                         ((uint32_t)CAN_RX_B3 << 8) |
                         (uint32_t)CAN_RX_B4;
            *state = 2;
            IMMO_RX_CHALLENGE = v;                 /* 0xFFFFC274 */
            break;
        }
        case 0x90: {
            uint8_t sel = CAN_RX_B1;
            if (sel >= 1 && sel <= 4) {
                uint32_t v = ((uint32_t)sel << 24) |
                             ((uint32_t)CAN_RX_B2 << 16) |
                             ((uint32_t)CAN_RX_B3 << 8) |
                             (uint32_t)CAN_RX_B4;
                *state = 4;
                IMMO_RX_KEY_VALUE = v;             /* 0xFFFFC25C */
            } else {
                *state = 6;
            }
            break;
        }
        case 0xC9:
            *state = 3;
            break;
        default:
            *state = 6;
            break;
        }
    } else {
        *state = 5;
    }
    CAN_RX_STATUS = 0;                             /* 0xC52F = 0 */
}
