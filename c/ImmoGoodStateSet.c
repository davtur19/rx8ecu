/*
 * ImmoGoodStateSet  —  RX-8 PCM @ ROM 0x36544 (60E1D400.bin)
 *
 * Marks the immobilizer as "good": turns the lamp OFF-progress (setImmoLight(1)),
 * raises the CAN TX flag (0xC240 = 1), records the good state in the EEPROM
 * working copy E2[0x1E] (0xFFFFC2F2 = 2) and primes the seed machine
 * (0xFFFFC29F = 1) with the good-state timeouts (0xFFFFC282 = 0x3A98,
 * 0xFFFFC284 = 0xFA) and result codes (0xFFFFC28D = 3, 0xFFFFC29A = 0,
 * 0xFFFFC28C = 0).
 *
 * Original listing (verified):
 *   0x36546  jsr 0x263C8 (delay: r4 = 1)   ; setImmoLight(1)
 *   0x36556  0xC240 = 1
 *   0x36558  0xFFFFC2F2 = 2
 *   0x3655E  0xFFFFC29F = 1
 *   0x36562  0xFFFFC282 = 0x3A98
 *   0x3656A  0xFFFFC284 = 0xFA
 *   0x3656E  0xFFFFC28C = 0
 *   0x36572  0xFFFFC28D = 3
 *   0x3657A  0xFFFFC29A = 0 (delay of rts)
 */
#include "eeprom_immo.h"

void ImmoGoodStateSet(void)
{
    setImmoLight(1);
    CAN_TX_DATA        = 1;
    E2_WORK_INDEX30    = 2;
    IMMO_SEED_ACTIVE   = 1;
    IMMO_TIMER         = 0x3A98;
    IMMO_TIMEOUT_CTR   = 0xFA;
    *(volatile uint8_t *)0xFFFFC28C = 0;
    IMMO_STATE_CODE    = 3;
    IMMO_GOODSTATE_FLAG = 0;
}
