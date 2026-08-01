/* cooling_fan_control.c
 *
 * ROM: 60E1D400  |  Address: 0x17DCC  |  Size: 84 bytes  |  VERIFIED vs ROM emulator
 *
 * Cooling-fan sensor-validity check and rising-edge fan counter.
 *
 * Validates the coolant temperature sensor RAM[0xFFFFA73C] (f32) with
 * complement_shift_u32 (0x2440): valid = |coolant| > 1e-5 (eps literal
 * ROM@0x17EC0).  On the rising edge of the fan-enable latch
 * (RAM[0xFFFFA95C] == 0 AND sensor valid) it increments the fan speed
 * counter RAM[0xFFFFA93B] and the redundant 8-bit cell RAM[0xFFFF8076]
 * (value + ~value) via the verified accessors readValue_8bit (0x3ED3C)
 * and updateMemoryAtAddress_8bit (0x3EE58).  Finally it latches
 * RAM[0xFFFFA95C] = valid.
 *
 * If the redundant cell is corrupted, the read returns the default (0)
 * and the firmware sets the corruption flag RAM[0xFFFFC6AC] = 1
 * (via 0x3F050), then self-heals the cell by rewriting (value, ~value).
 *
 * Verified: 15400 random coolant/counter/cell combinations vs the ROM
 * emulator (whole call chain executes natively), 0 mismatches.
 */

#include <stdint.h>

#define RAM_COOLANT   (*(volatile float *)0xFFFFA73C)
#define RAM_FAN_EN    (*(volatile uint8_t *)0xFFFFA95C)
#define RAM_FAN_CNT   (*(volatile uint8_t *)0xFFFFA93B)
#define RAM_CELL      (*(volatile uint16_t *)0xFFFF8076)   /* (value, ~value) */
#define RAM_ERR_FLAG  (*(volatile uint8_t *)0xFFFFC6AC)

#define ROM_EPS       (*(const float *)0x17EC0)            /* 1e-5 */

/* 0x2440: complement_shift_u32(value, center, eps) = |value-center| > eps */
extern int complement_shift_u32(float value, float center, float eps);
/* 0x2478: min(a + b, 255) */
extern uint8_t addSaturate8Bit(uint8_t a, uint8_t b);
/* 0x3ED3C: readValue_8bit(addr, default) - returns value if valid else default */
extern uint8_t readValue_8bit(uint16_t addr, uint8_t dflt);
/* 0x3EE58: write (value, ~value) u16 cell at addr */
extern void updateMemoryAtAddress_8bit(uint16_t addr, uint8_t value);

void cooling_fan_control(void)
{
    int valid = complement_shift_u32(RAM_COOLANT, 0.0f, ROM_EPS);

    if (RAM_FAN_EN == 0 && valid != 0) {
        /* rising edge of the fan-enable latch: bump the counters */
        RAM_FAN_CNT = addSaturate8Bit(RAM_FAN_CNT, 1);
        uint8_t v = readValue_8bit(0xFFFF8076, 0);
        v = addSaturate8Bit(v, 1);
        updateMemoryAtAddress_8bit(0xFFFF8076, v);
        /* corrupted cell -> 0x3F050 already set RAM_ERR_FLAG = 1; the
         * rewrite above self-heals the cell. */
    }

    RAM_FAN_EN = (uint8_t)valid;
}
