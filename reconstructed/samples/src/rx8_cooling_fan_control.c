/*
 * =============================================================================
 * rx8_cooling_fan_control.c  —  COOLING-FAN SENSOR VALIDITY + RISING-EDGE COUNTER
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x17DCC  (size 84 bytes to 0x17E20)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_cooling_fan_control.py
 *               (host-gcc vs tools/sh2emu.py over edge + random vectors;
 *               every RAM side-effect compared byte-for-byte, 0 mismatches).
 * Lift (truth): c/cooling_fan_control.c  (same address; the lift was itself
 *               verified vs the ROM emulator — 15400 random coolant/counter/
 *               cell combinations, whole call chain executed natively).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Cooling-fan sensor-validity check and rising-edge fan counter, called from
 * the time-critical task layer (engineControlCalculateTiming @0x145BE).  It
 * validates the coolant-temperature sensor float RAM[0xFFFFA73C] against a
 * tiny deadband and, on the rising edge of the fan-enable latch, bumps a fan
 * speed counter plus a redundant 8-bit shadow cell.
 *
 * ROM path (60E1D400.bin @0x17DCC):
 *
 *     2FE6  mov.l r14,@-r15           ; save r14
 *     F58D  fldi0 fr5                 ; fr5 = 0.0f (deadband centre)
 *     9367  mov.w 0x17EA2,r3          ; r3 = 0xA73C  (base of RAM[0xFFFFA73C])
 *     4F22  sts.l pr,@-r15
 *     C73A  mova  0x17EC0,r0          ; r0 = ROM eps literal @0x17EC0 (1e-5)
 *     F608  fmov.s @r0,fr6            ; fr6 = eps (deadband half-width)
 *     D23A  mov.l 0x17EC4,r2          ; r2 = 0x2440 complement_shift_u32
 *     420B  jsr   @r2
 *     F438  fmov.s @r3,fr4            ;   (delay) fr4 = coolant (float)
 *     D23A  mov.l 0x17EC8,r2          ; r2 = RAM[0xFFFFA95C] fan-enable latch
 *     6320  mov.b @r2,r3              ; r3 = fan-enable byte
 *     2338  tst   r3,r3
 *     8F17  bf/s  0x17E16             ; latch != 0 -> no rising edge
 *     6E03  mov   r0,r14              ;   (delay) r14 = valid (0x2440 result)
 *     60EC  extu.b r14,r0
 *     2008  tst   r0,r0
 *     8D13  bt/s  0x17E16             ; valid == 0  -> no rising edge
 *     0009  nop
 *     D236  mov.l 0x17ECC,r2          ; r2 = RAM[0xFFFFA93B] fan counter
 *     E501  mov   #0x01,r5
 *     D336  mov.l 0x17ED0,r3          ; r3 = 0x2478 addSaturate8Bit
 *     430B  jsr   @r3
 *     6420  mov.b @r2,r4              ;   (delay) r4 = counter
 *     D134  mov.l 0x17ECC,r1          ; r1 = RAM[0xFFFFA93B]
 *     D435  mov.l 0x17ED4,r4          ; r4 = RAM[0xFFFF8076] redundant cell
 *     2100  mov.b r0,@r1              ;   (delay) counter = sat8(counter+1)
 *     D335  mov.l 0x17ED8,r3          ; r3 = 0x3ED3C readValue_8bit
 *     430B  jsr   @r3
 *     E500  mov   #0x00,r5            ;   (delay) r5 = default 0
 *     6403  mov   r0,r4               ; r4 = cell value (or 0 if corrupt)
 *     D231  mov.l 0x17ED0,r2          ; r2 = 0x2478 addSaturate8Bit
 *     420B  jsr   @r2
 *     E501  mov   #0x01,r5            ;   (delay) r5 = 1
 *     D431  mov.l 0x17ED4,r4          ; r4 = RAM[0xFFFF8076]
 *     D332  mov.l 0x17EDC,r3          ; r3 = 0x3EE58 updateMemoryAtAddress_8bit
 *     430B  jsr   @r3
 *     6503  mov   r0,r5               ;   (delay) r5 = sat8(cell+1)
 * 0x17E16: D22C  mov.l 0x17EC8,r2     ; r2 = RAM[0xFFFFA95C]
 *     22E0  mov.b r14,@r2             ; latch = (uint8_t)valid   (ALWAYS)
 *     4F26  lds.l @r15+,pr
 *     000B  rts
 *     6EF6  mov.l @r15+,r14           ;   (delay)
 *
 * LEAF CALLS (executed natively by the emulator; each is a verified tiny leaf,
 * so it is modelled inline here instead of being left as a bare extern):
 *   0x2440  complement_shift_u32   deadband test: 1 iff |v - centre| > adj
 *   0x2478  addSaturate8Bit        min(a + b, 255)  (c/addSaturate8Bit.c)
 *   0x3ED3C readValue_8bit         value+~value u8 redundant cell read; on a
 *                                  mismatch sets RAM[0xFFFFC6AC] = 1 via the
 *                                  0x3F050 leaf and returns the caller default
 *                                  (see c/mem_accessors.c for the scheme)
 *   0x3EE58 updateMemoryAtAddress_8bit  write (value, ~value) u16 cell
 *
 * The deadband is exact: value=0.0f makes `0.0f - eps` == -eps and
 * `0.0f + eps` == +eps with a single rounding (negation is exact), so the two
 * float compares in complement_shift_u32 reproduce the ROM's fcmp/gt exactly
 * (NaN input -> both compares false -> valid = 0; |x| <= eps -> valid = 0).
 *
 * DISCREPANCY vs the lift: c/cooling_fan_control.c declares readValue_8bit /
 * updateMemoryAtAddress_8bit with a uint16_t address parameter, but the ROM
 * loads the full 32-bit address 0xFFFF8076 into r4 (mov.l 0x17ED4).  As
 * declared, 0xFFFF8076 would truncate to 0x8076 and read the wrong cell; this
 * port models the address as uint32_t (behavioural truth: the emulator, which
 * runs the real bytes).  Behaviour is otherwise exactly the lift's.
 *
 * RAM SIDE EFFECTS (the equivalence check compares all of these byte-exactly):
 *   RAM[0xFFFFA95C] fan-enable latch   always written, (uint8_t)valid
 *   RAM[0xFFFFA93B] fan speed counter  written iff latch==0 && valid!=0
 *   RAM[0xFFFF8076..77] redundant cell written iff the rising-edge path runs
 *   RAM[0xFFFFC6AC] corruption flag    written (1) iff the rising-edge path
 *                                      read a corrupt cell (0x3F050 side effect)
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_hw.h"

#define RAM_COOLANT   (*(volatile float *)0xFFFFA73C)  /* coolant sensor, f32  */
#define RAM_FAN_EN    (*(volatile uint8_t *)0xFFFFA95C)/* fan-enable latch      */
#define RAM_FAN_CNT   (*(volatile uint8_t *)0xFFFFA93B)/* fan speed counter     */
#define RAM_ERR_FLAG  (*(volatile uint8_t *)0xFFFFC6AC)/* redundancy error flag */

#define ROM_EPS       (*(const float *)0x00017EC0)     /* 1e-5, bits 0x3727C5AC */

/* 0x2440 — deadband test: 1 iff |centre - value| > adjustment (outside the
 * deadband).  c/complement_shift_u32.c, verified bit-exact. */
static int rx8_complement_shift_u32(float threshold, float value, float adjustment)
{
    if (value - adjustment > threshold) return 1;
    if (threshold > value + adjustment) return 1;
    return 0;
}

/* 0x2478 — saturating unsigned 8-bit add: min(a + b, 255). */
static uint8_t rx8_add_saturate_8bit(uint8_t a, uint8_t b)
{
    unsigned s = (unsigned)a + (unsigned)b;
    return s >= 255u ? 255u : (uint8_t)s;
}

/* 0x3ED3C — read a (value, ~value) u8 redundant cell; on a mismatch flag the
 * corruption (RAM[0xFFFFC6AC] = 1 via the 0x3F050 leaf) and return `dflt`. */
static uint8_t rx8_read_value_8bit(uint32_t addr, uint8_t dflt)
{
    uint8_t value = *(volatile uint8_t *)(uintptr_t)addr;
    uint8_t comp  = *(volatile uint8_t *)(uintptr_t)(addr + 1);
    if (value == (uint8_t)~comp)
        return value;
    RAM_ERR_FLAG = 1u;
    return dflt;
}

/* 0x3EE58 — write a (value, ~value) u16 redundant cell at addr. */
static void rx8_update_memory_at_address_8bit(uint32_t addr, uint8_t value)
{
    *(volatile uint8_t *)(uintptr_t)addr       = value;
    *(volatile uint8_t *)(uintptr_t)(addr + 1) = (uint8_t)~value;
}

/* 0x17DCC — validate the coolant sensor and count fan-on rising edges. */
void rx8_cooling_fan_control(void)
{
    int valid = rx8_complement_shift_u32(RAM_COOLANT, 0.0f, ROM_EPS);

    if (RAM_FAN_EN == 0u && valid != 0) {
        /* Rising edge of the fan-enable latch (was 0, sensor valid): bump the
         * published fan speed counter and the redundant 8-bit shadow cell. */
        RAM_FAN_CNT = rx8_add_saturate_8bit(RAM_FAN_CNT, 1u);

        uint8_t v = rx8_read_value_8bit(0xFFFF8076u, 0u);  /* 0 if corrupt */
        rx8_update_memory_at_address_8bit(0xFFFF8076u,
                                          rx8_add_saturate_8bit(v, 1u));
    }

    /* Latch the current validity — executed unconditionally (0x17E16-0x17E18). */
    RAM_FAN_EN = (uint8_t)valid;
}
