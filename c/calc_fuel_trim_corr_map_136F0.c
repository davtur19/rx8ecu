/* calc_fuel_trim_corr_map_136F0.c
 *
 * ROM: 60E1D400  |  Address: 0x136F0  |  Size: 0x8A bytes (0x136F0..0x13779)
 *                 0x136F0..0x13778 = code, 0x1377C..0x1379A = literal pool.
 *                 0x1379C = next function (sibling FPU trim routine).
 *
 * Fuel-trim "correction map" edge detector — sets two per-channel ACTIVE flags
 * (0xFFFFA714 / 0xFFFFA715) when either of two raw sensor/actuator bytes
 * (0xFFFFA415 / 0xFFFFA414) just CROSSED a calibration threshold, and latches
 * the two raw bytes into the previous-value shadow cells (0xFFFFA716 /
 * 0xFFFFA717).
 *
 * SIGNATURE:  void calc_fuel_trim_corr_map_136F0(void)
 *   - no arguments, no meaningful return (r0 is not set on the exit path;
 *     `rts`'s delay slot is a RAM store).
 *
 * RAM IN:
 *   0xFFFFA415  u8   channel-1 raw input byte  (r4)
 *   0xFFFFA414  u8   channel-2 raw input byte  (r6)
 *   0xFFFFA716  u8   channel-1 previous-value shadow (in/out)
 *   0xFFFFA717  u8   channel-2 previous-value shadow (in/out)
 *   0xFFFFA714  u8   channel-1 active flag (in/out — only written on edge)
 *   0xFFFFA715  u8   channel-2 active flag (in/out — only written on edge)
 *
 * CAL (ROM constants, fixed — read from the binary, not RAM):
 *   0x6E432  u8  threshold-1a  = 0x00      (channel-1 SET level)
 *   0x6E433  u8  threshold-1b  = 0x0C      (channel-1 CLEAR level)
 *   0x6E434  u8  threshold-2a  = 0x00      (channel-2 SET level)
 *   0x6E435  u8  threshold-2b  = 0x03      (channel-2 CLEAR level)
 *
 * RAM OUT:
 *   0xFFFFA714  u8   = 1 when ch1 input just became == th1a (and was not
 *                      already th1a last call); = 0 when ch1 input just
 *                      became == th1b (and was not th1b last call);
 *                      unchanged otherwise.
 *   0xFFFFA715  u8   same logic for channel 2 against th2a / th2b.
 *   0xFFFFA716  u8   := channel-1 input byte (shadow latched every call)
 *   0xFFFFA717  u8   := channel-2 input byte (shadow latched every call)
 *
 * SEMANTICS (human):
 *   This is a per-channel rising/falling EDGE detector on two raw byte signals
 *   (read e.g. from a sensor/actuator feedback path).  It compares the CURRENT
 *   sample against the value captured LAST call (the shadow cells): the active
 *   flag is only touched on the exact sample where the signal crosses a
 *   calibration level, and then it is forced to 1 (on the lower "SET" level)
 *   or to 0 (on the upper "CLEAR" level).  Between crossings the flag keeps its
 *   previous state, and the shadow cells are re-latched with the fresh samples
 *   so the NEXT call can detect the next crossing.  The two channels are
 *   independent (channel-1 level pair 0x00/0x0C, channel-2 pair 0x00/0x03).
 *
 * Byte-for-byte from the disasm (both `cmp/eq` sides verify against the shadow
 * before writing, so a flag write happens exactly once per crossing):
 *
 *     a1 = u8@0xFFFFA415;  a2 = u8@0xFFFFA414
 *     p1 = u8@0xFFFFA716;  p2 = u8@0xFFFFA717
 *
 *     if (a1 == ROM[0x6E432] && p1 != ROM[0x6E432]) flag1 = 1;
 *     if (a1 == ROM[0x6E433] && p1 != ROM[0x6E433]) flag1 = 0;
 *     if (a2 == ROM[0x6E434] && p2 != ROM[0x6E434]) flag2 = 1;
 *     if (a2 == ROM[0x6E435] && p2 != ROM[0x6E435]) flag2 = 0;
 *
 *     RAM[0xFFFFA716] = a1;  RAM[0xFFFFA717] = a2;   // rts delay slot
 *
 * Track A: verified against the emulated ROM bytes (tools/sh2emu.py) over a
 * structured sweep + 20000 seeded random vectors, 0 mismatches.  Test:
 * c/tests/test_calc_fuel_trim_corr_map_136F0.py.
 */
#include <stdint.h>

#define RAM8(addr)      (*(volatile uint8_t *)(uintptr_t)(addr))
#define CAL8(addr)      (*(const  uint8_t *)(uintptr_t)(addr))

/* calibration thresholds (ROM constants @0x6E432..0x6E435 in 60E1D400.bin) */
#define CAL_CH1_SET     CAL8(0x6E432)   /* = 0x00 */
#define CAL_CH1_CLR     CAL8(0x6E433)   /* = 0x0C */
#define CAL_CH2_SET     CAL8(0x6E434)   /* = 0x00 */
#define CAL_CH2_CLR     CAL8(0x6E435)   /* = 0x03 */

#define RAM_CH1_IN      RAM8(0xFFFFA415)  /* channel-1 raw input byte  (r4) */
#define RAM_CH2_IN      RAM8(0xFFFFA414)  /* channel-2 raw input byte  (r6) */
#define RAM_CH1_SHADOW  RAM8(0xFFFFA716)  /* channel-1 previous-value shadow */
#define RAM_CH2_SHADOW  RAM8(0xFFFFA717)  /* channel-2 previous-value shadow */
#define RAM_FLAG1       RAM8(0xFFFFA714)  /* channel-1 active flag */
#define RAM_FLAG2       RAM8(0xFFFFA715)  /* channel-2 active flag */

void calc_fuel_trim_corr_map_136F0(void)
{
    uint8_t a1 = RAM_CH1_IN;      /* mov.b @0xFFFFA415 -> r4 */
    uint8_t a2 = RAM_CH2_IN;      /* mov.b @0xFFFFA414 -> r6 */
    uint8_t p1 = RAM_CH1_SHADOW;  /* mov.b @0xFFFFA716 */
    uint8_t p2 = RAM_CH2_SHADOW;  /* mov.b @0xFFFFA717 */

    /* channel 1: SET / CLEAR edge detection (0x136F8..0x13732) */
    if (a1 == CAL_CH1_SET && p1 != CAL_CH1_SET)
        RAM_FLAG1 = 1;
    if (a1 == CAL_CH1_CLR && p1 != CAL_CH1_CLR)
        RAM_FLAG1 = 0;

    /* channel 2: SET / CLEAR edge detection (0x13734..0x13770) */
    if (a2 == CAL_CH2_SET && p2 != CAL_CH2_SET)
        RAM_FLAG2 = 1;
    if (a2 == CAL_CH2_CLR && p2 != CAL_CH2_CLR)
        RAM_FLAG2 = 0;

    /* latch shadows (0x13772..0x1377A: stores in rts delay slot) */
    RAM_CH1_SHADOW = a1;
    RAM_CH2_SHADOW = a2;
}
