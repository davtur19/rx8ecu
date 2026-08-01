/**
 * setMemInsideFUNCto1 @ 0x3E3F0 (60E0FC00)
 *
 * Purpose:
 *   Set a RAM fault flag byte to 1. This is one of many small helper
 *   functions that the ECU uses to mark memory locations as faulted
 *   or invalid.
 *
 *   This specific function writes 1 to address 0xFFFFC638, which
 *   likely indicates "inside function" or "in-progress" state for
 *   a sensor processing routine.
 *
 * RAM:
 *   0xFFFFC638  uint8_t  Fault/memory flag
 */

#include <stdint.h>

#define MEM_FLAG_ADDR (*(volatile uint8_t *)0xFFFFC638)

void setMemInsideFUNCto1(void)
{
    MEM_FLAG_ADDR = 1;
}
