/*
 * ImmoGetSeed_3664E  —  RX-8 PCM @ ROM 0x3664E (60E1D400.bin)
 *
 * Recomputes the immobilizer seed from the current rolling code and the two
 * EEPROM key words, storing the result into IMMO_SEED_OUT (0xFFFFC270).
 *
 *   IMMO_SEED_OUT = calculateImmoSeed(
 *                       *(u32*)0xFFFFC2DC,   -- EEPROM[0x02..05] words
 *                       *(u32*)0xFFFFC2E0,   -- EEPROM[0x06..09] words
 *                       IMMO_KEYGEN_ADC);    -- 0xFFFFC278 rolling code
 *
 * The incoming r4 (caller's setImmoLight result) is unused -- it is
 * overwritten by the delay slot before the call.
 */
#include "eeprom_immo.h"

void ImmoGetSeed_3664E(void)
{
    IMMO_SEED_OUT = calculateImmoSeed(
        *(volatile uint32_t *)0xFFFFC2DC,
        *(volatile uint32_t *)0xFFFFC2E0,
        IMMO_KEYGEN_ADC);
}
