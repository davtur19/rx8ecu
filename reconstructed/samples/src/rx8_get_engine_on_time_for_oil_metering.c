/*
 * =============================================================================
 * rx8_get_engine_on_time_for_oil_metering.c  —  ENGINE-ON TIME ACCUMULATOR
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0xE492  (34 bytes: 0xE492 .. 0xE4B3)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_get_engine_on_time_for_oil_metering.py
 *               (host-gcc vs tools/sh2emu.py over edge + 20000 random vectors,
 *               RAM side-effect at 0xFFFFA422 compared byte-exactly;
 *               0 mismatches).
 * Lift (truth): c/getEngineOnTimeForOilMetering.c  (same address; also
 *               c/tests/test_getEngineOnTimeForOilMetering.py structural check)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Per-tick accumulation of total engine running time used by the oil-metering
 * pump (OMP) calculations.  Once per scheduling tick, while the engine-running
 * flag is set, the 16-bit engine-on timer word is bumped by +1 through the
 * saturating 16-bit add leaf @0x2460 (add16bitSaturate, c/add16bitSaturate.c).
 * Disassembly of 60E1D400.bin @ 0xE492:
 *
 *     4F22   sts.l pr,@-r15            ; prologue (save PR)
 *     9232   mov.w @(0xE4FC,PC),r2     ; r2 = SIGN-EXT(0xA428) = 0xFFFFA428
 *     6020   mov.b @r2,r0              ; r0 = flag byte @0xFFFFA428
 *     600C   extu.b r0,r0              ; zero-extend to 0..255
 *     8801   cmp/eq #0x01,r0           ; T = (flag == 1)
 *     8F07   bf/s  0xE4AE              ; flag != 1 -> skip the accumulate
 *     0009   nop
 *     912E   mov.w @(0xE500,PC),r1     ; r1 = SIGN-EXT(0xA422) = 0xFFFFA422
 *     E501   mov    #0x01,r5           ; r5 = 1  (accumulator increment)
 *     D318   mov.l @(0xE508,PC),r3     ; r3 = 0x00002460  (add16bitSaturate)
 *     430B   jsr    @r3                ; call the leaf
 *     6411   mov.w @r1,r4              ;   (delay) r4 = timer @0xFFFFA422
 *     9229   mov.w @(0xE500,PC),r2     ; r2 = 0xFFFFA422
 *     2201   mov.w r0,@r2              ; timer @0xFFFFA422 = r0
 *     4F26   lds.l @r15+,pr            ; epilogue
 *     000B   rts
 *     0009   nop
 *
 * The 0x2460 leaf is add16bitSaturate:  extu.w both operands, add (32-bit),
 * clamp at 0xFFFF -> result = min((u16)current + (u16)inc, 0xFFFF).  With the
 * call site's constant inc = 1 the timer thus counts 0,1,2,...,0xFFFF and then
 * sticks at 0xFFFF (never wraps to 0).
 *
 * CALLING CONVENTION
 * ------------------
 * ABI-clean void leaf: takes NO register arguments (both RAM addresses come
 * from PC-relative literals, so r4-r7 are ignored on entry) and returns
 * nothing (r0 is left holding the timer after the epilogue but no caller
 * consumes it).  Internally it drives the non-ABI leaf 0x2460 via
 * `jsr @r3` (r4 = timer, r5 = 1) and stores its r0 return value back to RAM.
 *
 * RAM SIDE EFFECTS (mirrored byte-exactly by the harness)
 * -------------------------------------------------------
 * - reads u8  @0xFFFFA428 (engine-running flag; ONLY == 1 triggers)
 * - reads u16 @0xFFFFA422 (engine-on timer)
 * - writes u16 @0xFFFFA422 (timer + 1, saturating) iff flag == 1
 *
 * DISCREPANCIES vs THE LIFT
 * -------------------------
 * 1. The c/ lift spells the cells as 0x0000A428 / 0x0000A422 (the 16-bit
 *    literal values printed by the disassembler).  The ROM loads them with
 *    `mov.w @(disp,PC)` which SIGN-EXTENDS, so the real accessed addresses
 *    are 0xFFFFA428 / 0xFFFFA422 in the on-chip RAM window
 *    (0xFFFF6000..0xFFFFDFFF) — the low 0x0000Axxx form is the same physical
 *    RAM aliased through the window.  The reconstructed source uses the
 *    sign-extended 0xFFFFxxxx forms (host-compatible, above mmap_min_addr);
 *    the emulator run in the harness confirmed the ROM reads the 0xFFFFxxxx
 *    cells (seeding 0xA422 only yields garbage), so the lift's low-form
 *    addresses are a display artifact, not the real access.
 * 2. The c/ lift calls an extern `timer_accumulator_function`; this sample
 *    inlines the leaf's semantics (add16bitSaturate @0x2460, c/add16bitSaturate.c)
 *    so the host build is self-contained.  Behaviour is identical for every
 *    (current, inc) pair the call site can produce.
 * 3. Context: c/throttle_position_sensor.c documents the 0xFFFFA428 word as
 *    "Main TPS processed value" and c/idle_speed_control_18054.c as
 *    "engine-state / TPS-low-byte" — the low byte doubles as the engine-running
 *    flag this routine tests; only the byte read (`mov.b`+`extu.b`, == 1) is
 *    used here.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"

#define RX8_OMP_ENGINE_FLAG   RX8_IO8(0xFFFFA428u)   /* engine-running flag   */
#define RX8_OMP_ENGINE_ON_TMR RX8_IO16(0xFFFFA422u)  /* engine-on timer (u16) */

/* Saturating 16-bit add leaf @0x2460 (add16bitSaturate, c/add16bitSaturate.c):
 * min((u16)a + (u16)b, 0xFFFF).  The call site only ever passes inc = 1. */
static uint16_t rx8_omp_add16_saturate(uint16_t current, uint16_t inc)
{
    uint32_t sum = (uint32_t)current + (uint32_t)inc;
    return (sum >= 0xFFFFu) ? (uint16_t)0xFFFFu : (uint16_t)sum;
}

/* 0xE492 — bump the oil-metering engine-on timer by 1 while the engine runs. */
void rx8_get_engine_on_time_for_oil_metering(void)
{
    if (RX8_OMP_ENGINE_FLAG == 1u) {
        RX8_OMP_ENGINE_ON_TMR = rx8_omp_add16_saturate(RX8_OMP_ENGINE_ON_TMR, 1u);
    }
}
