/* purge_flow_counter_init.c
 *
 * ROM: 60E1D400  |  Address: 0xF534  |  Size: 16 bytes  |  VERIFIED vs ROM emulator
 *
 * EVAP purge-flow counter initialization.  Resets the three-byte purge flow
 * state cell to zero at startup / purge disable.
 *
 * RAM layout (values written to the firmware's redundant 1+1 byte cells):
 *   RAM[0xFFFFA4B0] = purge flow countdown counter (u8)  (16-bit alias 0xA4B0)
 *   RAM[0xFFFFA4B1] = purge flow state / target (u8)
 *   RAM[0xFFFFA4B2] = purge decrement enable flag (u8, 1 = counting)
 *
 * The counter byte is reached through the truncated 16-bit pointer literal
 * 0xA4B0 (see the ROM literal pool @0xF5E2); on the SH-2 the on-chip RAM is
 * aliased so 0xA4B0 and 0xFFFFA4B0 address the same byte.  The other two
 * bytes use full 32-bit pointers (0xFFFFA4B1 / 0xFFFFA4B2).
 *
 * Verified: 3000 random pre-states vs the ROM emulator, 0 mismatches.
 */

#include <stdint.h>

#define RAM_PURGE_FLOW       (*(volatile uint8_t *)0xFFFFA4B0)
#define RAM_PURGE_FLOW_STATE (*(volatile uint8_t *)0xFFFFA4B1)
#define RAM_PURGE_DEC_EN     (*(volatile uint8_t *)0xFFFFA4B2)

void purge_flow_counter_init(void)
{
    RAM_PURGE_FLOW       = 0;
    RAM_PURGE_FLOW_STATE = 0;
    RAM_PURGE_DEC_EN     = 0;
}
