/*
 * dtcRelated.c  —  RX-8 PCM DTC list builder/filter (0x062002)
 *
 * Scans the 21-entry DTC handler context table at 0xFFFF87D8 (16 bytes per
 * entry) and appends the 16-bit DTC code of every entry whose "type" byte
 * (entry offset +6) matches the requested type selector to a caller-supplied
 * word array.  An optional enable gate (r5) first checks the entry against
 * two ROM property tables indexed by DTC code:
 *
 *   tableA @ 0x0007E220  (DTC class/property byte)
 *   tableB @ 0x0007E2AC  (DTC enable byte)
 *
 *   enable = 0: no gate          enable = 1: tableA[code] must be 1
 *                                 enable = 2: tableB[code] must be 1
 *
 * The entry whose index equals the "current DTC index" register
 * (0xFFFF8928) is skipped, so the function never reports the DTC that is
 * currently being serviced by the diag handler.
 *
 * Type selector dispatch (on the entry type byte):
 *   0x00 -> type == 0
 *   0x60 -> 0x01 .. 0x3F
 *   0x80 -> bit 7 set
 *   0xC0 -> == 0xC0       0xC1 -> == 0xC1       0x50 -> == 0x50
 *   0xF0 -> (0x01..0x3F) OR bit 7 set
 *   0x70 -> 0x81 .. 0xBF
 *
 * Return value: number of matching entries.  Matching 16-bit DTC codes are
 * written CONSECUTIVELY to out[0], out[1], ... (packed, in scan order) --
 * the running count doubles as the output index (r12 = out + 2*count).
 *
 * SH-2E notes: r7 = count, r11 = loop index, r12 = out + 2*count,
 * r13 = DTC code word, r14 = type byte, r8/r9/r10 = tableA/B + masks.
 * Verified against ROM 60E1D400.bin (Track-A: emulator, see
 * c/tests/test_dtcRelated.py).
 */
#include <stdint.h>

#define DTC_CTX_TABLE     0xFFFF87D8u   /* 21 entries x 16 bytes            */
#define DTC_CUR_INDEX     0xFFFF8928u   /* word: DTC index being serviced   */
#define TABLE_A           0x0007E220u   /* ROM: DTC property byte table     */
#define TABLE_B           0x0007E2ACu   /* ROM: DTC enable byte table       */
#define DTC_ENTRY_COUNT   21u
#define DTC_ENTRY_STRIDE  16u

static uint8_t rom_byte(uint32_t a)
{
    return *(const volatile uint8_t *)a;
}

uint8_t dtcRelated(uint8_t type, uint8_t enable, uint16_t *out)
{
    uint16_t cur_idx = *(volatile uint16_t *)DTC_CUR_INDEX;
    uint8_t  count = 0;
    uint8_t  i;

    for (i = 0; i < DTC_ENTRY_COUNT; i++) {
        uint8_t  *entry;
        uint8_t   flag;                 /* type/status byte @ entry+6      */
        uint16_t  code;                 /* 16-bit DTC code @ entry+0       */
        uint8_t   ok = 0;

        if (i == cur_idx)               /* skip DTC being serviced         */
            continue;

        entry = (uint8_t *)DTC_CTX_TABLE + (uint32_t)i * DTC_ENTRY_STRIDE;
        flag  = entry[6];
        code  = *(uint16_t *)entry;

        /* enable gate against the ROM property tables */
        if (enable) {
            if (enable == 1)
                ok = (rom_byte(TABLE_A + code) == 0x01u);
            else if (enable == 2)
                ok = (rom_byte(TABLE_B + code) == 0x01u);
            if (!ok)
                continue;
        }

        /* type selector on the entry type byte */
        ok = 0;
        switch (type) {
        case 0x00: ok = (flag == 0x00u);                            break;
        case 0x60: ok = (flag >= 0x01u && flag <= 0x3Fu);           break;
        case 0x80: ok = ((flag & 0x80u) == 0x80u);                  break;
        case 0xC0: ok = (flag == 0xC0u);                            break;
        case 0xC1: ok = (flag == 0xC1u);                            break;
        case 0x50: ok = (flag == 0x50u);                            break;
        case 0xF0: ok = ((flag >= 0x01u && flag <= 0x3Fu) ||
                         ((flag & 0x80u) == 0x80u));                break;
        case 0x70: ok = (flag >= 0x81u && flag <= 0xBFu);           break;
        default:   ok = 0;                                          break;
        }
        if (ok) {
            out[count] = code;          /* packed: out[0..count-1] in order */
            count++;
        }
    }
    return count;
}
