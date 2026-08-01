/* purge_state_query.c
 *
 * ROM: 60E1D400  |  Address: 0xF5DC  |  Size: 6 bytes  |  VERIFIED vs ROM emulator
 *
 * EVAP purge state query.  Returns the current purge flow state byte
 * (RAM[0xFFFFA4B1]) — the value produced by purge_control_state_update().
 * A 6-byte leaf: load pointer, delay-slot read into r0, rts.
 *
 * Verified: exhaustive over all 256 state byte values vs the ROM emulator,
 * 0 mismatches.
 */

#include <stdint.h>

#define RAM_PURGE_FLOW_STATE (*(volatile uint8_t *)0xFFFFA4B1)

uint8_t purge_state_query(void)
{
    return RAM_PURGE_FLOW_STATE;
}
