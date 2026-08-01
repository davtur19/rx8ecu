/**
 * SetMemoryNotValid2 @ 0x3E5A8 (60E0FC00)
 *
 * Purpose:
 *   Write 1 to a RAM fault/memory-invalid flag, then return.
 *   Similar to setMemInsideFUNCto1, but targets a different address.
 *
 *   The "2" suffix suggests there are multiple variants of this
 *   memory-not-valid flag setter for different subsystems.
 *
 * RAM:
 *   0xFFFFA400-ish  uint8_t  Fault/memory-invalid flag
 *   (exact address depends on ROM image; the Equinox 60E0FC00
 *    image writes to the address obtained from the PC-relative
 *    pool at 0x3E6B8)
 */

#include <stdint.h>

#define MEM_INVALID_ADDR (*(volatile uint8_t *)0xFFFFC63A)

void SetMemoryNotValid2(void)
{
    MEM_INVALID_ADDR = 1;
}
