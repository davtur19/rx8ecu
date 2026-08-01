/*
 * getDataFromE2RAM  —  RX-8 PCM @ ROM 0x36C1C (60E1D400.bin)
 *
 * Populates the working-copy variables (0xFFFFC2D8..0xFFFFC2F2 and the
 * CAN shadow bytes 0xC242..0xC244) from the validated EEPROM shadow, one
 * getFromE2_E2ADDR_RAMADDR_LEN call per EEPROM region.  Called after the
 * boot load (loadDatafromE2intoRAM) to expose the EEPROM contents to the
 * running firmware.
 *
 * EEPROM index -> destination map (verified from the literal pool):
 *   0x00 -> 0xFFFFC2D8 (1B)     0x0F -> 0xFFFFC2E7 (1B)
 *   0x02 -> 0xFFFFC2DC (4B)     0x10 -> 0xC242      (1B)
 *   0x06 -> 0xFFFFC2E0 (4B)     0x16 -> 0xFFFFC2EA (2B)
 *   0x0A -> 0xFFFFC2E4 (1B)     0x18 -> 0xFFFFC2EC (2B)
 *   0x0C -> 0xFFFFC2E5 (1B)     0x12 -> 0xC244      (1B)
 *   0x0D -> 0xFFFFC2E6 (1B)     0x13 -> 0xFFFFC2E8 (1B)
 *   0x0E -> 0xC243      (1B)    0x14 -> 0xFFFFC2E9 (1B)
 *   0x1A -> 0xFFFFC2EE (1B)     0x1C -> 0xFFFFC2F0 (1B)
 *   0x1B -> 0xFFFFC2EF (1B)     0x1D -> 0xFFFFC2F1 (1B)
 *   0x1E -> 0xFFFFC2F2 (1B)
 */
#include "eeprom_immo.h"

void getDataFromE2RAM(void)
{
    getFromE2_E2ADDR_RAMADDR_LEN(0x00, (uint8_t *)&E2_WORK_INDEX0,  1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x02, (uint8_t *)&E2_WORK_INDEX2,  4);
    getFromE2_E2ADDR_RAMADDR_LEN(0x06, (uint8_t *)&E2_WORK_INDEX6,  4);
    getFromE2_E2ADDR_RAMADDR_LEN(0x0A, (uint8_t *)&E2_WORK_INDEX10, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x0C, (uint8_t *)&E2_WORK_INDEX12, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x0D, (uint8_t *)&E2_WORK_INDEX13, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x0E, (uint8_t *)&CAN_SHADOW_C243, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x0F, (uint8_t *)&E2_WORK_INDEX15, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x10, (uint8_t *)&CAN_SHADOW_C242, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x16, (uint8_t *)&E2_WORK_INDEX22, 2);
    getFromE2_E2ADDR_RAMADDR_LEN(0x18, (uint8_t *)&E2_WORK_INDEX24, 2);
    getFromE2_E2ADDR_RAMADDR_LEN(0x12, (uint8_t *)&CAN_SHADOW_C244, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x13, (uint8_t *)&E2_WORK_INDEX19, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x14, (uint8_t *)&E2_WORK_INDEX20, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x1A, (uint8_t *)&E2_WORK_INDEX26, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x1B, (uint8_t *)&E2_WORK_INDEX27, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x1C, (uint8_t *)&E2_WORK_INDEX28, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x1D, (uint8_t *)&E2_WORK_INDEX29, 1);
    getFromE2_E2ADDR_RAMADDR_LEN(0x1E, (uint8_t *)&E2_WORK_INDEX30, 1);
}
