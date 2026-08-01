/* radiator_fan_relay_write.c
 *
 * ROM: 60E1D400  |  Address: 0x259C0  |  Size: 40 bytes  |  VERIFIED vs ROM emulator
 *
 * Drives the radiator fan relay byte from bit 0 of a status byte,
 * active-low: the relay is energized (1) when the bit is clear.
 *
 *   RAM[0xFFFFB5AB] = (RAM[0xFFFF9ECD] & 1) ? 0 : 1
 *
 * Verified: exhaustive 0..255 + 3000 random inputs, 0 mismatches.
 */

#include <stdint.h>

#define RAM_FAN_RELAY (*(volatile uint8_t *)0xFFFFB5AB)
#define RAM_STATUS    (*(volatile uint8_t *)0xFFFF9ECD)

void radiator_fan_relay_write(void)
{
    RAM_FAN_RELAY = (RAM_STATUS & 1) ? 0 : 1;
}
