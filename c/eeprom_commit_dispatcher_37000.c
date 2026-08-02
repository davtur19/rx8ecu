/*
 * eeprom_commit_dispatcher_37000  —  RX-8 PCM @ ROM 0x37000 (60E1D400.bin)
 *
 * Dispatches an EEPROM commit request to the low-level writer 0x38B5C
 * (SPI EEPROM scheduler).  If the write-queue busy flag 0xFFFFC2D2 is set
 * the request is skipped (returns 1).  Otherwise `code` selects the EEPROM
 * region written, as (index, length) for 0x38B5C(index, length, 1):
 *
 *   0x01 -> (0x0A, 2)   0x02 -> (0x02, 8)   0x03 -> (0x00, 2)
 *   0x04 -> (0x0C, 6)   0x05 -> (0x12, 2)   0x06 -> (0x0E, 2)
 *   0x07 -> (0x16, 4)   0x08 -> (0x14, 2)   0x09 -> (0x0C, 8)
 *   0x0A -> (0x1A, 4)   0x0B -> (0x02, 10)  0x0C -> (0x0C, 0x14)
 *   0x0D -> (0x1E, 2)   0x0E -> (0x0C, 2)   0x0F -> (0x0E, 2)
 *   0xFF -> (0x00, 0x20)
 *   other -> no call (r5 stays 1)
 *
 * If 0x38B5C returns 0 (still busy) the queue flag 0xFFFFC2D2 is set.
 * Verified at 0x37000..0x3711A.
 */
#include "eeprom_immo.h"

extern uint8_t eeprom_write_sched(uint16_t index, uint8_t len, uint8_t flag); /* 0x38B5C */

uint8_t eeprom_commit_dispatcher_37000(uint8_t code)
{
    uint8_t result = 1;

    if (E2_WQ_FLAG_D2 == 0) {          /* 0xFFFFC2D2 */
        uint16_t index = 0;
        uint8_t  len   = 0;
        int      called = 0;
        switch (code) {
        case 0x01: index = 0x0A; len = 0x02; called = 1; break;
        case 0x02: index = 0x02; len = 0x08; called = 1; break;
        case 0x0D: index = 0x1E; len = 0x02; called = 1; break;
        case 0x03: index = 0x00; len = 0x02; called = 1; break;
        case 0x04: index = 0x0C; len = 0x06; called = 1; break;
        case 0x05: index = 0x12; len = 0x02; called = 1; break;
        case 0x06: index = 0x0E; len = 0x02; called = 1; break;
        case 0x07: index = 0x16; len = 0x04; called = 1; break;
        case 0x08: index = 0x14; len = 0x02; called = 1; break;
        case 0x0C: index = 0x0C; len = 0x14; called = 1; break;
        case 0x09: index = 0x0C; len = 0x08; called = 1; break;
        case 0x0A: index = 0x1A; len = 0x04; called = 1; break;
        case 0x0B: index = 0x02; len = 0x0A; called = 1; break;
        case 0x0E: index = 0x0C; len = 0x02; called = 1; break;
        case 0x0F: index = 0x0E; len = 0x02; called = 1; break;
        case 0xFF: index = 0x00; len = 0x20; called = 1; break;
        default:
            break;                     /* 0x37078: no call, result stays 1 */
        }
        if (called) {                  /* 0x37106: jsr 0x38B5C */
            result = (uint8_t)eeprom_write_sched(index, len, 1);
            if (result == 0)
                E2_WQ_FLAG_D2 = 1;     /* 0x37114..0x37118 */
        }
    }
    return result;                     /* r5 = extu.b result */
}
