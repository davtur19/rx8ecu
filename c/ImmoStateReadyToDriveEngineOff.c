/*
 * ImmoStateReadyToDriveEngineOff  —  RX-8 PCM @ ROM 0x364D8 (60E1D400.bin)
 *
 * Idle-state handler ("ready to drive", engine off).
 *
 * If the immobilizer state (0xFFFFC28E) is 1 ("key validated"): waits until
 * the rolling-code word (0xFFFFC278) CHANGES — re-running the key generator
 * (Immo_Keygen_related_ADC, 0x36AFC) until it does — then arms the 500-tick
 * timer (0xFFFFC27C = 0x01F4) and falls into the main state machine
 * (ImmoStateMachine_360E8, 0x360E8).
 *
 * Otherwise: forces state = 5, decrements the countdown 0xFFFFC282 (while
 * it is nonzero — cmp/pl after extu.w, so true for ANY value != 0), and
 * when it reaches 0: ImmoBadStateSet(), result code 5, sends CAN message 0xC8 via
 * the TX dispatcher (0x369B8), and resets the countdown to 500.
 *
 * Original listing (verified) — see 0x364DE..0x36542.
 * Note the loop shape: snapshot = *0xFFFFC278; do { keygen(); }
 * while (*0xFFFFC278 == snapshot).
 */
#include "eeprom_immo.h"

void ImmoStateReadyToDriveEngineOff(void)
{
    uint8_t *state = (uint8_t *)0xFFFFC28E;

    if (*state == 1) {
        uint32_t *rolling = (uint32_t *)0xFFFFC278;
        uint32_t snapshot = *rolling;

        do {
            Immo_Keygen_related_ADC();       /* 0x36AFC */
        } while (*rolling == snapshot);

        *(volatile uint16_t *)0xFFFFC27C = 0x01F4;   /* 500-tick timer */
        ImmoStateMachine_360E8();                    /* tail jump 0x360E8 */
    } else {
        *state = 5;
        {
            uint16_t cnt = IMMO_TIMER;
            if (cnt != 0)                /* 0x360B2-0x360B6: extu.w + cmp/pl */
                IMMO_TIMER = (uint16_t)(cnt - 1);  /* r2 + 0xFFFF == r2 - 1 */
        }
        if (IMMO_TIMER == 0) {
            ImmoBadStateSet();
            IMMO_STATE_CODE = 5;
            setImmoCANTXData_369B8(0xC8);
            IMMO_TIMER = 0x01F4;
        }
    }
}
