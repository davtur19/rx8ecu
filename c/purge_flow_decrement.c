/* purge_flow_decrement.c
 *
 * ROM: 60E1D400  |  Address: 0xF5B4  |  Size: 40 bytes  |  VERIFIED vs ROM emulator
 *
 * EVAP purge flow countdown.  Called periodically while purge is enabled:
 *
 *   if (RAM[0xFFFFA4B2] == 1)          decrement-enable latch already set
 *       if (RAM[0xFFFFA4B0] > 0)       counter not exhausted
 *           RAM[0xFFFFA4B0]--          count down one tick
 *   else
 *       RAM[0xFFFFA4B2] = 1            first call: arm the countdown
 *
 * So the first invocation only arms the decrement (B2=1), the counter itself
 * is decremented from then on until it reaches 0.  RAM[0xFFFFA4B2] is the
 * "armed" flag; RAM[0xFFFFA4B0] is the purge flow countdown value.
 *
 * Note: cmp/pl (signed > 0) is used on the extu.b-extended counter, so any
 * nonzero byte value (1..255) counts as "> 0".
 *
 * Verified: 3000 random pre-states vs the ROM emulator, 0 mismatches.
 */

#include <stdint.h>

#define RAM_PURGE_FLOW   (*(volatile uint8_t *)0xFFFFA4B0)
#define RAM_PURGE_DEC_EN (*(volatile uint8_t *)0xFFFFA4B2)

void purge_flow_decrement(void)
{
    if (RAM_PURGE_DEC_EN == 1) {
        if (RAM_PURGE_FLOW > 0)
            RAM_PURGE_FLOW--;
    } else {
        RAM_PURGE_DEC_EN = 1;
    }
}
