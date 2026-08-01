/*
 * checkImmoStatus_371E4  —  RX-8 PCM @ ROM 0x371E4 (60E1D400.bin)
 *
 * Periodic sanity/reset of the EEPROM working copies and CAN shadow bytes
 * (called every loop while EEPROM[0x00] == 0x5A "armed").
 *
 * Prologue: if E2_WORK_INDEX0 (0xFFFFC2D8) != 0x5A, it is zeroed; if it is
 * still not 0x5A the "reset" branch runs (unarmed -> full re-init of the
 * working copies); otherwise the "armed" branch validates/clamps values:
 *
 *   armed:
 *     - E2_WORK_INDEX12 (0xFFFFC2E5): if (v & 0xFC) != 0 -> v = 0
 *     - CAN_SHADOW_C243 (0xC243):      if (v & 0x0F) != 0 -> v = 0,
 *                                        then if E2_WORK_INDEX10 == 1
 *                                        v |= 0x40
 *     - E2_WORK_INDEX13 (0xFFFFC2E6): if v > 5 -> v = 0
 *     - if (E2_WORK_INDEX12 & 0x02) == 0:
 *         if (*(u8*)0xC242 == 0x55) { *(u8*)0xC242 = 0x33;
 *                                     *(u16*)0xFFFFC2A4 = 0; }
 *     - E2_WORK_INDEX30 (0xFFFFC2F2): if v > 2 -> v = 2
 *                                     (clamp abnormal values)
 *
 *   reset (not armed):
 *     - 0xFFFFC2E5 = 0; 0xFFFFC2E6 = 0; 0xC243 = 0
 *     - if E2_WORK_INDEX10 == 1 -> 0xC243 |= 0x40
 *     - 0xC242 = 0x33
 *     - 0xC244 = 8; 0xFFFFC2E9 = 0; 0xFFFFC2E8 = 0;
 *       0xFFFFC2EE = 0; 0xFFFFC2EF = 0; 0xFFFFC2F0 = 0;
 *       0xFFFFC2F1 = 0; 0xFFFFC2F2 = 2
 *
 *   common:
 *     - 0xC244: clamp to [8, 0x3F]
 *     - if E2_WORK_INDEX20 (0xFFFFC2E9) > 0:
 *         0xFFFFC2A9 = 1; 0xFFFFC2E9 = 0xC8
 *
 * NOTE: the "movt r2 / add #-1 / neg / tst / bf" idiom at 0x37250-0x37258
 * decodes the MOVT Rn form with register in bits 11-8 (0x0n29); it tests
 * bit 1 of 0xFFFFC2E5 and runs the 0xC242==0x55 handshake only when the
 * bit is clear.
 */
#include "eeprom_immo.h"

void checkImmoStatus(void)
{
    /* prologue 0x371F0 */
    if (E2_WORK_INDEX0 != 0x5A)
        E2_WORK_INDEX0 = 0;

    if (E2_WORK_INDEX0 == 0x5A) {
        /* armed: validate working copies */
        if (E2_WORK_INDEX12 & 0xFC)              /* 0x37218 */
            E2_WORK_INDEX12 = 0;
        if (CAN_SHADOW_C243 & 0x0F) {            /* 0x37224 */
            CAN_SHADOW_C243 = 0;
            if (E2_WORK_INDEX10 == 1)
                CAN_SHADOW_C243 |= 0x40;
        }
        if (E2_WORK_INDEX13 > 5)                 /* 0x37244 */
            E2_WORK_INDEX13 = 0;
        if ((E2_WORK_INDEX12 & 0x02) == 0) {     /* 0x3724E MOVT R2 idiom */
            if (*(volatile uint8_t *)0x0000C242 == 0x55) {
                *(volatile uint8_t *)0x0000C242 = 0x33;
                *(volatile uint16_t *)0xFFFFC2A4 = 0;
            }
        }
        if (E2_WORK_INDEX30 > 2)                 /* 0x37276 */
            E2_WORK_INDEX30 = 2;
    } else {
        /* reset: full re-init of working copies */
        E2_WORK_INDEX12 = 0;
        E2_WORK_INDEX13 = 0;
        CAN_SHADOW_C243 = 0;
        if (E2_WORK_INDEX10 == 1)
            CAN_SHADOW_C243 |= 0x40;
        *(volatile uint8_t *)0x0000C242 = 0x33;
        CAN_SHADOW_C244 = 8;                     /* 0xC244 */
        E2_WORK_INDEX20 = 0;                     /* 0xFFFFC2E9 */
        E2_WORK_INDEX19 = 0;                     /* 0xFFFFC2E8 */
        E2_WORK_INDEX26 = 0;                     /* 0xFFFFC2EE */
        E2_WORK_INDEX27 = 0;                     /* 0xFFFFC2EF */
        E2_WORK_INDEX28 = 0;                     /* 0xFFFFC2F0 */
        E2_WORK_INDEX29 = 0;                     /* 0xFFFFC2F1 */
        E2_WORK_INDEX30 = 2;                     /* 0xFFFFC2F2 */
    }

    /* common: clamp 0xC244 to [8, 0x3F] */
    {
        uint8_t v = CAN_SHADOW_C244;
        if (v < 8 || v > 0x3F)
            CAN_SHADOW_C244 = 8;
    }

    /* common: 0xFFFFC2E9 > 0 -> 0xFFFFC2A9 = 1, 0xFFFFC2E9 = 0xC8 */
    if (E2_WORK_INDEX20 > 0) {
        *(volatile uint8_t *)0xFFFFC2A9 = 1;
        E2_WORK_INDEX20 = 0xC8;
    }
}
