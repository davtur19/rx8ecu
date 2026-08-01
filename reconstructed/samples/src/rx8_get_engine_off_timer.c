/*
 * =============================================================================
 * rx8_get_engine_off_timer.c  —  ENGINE-OFF ELAPSED-TIME ACCUMULATOR
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x3279E  (40 bytes: 0x3279E .. 0x327C5)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_get_engine_off_timer.py
 *               (host-gcc vs tools/sh2emu.py over edge + random vectors,
 *               RAM side-effect at 0xFFFFBFD6 compared byte-exactly;
 *               0 mismatches).
 * Lift (truth): c/getEngineOffTimer.c  (same address; the 0x2460 leaf it calls
 *               is add16bitSaturate, c/add16bitSaturate.c)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Per-tick accumulator tracking how long the engine has been off: while the
 * engine-running flag is set the 16-bit timer word is bumped by +1 through the
 * saturating 16-bit add leaf @0x2460; the instant the flag clears the word is
 * reset to 0, so a caller can read "elapsed time since the engine last started
 * running" straight out of RAM.  Disassembly of 60E1D400.bin @ 0x3279E:
 *
 *     2FE6   mov.l r14,@-r15            ; prologue (save r14)
 *     4F22   sts.l pr,@-r15             ;           (save PR)
 *     DE2D   mov.l @(0x32858,PC),r14    ; r14 = 0xFFFFBFD6 (timer cell)
 *     934B   mov.w @(0x3283E,PC),r3     ; r3 = SIGN-EXT(0xA41C) = 0xFFFFA41C
 *     6030   mov.b @r3,r0               ; r0 = flag byte @0xFFFFA41C
 *     600C   extu.b r0,r0               ; zero-extend to 0..255
 *     8801   cmp/eq #0x01,r0            ; T = (flag == 1)
 *     8F06   bf/s 0x327BC               ; flag != 1 -> else (zero the timer)
 *     0009   nop
 *     D12A   mov.l @(0x3285C,PC),r1     ; r1 = 0x00002460 (add16bitSaturate)
 *     E501   mov #0x01,r5               ; r5 = 1  (accumulator increment)
 *     410B   jsr @r1                    ; call the leaf
 *     64E1   mov.w @r14,r4              ;   (delay) r4 = timer @0xFFFFBFD6
 *     A002   bra 0x327C0                ; skip the else
 *     2E01   mov.w r0,@r14              ;   (delay) timer @0xFFFFBFD6 = r0
 *     E200   mov #0x00,r2               ; else: r2 = 0
 *     2E21   mov.w r2,@r14              ; timer @0xFFFFBFD6 = 0
 *     4F26   lds.l @r15+,pr             ; epilogue
 *     000B   rts
 *     6EF6   mov.l @r15+,r14            ;   (delay) restore r14
 *
 * The 0x2460 leaf is add16bitSaturate:  extu.w both operands, add (32-bit),
 * clamp at 0xFFFF -> result = min((u16)current + (u16)inc, 0xFFFF).  With the
 * call site's constant inc = 1 the timer thus counts 0,1,2,...,0xFFFF and then
 * sticks at 0xFFFF (never wraps to 0), exactly like the oil-metering engine-on
 * accumulator @0xE492 (samples/rx8_get_engine_on_time_for_oil_metering.c).
 *
 * CALLING CONVENTION
 * ------------------
 * ABI-clean void leaf: takes NO register arguments (both RAM addresses come
 * from PC-relative literals, so r4-r7 are ignored on entry) and returns
 * nothing.  Internally it drives the non-ABI leaf 0x2460 via `jsr @r1`
 * (r4 = timer, r5 = 1) and stores its r0 return value back to RAM.
 *
 * RAM SIDE EFFECTS (mirrored byte-exactly by the harness)
 * -------------------------------------------------------
 * - reads u8  @0xFFFFA41C (engine-running flag; ONLY == 1 triggers)
 * - reads u16 @0xFFFFBFD6 (engine-off timer)
 * - writes u16 @0xFFFFBFD6 (timer + 1 saturating) iff flag == 1, else 0
 *
 * DISCREPANCIES vs THE LIFT
 * -------------------------
 * 1. The c/ lift spells the flag cell as 0x0000A41C (the 16-bit literal value
 *    printed by the disassembler).  The ROM loads it with `mov.w @(disp,PC)`
 *    which SIGN-EXTENDS, so the real accessed address is 0xFFFFA41C in the
 *    on-chip RAM window (0xFFFF6000..0xFFFFDFFF) — the low 0x0000A41C form is
 *    the same physical RAM aliased through the window.  The reconstructed
 *    source uses the sign-extended 0xFFFFA41C form (host-compatible, above
 *    mmap_min_addr); the emulator run in the harness confirmed the ROM reads
 *    the 0xFFFFA41C cell (seeding 0xA41C only yields garbage).
 * 2. The c/ lift declares `extern uint16_t timer_accumulator_function(uint16_t
 *    current, uint8_t mode)` and passes 1 as a "mode".  The 0x2460 leaf is in
 *    fact add16bitSaturate(current, inc) — the second operand is the additive
 *    INCREMENT, not a mode selector; this sample inlines the leaf's semantics
 *    (c/add16bitSaturate.c) so the host build is self-contained.  Behaviour is
 *    identical for every (current, inc) pair the call site can produce.
 * 3. Semantics: despite the ROM symbol "getEngineOffTimer", the word counts UP
 *    while the engine-running flag == 1 and is ZEROED when the flag clears
 *    (the flag low byte at 0xFFFFA41C doubles as the engine-running/state byte
 *    this routine tests, cf. c/throttle_position_sensor.c on the 0xFFFFA428
 *    word).  The reconstructed source follows the ROM bytes; the lift's
 *    prose ("calls a timer-continue function when engine running, resets when
 *    off") describes the same control flow.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"

#define RX8_OFF_ENGINE_FLAG RX8_IO8(0xFFFFA41Cu)   /* engine-running flag   */
#define RX8_OFF_TIMER       RX8_IO16(0xFFFFBFD6u)  /* engine-off timer (u16) */

/* Saturating 16-bit add leaf @0x2460 (add16bitSaturate, c/add16bitSaturate.c):
 * min((u16)a + (u16)b, 0xFFFF).  The call site only ever passes inc = 1. */
static uint16_t rx8_off_add16_saturate(uint16_t current, uint16_t inc)
{
    uint32_t sum = (uint32_t)current + (uint32_t)inc;
    return (sum >= 0xFFFFu) ? (uint16_t)0xFFFFu : (uint16_t)sum;
}

/* 0x3279E — engine-off elapsed-time accumulator (+1 while running, 0 when off). */
void rx8_get_engine_off_timer(void)
{
    if (RX8_OFF_ENGINE_FLAG == 1u) {
        RX8_OFF_TIMER = rx8_off_add16_saturate(RX8_OFF_TIMER, 1u);
    } else {
        RX8_OFF_TIMER = 0;
    }
}
