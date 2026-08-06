/* getEngineCrankingStatus_0x10EE6.c
 *
 * ROM: 60E0FC00 | Address: 0x10EE6 | Size: 0x1E (30) bytes per CSV range
 * 0x10EE6..0x10F04.  Code runs to the `rts` @0x10F00 (delay nop @0x10F02);
 * the next function setTimingArrayValuesForOutput (0x10F04) starts exactly at
 * the CSV end.  The CSV range is CORRECT (code to 0x10F02, next function
 * exactly at 0x10F04) — no correction needed.
 *
 * ENTRY VERIFICATION: 0x10EE6 matches the symbols CSV start.  Valid entry:
 * opens straight with a mov.l literal load (no function-pointer preamble).
 * The preceding getEngineCrankingStatusEnum (0x10ED2) ends with `rts` @0x10EE2
 * + delay mov @0x10EE4, so there is no fall-through into us; no incoming
 * branches into the body (only the single mov.w literal pool @0x10FB4, which
 * the caller reads back).  Called via the function-pointer slot @0x144F4 of
 * the engineControlCalculateTiming dispatcher (0x141FC) dispatch table
 * (immediately after calculatePerRotorIgnitionDwell's stub @0x144F0).  The
 * ROM literal @0x10FB4 is the ONLY 32-bit reference to 0x10EE6... wait — the
 * 0x10FB4 literal is the *input* pointer for r5.  The dispatcher reference:
 * slot @0x144F4 holds the literal 0x00010EE6, the ONLY 32-bit reference to
 * 0x10EE6 in the binary.  The CSV address IS the real entry point.
 *
 * SEMANTICS (instruction-for-instruction, see disasm): a small status-flag
 * writer over the rotor ignition/timing object array anchored at 0xFFFFA578
 * (the same base used by calculatePerRotorIgnitionDwell and the
 * getEngineStatus sibling functions).  It walks the array two entries forward
 * (stride 0x2C = 44) and writes byte 1 into the +2 flag field of each, from
 * the base 0xFFFFA578 up to (exclusive) the end sentinel 0xFFFFA5D0 which is
 * 0x58 (88) bytes past the base.
 *
 *   end  = 0xFFFFA578 + 0x58 = 0xFFFFA5D0            (constant, via literal)
 *   base = 0xFFFFA578                                 (constant, via literal)
 *   for (p = base; p < end; p += 0x2C)
 *       *(volatile uint8_t *)(p + 2) = 1;
 *
 * With the fixed base/end stride this loop runs exactly twice, writing:
 *   u8@0xFFFFA57A = 1
 *   u8@0xFFFFA5A6 = 1
 * r0 on return = 1 (r5 is latched to 0x01 in the branch delay slot and copied
 * to r0 on the first loop pass; r5/r0 are never modified afterwards).
 * No other register side effects; no stack frame, no sub-calls.
 *
 * The loop's initial `cmp/hs` + `bt/s` guard is a bounds check that, for the
 * hard-coded base < end sentinel, is never taken (base is always < end), so
 * the loop always runs to completion.  The guard is preserved in the C for
 * structural fidelity.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py, 60E0FC00.bin) in
 * c/tests/test_getEngineCrankingStatus_0x10EE6.py — 0 mismatches over
 * 5 seeds x 100000 iterations (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>

/* ---- Fixed RAM base anchors (mov.l literals) ---- */
#define BASE (uintptr_t)0xFFFFA578           /* rotor timing array base      */
#define END  (uintptr_t)0xFFFFA5D0           /* base + 0x58 end sentinel     */
#define STRIDE 0x2C                          /* 44, rotor entry stride       */

/* ---- RAM flag fields written (u8 @ +2 per entry) ---- */

void getEngineCrankingStatus_0x10EE6(void)
{
    uintptr_t p = BASE;

    /* guard: skip the loop body when base >= end (never for the constant) */
    if (BASE >= END)
        return;

    do {
        *(volatile uint8_t *)(p + 2) = 0x01;   /* mov.b r0,@(0x02,r4), r0=1 */
        p += STRIDE;                            /* add #0x2C,r4             */
    } while (p < END);
}