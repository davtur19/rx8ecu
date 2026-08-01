/*
 * =============================================================================
 * rx8_immo_bad_state_set.c  —  IMMOBILIZER "BAD STATE" MARKER (SIDE-EFFECT LEAF)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x365B8
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_immo_bad_state_set.py
 *               (host-gcc vs tools/sh2emu.py over edge + N random initial
 *               RAM states, comparing all four side-effected cells;
 *               0 mismatches).
 * Lift (truth): c/ImmoBadStateSet.c  (ImmoBadStateSet @ 0x365B8)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Marks the immobilizer state as "bad": the lamp is turned off, the CAN TX
 * data flag is cleared, the bad-state timeout is (re)loaded with 500 and the
 * result/state code is set to 4.  It is a void leaf with no arguments and no
 * register return — its only observable effect is the RAM it writes, so it is
 * driven through the standard SH2.call() entry and checked by comparing the
 * side-effected bytes (same rig as rx8_radiator_fan_relay_write / 0x259C0).
 *
 * Disassembly of 60E1D400.bin @ 0x365B8 (22 bytes, 0x365B8-0x365D5):
 *
 *     4F22   sts.l        pr,@-r15       ; save PR
 *     D32C   mov.l        0x3666C,r3     ; r3 = 0x000263C8 (setImmoLight)
 *     430B   jsr          @r3            ;   -> setImmoLight(0)
 *     E400   mov          #0x00,r4       ;     (delay slot) r4 = 0 (lamp off)
 *     9351   mov.w        0x36666,r3     ; r3 = signext(0xC240) = 0xFFFFC240
 *     E200   mov          #0x00,r2       ; r2 = 0
 *     9150   mov.w        0x36668,r1     ; r1 = 0x01F4 (500)
 *     2320   mov.b        r2,@r3         ; byte@0xFFFFC240 = 0   (CAN TX flag)
 *     D029   mov.l        0x36670,r0     ; r0 = 0xFFFFC284 (bad-state timeout)
 *     E204   mov          #0x04,r2       ; r2 = 4 (result code)
 *     2011   mov.w        r1,@r0         ; word@0xFFFFC284 = 0x01F4
 *     D129   mov.l        0x36674,r1     ; r1 = 0xFFFFC28D (state/result byte)
 *     4F26   lds.l        @r15+,pr       ; restore PR
 *     000B   rts
 *     2120   mov.b        r2,@r1         ;   (delay slot) byte@0xFFFFC28D = 4
 *
 * RAM SIDE EFFECTS (the harness compares every one of these cells)
 * -----------------------------------------------------------------
 *   1. word @0xFFFFF754  &= ~0x0060  — the immo lamp bits.  The ROM reaches
 *      this through the jsr to setImmoLight(0) @0x263C8, which issues
 *      reg16SetClear(0xFFFFF754, 0x20, 0) then reg16SetClear(0xFFFFF754,
 *      0x40, 0) — i.e. two read-modify-writes that clear bits 0x20 and 0x40
 *      of the LC/status word (RX8_STATUS_WORD in include/rx8_hw.h).  The
 *      composite on plain on-chip RAM is `word &= ~0x0060`.
 *   2. byte @0xFFFFC240 = 0           — CAN TX data flag (clear).
 *   3. word @0xFFFFC284 = 0x01F4      — bad-state timeout (500 ticks).
 *   4. byte @0xFFFFC28D = 4           — immobilizer result/state code.
 *
 * VERIFYING THE LIFT / DISCREPANCIES
 * ----------------------------------
 * The lift in c/ImmoBadStateSet.c was checked against the raw ROM bytes
 * (disassembly above) and against tools/sh2emu.py: 0 mismatches on the
 * direct writes, with two notes on faithful reconstruction:
 *  1. the lift's CAN_TX_DATA macro is written as 0x0000C240, but the ROM's
 *     `mov.w` PC-relative load sign-extends the literal 0xC240 to the
 *     effective address 0xFFFFC240 (the on-chip CAN block).  This sample
 *     writes the CPU's actual address 0xFFFFC240;
 *  2. the lift models the lamp-off as a call to setImmoLight(0) @0x263C8.
 *     That subroutine's observable effect (clear bits 0x20/0x40 of the word
 *     at 0xFFFFF754 — confirmed from its disassembly) is folded inline here
 *     so the sample is self-contained; the harness still validates it
 *     against the REAL setImmoLight bytes executed inside the emulator.
 *  3. the ROM touches the stack while calling setImmoLight (pushes r10-r14/
 *     pr and a 24-byte frame at 0xFFFFDFxx); those cells are transient and
 *     restored, so they are not part of the observable state.
 * =============================================================================
 */
#include <stdint.h>
#include <stddef.h>

#include "rx8_hw.h"
#include "rx8_samples.h"

/* ---- 0x365B8  mark the immobilizer state as bad (see header) ---------- */
void rx8_immo_bad_state_set(void)
{
    /* jsr 0x263C8 — setImmoLight(0): clear the immo-lamp bits 0x20/0x40 of
     * the status word 0xFFFFF754 (two reg16SetClear calls, mask 0x20 then
     * 0x40; see the header note for the fold-in). */
    RX8_IO16(0xFFFFF754) &= ~0x0060u;

    RX8_IO8(0xFFFFC240)   = 0u;        /* CAN TX data flag = 0    */
    RX8_IO16(0xFFFFC284)  = 0x01F4u;   /* bad-state timeout = 500 */
    RX8_IO8(0xFFFFC28D)   = 4u;        /* state/result code = 4   */
}
