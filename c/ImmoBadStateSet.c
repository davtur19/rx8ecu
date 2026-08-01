/*
 * ImmoBadStateSet  —  RX-8 PCM @ ROM 0x365B8 (60E1D400.bin)
 *
 * Marks the immobilizer as "bad": turns the lamp off (setImmoLight(0)),
 * clears the CAN TX flag (0xC240 = 0), sets the bad-state timeout
 * (0xFFFFC284 = 0x1F4 = 500) and the result code (0xFFFFC28D = 4).
 *
 * Original listing (verified):
 *   0x365BC  jsr 0x263C8 (delay: r4 = 0)   ; setImmoLight(0)
 *   0x365C6  0xC240 = 0
 *   0x365CC  0xFFFFC284 = 0x01F4
 *   0x365D4  0xFFFFC28D = 4 (delay of rts)
 */
#include "eeprom_immo.h"

void ImmoBadStateSet(void)
{
    setImmoLight(0);
    CAN_TX_DATA      = 0;
    IMMO_TIMEOUT_CTR = 0x01F4;
    IMMO_STATE_CODE  = 4;
}
