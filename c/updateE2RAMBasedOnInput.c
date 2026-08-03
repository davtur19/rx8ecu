/*
 * updateE2RAMBasedOnInput  —  RX-8 PCM @ ROM 0x36D0C (60E1D400.bin)
 *
 * Dispatches EEPROM shadow updates based on an 8-bit input code.  Each code
 * maps to one or more writeToE2RAMArea(index, src, len) calls that persist
 * the current working-copy values into the E2 shadow (value + complement).
 *
 * The code map below is VERIFIED from the disassembly (branch targets and
 * the literal pool).  Codes with no case fall through and do nothing.
 *
 *   0x01 -> E2[0x0A] = work_0A (1B)
 *   0x02 -> E2[0x02] = pairing (8B)
 *   0x0B -> E2[0x02] = pairing (8B)  +  E2[0x0A] = work_0A (1B)
 *          (verified 0x36ED4 jsr write(0x02,..,8) then FALL-THROUGH into
 *           0x36ED8 write(0x0A,..,1); unlike 0x02 which bra-skip the second
 *           write.  Corrected from the original single-write listing.)
 *   0x03 -> E2[0x00] = work_00 (1B)
 *   0x04 -> E2[0x0C] = work_0C, E2[0x0E] = C243, E2[0x10] = C242
 *   0x05 -> E2[0x12] = C244,  E2[0x13] = work_13
 *   0x06 -> E2[0x0E] = C243
 *   0x07 -> E2[0x16] = work_16 (2B), E2[0x18] = work_18 (2B)
 *   0x08 -> E2[0x14] = work_14
 *   0x09 -> E2[0x0C] = work_0C, E2[0x0E] = C243, E2[0x10] = C242,
 *           E2[0x12] = C244,  E2[0x13] = work_13
 *   0x0A -> E2[0x1A..0x1D] = work (4 x 1B)
 *   0x0C -> E2[0x0C..0x13] + E2[0x14] + E2[0x1A..0x1E] (13 writes)
 *   0x0D -> E2[0x1E] = work_1E
 *   0x0E -> E2[0x0D] = work_0D
 *   0x0F -> E2[0x0F] = work_0F
 *   0xFF -> full save (18 writes, E2[0x00..0x1E])
 *
 * Original listing structure (verified):
 *   0x36D0E  extu.b r4,r0 ; r14 = 0x39124 (writeToE2RAMArea)
 *   0x36D1A  r12 = 0xFFFFC2E5 ; r13 = 0xC243
 *   0x36D12  cmp/eq #0x01 ...  (dispatch chain, bt/s to each case)
 *   each case: loads r5 = src, r6 = len, r4 = index (delay slots), then
 *   jsr @r14 (writeToE2RAMArea) and either the next write or the epilogue.
 *   0x36FB6  jsr @r14  (final call of the case)
 *   0x36FBA  lds.l @r15+,pr ; rts
 */
#include "eeprom_immo.h"

void updateE2RAMBasedOnInput(uint8_t code)
{
    switch (code) {
    case 0x01:
        writeToE2RAMArea(0x0A, (const uint8_t *)&E2_WORK_INDEX10, 1);
        break;
    case 0x02:
        writeToE2RAMArea(0x02, (const uint8_t *)&E2_WORK_INDEX2, 8);
        break;
    case 0x0B:
        writeToE2RAMArea(0x02, (const uint8_t *)&E2_WORK_INDEX2, 8);
        writeToE2RAMArea(0x0A, (const uint8_t *)&E2_WORK_INDEX10, 1);
        break;
    case 0x03:
        writeToE2RAMArea(0x00, (const uint8_t *)&E2_WORK_INDEX0, 1);
        break;
    case 0x04:
        writeToE2RAMArea(0x0C, (const uint8_t *)&E2_WORK_INDEX12, 1);
        writeToE2RAMArea(0x0E, (const uint8_t *)&CAN_SHADOW_C243, 1);
        writeToE2RAMArea(0x10, (const uint8_t *)&CAN_SHADOW_C242, 1);
        break;
    case 0x05:
        writeToE2RAMArea(0x12, (const uint8_t *)&CAN_SHADOW_C244, 1);
        writeToE2RAMArea(0x13, (const uint8_t *)&E2_WORK_INDEX19, 1);
        break;
    case 0x06:
        writeToE2RAMArea(0x0E, (const uint8_t *)&CAN_SHADOW_C243, 1);
        break;
    case 0x07:
        writeToE2RAMArea(0x16, (const uint8_t *)&E2_WORK_INDEX22, 2);
        writeToE2RAMArea(0x18, (const uint8_t *)&E2_WORK_INDEX24, 2);
        break;
    case 0x08:
        writeToE2RAMArea(0x14, (const uint8_t *)&E2_WORK_INDEX20, 1);
        break;
    case 0x09:
        writeToE2RAMArea(0x0C, (const uint8_t *)&E2_WORK_INDEX12, 1);
        writeToE2RAMArea(0x0E, (const uint8_t *)&CAN_SHADOW_C243, 1);
        writeToE2RAMArea(0x10, (const uint8_t *)&CAN_SHADOW_C242, 1);
        writeToE2RAMArea(0x12, (const uint8_t *)&CAN_SHADOW_C244, 1);
        writeToE2RAMArea(0x13, (const uint8_t *)&E2_WORK_INDEX19, 1);
        break;
    case 0x0A:
        writeToE2RAMArea(0x1A, (const uint8_t *)&E2_WORK_INDEX26, 1);
        writeToE2RAMArea(0x1B, (const uint8_t *)&E2_WORK_INDEX27, 1);
        writeToE2RAMArea(0x1C, (const uint8_t *)&E2_WORK_INDEX28, 1);
        writeToE2RAMArea(0x1D, (const uint8_t *)&E2_WORK_INDEX29, 1);
        break;
    case 0x0C:
        writeToE2RAMArea(0x0C, (const uint8_t *)&E2_WORK_INDEX12, 1);
        writeToE2RAMArea(0x0D, (const uint8_t *)&E2_WORK_INDEX13, 1);
        writeToE2RAMArea(0x0E, (const uint8_t *)&CAN_SHADOW_C243, 1);
        writeToE2RAMArea(0x0F, (const uint8_t *)&E2_WORK_INDEX15, 1);
        writeToE2RAMArea(0x10, (const uint8_t *)&CAN_SHADOW_C242, 1);
        writeToE2RAMArea(0x14, (const uint8_t *)&E2_WORK_INDEX20, 1);
        writeToE2RAMArea(0x12, (const uint8_t *)&CAN_SHADOW_C244, 1);
        writeToE2RAMArea(0x13, (const uint8_t *)&E2_WORK_INDEX19, 1);
        writeToE2RAMArea(0x1A, (const uint8_t *)&E2_WORK_INDEX26, 1);
        writeToE2RAMArea(0x1B, (const uint8_t *)&E2_WORK_INDEX27, 1);
        writeToE2RAMArea(0x1C, (const uint8_t *)&E2_WORK_INDEX28, 1);
        writeToE2RAMArea(0x1D, (const uint8_t *)&E2_WORK_INDEX29, 1);
        writeToE2RAMArea(0x1E, (const uint8_t *)&E2_WORK_INDEX30, 1);
        break;
    case 0x0D:
        writeToE2RAMArea(0x1E, (const uint8_t *)&E2_WORK_INDEX30, 1);
        break;
    case 0x0E:
        writeToE2RAMArea(0x0D, (const uint8_t *)&E2_WORK_INDEX13, 1);
        break;
    case 0x0F:
        writeToE2RAMArea(0x0F, (const uint8_t *)&E2_WORK_INDEX15, 1);
        break;
    case 0xFF:
        writeToE2RAMArea(0x00, (const uint8_t *)&E2_WORK_INDEX0,  1);
        writeToE2RAMArea(0x02, (const uint8_t *)&E2_WORK_INDEX2,  8);
        writeToE2RAMArea(0x0A, (const uint8_t *)&E2_WORK_INDEX10, 1);
        writeToE2RAMArea(0x0C, (const uint8_t *)&E2_WORK_INDEX12, 1);
        writeToE2RAMArea(0x0D, (const uint8_t *)&E2_WORK_INDEX13, 1);
        writeToE2RAMArea(0x0E, (const uint8_t *)&CAN_SHADOW_C243, 1);
        writeToE2RAMArea(0x0F, (const uint8_t *)&E2_WORK_INDEX15, 1);
        writeToE2RAMArea(0x10, (const uint8_t *)&CAN_SHADOW_C242, 1);
        writeToE2RAMArea(0x12, (const uint8_t *)&CAN_SHADOW_C244, 1);
        writeToE2RAMArea(0x13, (const uint8_t *)&E2_WORK_INDEX19, 1);
        writeToE2RAMArea(0x16, (const uint8_t *)&E2_WORK_INDEX22, 2);
        writeToE2RAMArea(0x18, (const uint8_t *)&E2_WORK_INDEX24, 2);
        writeToE2RAMArea(0x14, (const uint8_t *)&E2_WORK_INDEX20, 1);
        writeToE2RAMArea(0x1A, (const uint8_t *)&E2_WORK_INDEX26, 1);
        writeToE2RAMArea(0x1B, (const uint8_t *)&E2_WORK_INDEX27, 1);
        writeToE2RAMArea(0x1C, (const uint8_t *)&E2_WORK_INDEX28, 1);
        writeToE2RAMArea(0x1D, (const uint8_t *)&E2_WORK_INDEX29, 1);
        writeToE2RAMArea(0x1E, (const uint8_t *)&E2_WORK_INDEX30, 1);
        break;
    default:
        break;  /* unhandled code: no update */
    }
}
