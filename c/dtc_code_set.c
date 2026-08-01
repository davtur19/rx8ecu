/*
 * dtc_code_set.c  —  RX-8 PCM DTC code storage helpers (0x046780 / 0x0467AA)
 *
 * These two functions manage the checksum-protected DTC flag words in the
 * backup-RAM fault area:
 *
 *   dtc_code_set  (0x046780) — "mark a DTC as present"
 *       If the DTC-present flag byte at 0xFFFF8788 reads back 1 (via the
 *       checksum-validated read readValue_8bit_ADDRESS_VAL), both DTC
 *       state words at 0xFFFF875C and 0xFFFF875E are written with the
 *       value 0 (checksum-encoded by updateMemoryAtAddress_8bit).
 *
 *   dtc_code_clear (0x0467AA) — "clear a DTC"
 *       Unconditionally writes 0 to the same two state words.
 *
 * The RAM "checksum" convention used here: every byte is stored together
 * with its bitwise complement in the adjacent byte (16-bit pair).  The
 * reader validates byte[n] == ~byte[n+1] before trusting it; writers use
 * updateMemoryAtAddress_8bit which stores val and ~val as a word.
 *
 * RAM layout (backup RAM / fault area):
 *   0xFFFF875C, 0xFFFF875E  DTC state words (written to 0 on set/clear)
 *   0xFFFF8788              DTC-present / enable flag
 *
 * Verified against ROM 60E1D400.bin.
 */
#include <stdint.h>

#define DTC_STATE_WORD_0   0xFFFF875Cu
#define DTC_STATE_WORD_1   0xFFFF875Eu
#define DTC_PRESENT_FLAG   0xFFFF8788u

/* called helpers (ROM addresses) */
extern uint8_t readValue_8bit_ADDRESS_VAL(uint16_t addr, uint8_t def);   /* 0x3ED3C */
extern void    updateMemoryAtAddress_8bit_ADDR_VAL(uint16_t addr, uint8_t val); /* 0x3EE58 */

/* 0x046780  mark a DTC as present (only when the present flag is set) */
void dtc_code_set(void)
{
    if (readValue_8bit_ADDRESS_VAL(DTC_PRESENT_FLAG, 0x01u) == 0x01u) {
        updateMemoryAtAddress_8bit_ADDR_VAL(DTC_STATE_WORD_0, 0x00u);
        updateMemoryAtAddress_8bit_ADDR_VAL(DTC_STATE_WORD_1, 0x00u);
    }
}

/* 0x0467AA  clear a DTC (unconditional) */
void dtc_code_clear(void)
{
    updateMemoryAtAddress_8bit_ADDR_VAL(DTC_STATE_WORD_0, 0x00u);
    updateMemoryAtAddress_8bit_ADDR_VAL(DTC_STATE_WORD_1, 0x00u);
}
