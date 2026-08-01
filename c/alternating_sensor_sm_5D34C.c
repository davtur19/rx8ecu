// alternating_sensor_sm_5D34C (0x5D34C) — sensor state machine, 3rd instance.
// Symbol-table name: diagMeteringPumpPositionControl (unconfirmed).
// RAW-value variant: out==0 stores the raw cmd byte in 0xFFFFD385,
// out in {5,7} returns the raw latch (no ==1 gating, unlike sm_08).
#include <stdint.h>

#define SM_BASE    0x60204UL
#define SM_MASK    (*(volatile uint8_t  *)(SM_BASE + 0x8))
#define SM_PTR     (*(volatile uint32_t *)(SM_BASE + 0xC))
#define ST_D355    (*(volatile uint8_t  *)0xFFFFD355UL)
#define MAGIC_D350 (*(volatile uint16_t *)0xFFFFD350UL)
#define INP_D3A8   (*(volatile uint8_t  *)0xFFFFD3A8UL)
#define CNT_D354   (*(volatile uint8_t  *)0xFFFFD354UL)
#define SRC_D352   (*(volatile uint16_t *)0xFFFFD352UL)
#define LATCH_D385 (*(volatile uint8_t  *)0xFFFFD385UL)

uint8_t alternating_sensor_sm_5D34C(uint8_t cmd /* r4 */)
{
    volatile uint8_t *ptr = (volatile uint8_t *)(uintptr_t)SM_PTR;  /* stored RAM pointer @0x60210 */
    uint8_t mask = SM_MASK;

    if (ST_D355 == 0) {
        uint8_t masked = INP_D3A8 & mask;
        if (MAGIC_D350 == 0x172D) {
            if (masked != 0) {
                *ptr = CNT_D354;
                if (CNT_D354 == 7)
                    LATCH_D385 = (SRC_D352 >> 8) & 0xFF;
                ST_D355 = 1;
            } else {
                *ptr = 0;
                ST_D355 = 2;
            }
        } else {
            if (masked == 0)
                *ptr = 0;
            ST_D355 = 0;
        }
    }

    uint8_t out = *ptr;
    if (out == 0) {
        LATCH_D385 = cmd;              /* raw, no ==1 gating */
        return cmd;
    }
    if (out == 5 || out == 7)
        return LATCH_D385;             /* raw latch */
    return cmd;
}
