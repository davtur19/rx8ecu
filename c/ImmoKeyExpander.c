/*
 * ImmoKeyExpander_365D6  —  RX-8 PCM @ ROM 0x365D6 (60E1D400.bin)
 *
 * Derives the four expected key values from the current rolling code
 * (0xFFFFC278) and the two EEPROM key words (0xFFFFC2E0 / 0xFFFFC2DC):
 *
 *   slot0 = seed_mixer(w2E0,      key)
 *   slot1 = seed_mixer(w2E0>>16,  key>>8)
 *   slot2 = seed_mixer(w2DC,      key>>16)
 *   slot3 = seed_mixer(w2DC>>16,  key>>24)
 *
 * and stores the four expected values with the slot number prefix:
 *
 *   0xFFFFC260 = slot0 | 0x01000000
 *   0xFFFFC264 = slot1 | 0x02000000
 *   0xFFFFC268 = slot2 | 0x03000000
 *   0xFFFFC26C = slot3 | 0x04000000
 *
 * Called from ImmoWaitForKey_35F92 (first contact / unpaired) to generate
 * the expected key set before sending challenge CAN id 0x09.
 */
#include "eeprom_immo.h"

void ImmoKeyExpander_365D6(void)
{
    uint32_t key  = IMMO_KEYGEN_ADC;                    /* 0xFFFFC278 */
    uint32_t w2E0 = *(volatile uint32_t *)0xFFFFC2E0;
    uint32_t w2DC = *(volatile uint32_t *)0xFFFFC2DC;

    IMMO_KEY_SLOT0 = seed_mixer(w2E0,      key);
    IMMO_KEY_SLOT1 = seed_mixer(w2E0 >> 16, key >> 8);
    IMMO_KEY_SLOT2 = seed_mixer(w2DC,      key >> 16);
    IMMO_KEY_SLOT3 = seed_mixer(w2DC >> 16, key >> 24);

    IMMO_EXPECTED1 = IMMO_KEY_SLOT0 | 0x01000000;       /* 0xFFFFC260 */
    IMMO_EXPECTED2 = IMMO_KEY_SLOT1 | 0x02000000;       /* 0xFFFFC264 */
    IMMO_EXPECTED3 = IMMO_KEY_SLOT2 | 0x03000000;       /* 0xFFFFC268 */
    IMMO_EXPECTED4 = IMMO_KEY_SLOT3 | 0x04000000;       /* 0xFFFFC26C */
}
