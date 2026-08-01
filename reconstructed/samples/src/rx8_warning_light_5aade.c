/*
 * =============================================================================
 * rx8_warning_light_5aade.c  —  WARNING-LIGHT VALUE SETTER (SIDE-EFFECT LEAF)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x5AADE
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_warning_light_5aade.py
 *               (host-gcc vs tools/sh2emu.py over edge + N random vectors,
 *               comparing the side-effected warning-light byte; 0 mismatches;
 *               c/tests/test_warning_light_0x5AADE.py additionally sweeps all
 *               256 status bytes exhaustively).
 * Lift (truth): c/warning_light_0x5AADE.c  (68 bytes, 0x5AADE-0x5AB66)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A pure side-effect leaf: it maps the lamp-status byte RAM[0xFFFFCD4C] to a
 * warning-light value byte RAM[0xFFFFD2C5]:
 *
 *   b = byte@0xFFFFCD4C
 *   v = (b & 0x60) ? 0x6D : (b & 0x1C) ? 0x69 : (b & 0x80) ? 0x68 : 0
 *   byte@0xFFFFD2C5 = v
 *
 * Disassembly of 60E1D400.bin @ 0x5AADE (mov.w sign-extends, so the 16-bit
 * literals 0xCD4C/0xD2C5 become 0xFFFFCD4C/0xFFFFD2C5):
 *
 *     9544   mov.w @(0x44,PC),r5     ; r5 = 0xFFFFD2C5  (write target)
 *     9442   mov.w @(0x42,PC),r4     ; r4 = 0xFFFFCD4C  (read source)
 *     6043   mov   r4,r0
 *     6000   mov.b @r0,r0            ; b = RAM[0xFFFFCD4C] (sign-extended)
 *     C840   tst   #0x40,r0
 *     0029   movt  r0
 *     70FF   add   #-1,r0
 *     600B   neg   r0,r0
 *     8801   cmp/eq #1,r0            ; r0 == 1  iff  bit 0x40 set
 *     8D09   bt/s  0x5AB06           ;   b & 0x40  -> 0x6D
 *     0009   nop                     ;     (delay slot)
 *     ...    same tst/movt/add/neg/cmp/eq idiom repeated for 0x20 -> 0x6D,
 *            0x10, 0x08, 0x04 -> 0x69, and finally 0x80 -> 0x68
 *     E26D   mov   #0x6D,r2          ; 109 (warn-oil / first lit lamps)
 *     E269   mov   #0x69,r2          ; 105
 *     E268   mov   #0x68,r2          ; 104
 *     E100   mov   #0,r1
 *     2520   mov.b r2,@r5            ; RAM[0xFFFFD2C5] = v   (delayed bra)
 *     2510   mov.b r1,@r5            ; RAM[0xFFFFD2C5] = 0
 *     000B   rts
 *
 * The `tst/movt/add #-1/neg/cmp/eq #1/bt` chain is the compiler's expansion of
 * `if (b & mask)`, and its priority order matters: 0x40 and 0x20 are tested
 * first (both -> 0x6D), then 0x10/0x08/0x04 (all -> 0x69), then 0x80 (-> 0x68)
 * LAST, then 0.  A byte carrying both 0x40 and 0x80 therefore yields 0x6D —
 * the nested conditional below preserves exactly that priority.
 *
 * CALLING CONVENTION
 * ------------------
 * No arguments, no return value: a register-free side-effect leaf.  Both
 * addresses are hard-coded via PC-relative mov.w loads.  Nothing meaningful is
 * left in r0 (the lift returns void), so the harness drives it with the
 * standard SH2.call() entry and inspects only the written byte.
 *
 * RAM SIDE EFFECT: writes one byte @0xFFFFD2C5 from RAM[0xFFFFCD4C] — the
 * harness compares that byte (the emulator's RAM overlay) against the host's
 * mmap-backed page (same MAP_FIXED trick as tests/host_oracle.c).
 *
 * VERIFYING THE LIFT / DISCREPANCIES
 * ----------------------------------
 * The lift in c/warning_light_0x5AADE.c was checked against the raw ROM bytes
 * (disassembly above) and against tools/sh2emu.py over all 256 status bytes:
 * 0 mismatches, no behavioural discrepancy found.  Two notes on faithful
 * reconstruction:
 *  1. the ROM re-reads RAM[0xFFFFCD4C] once per tst (six loads in total);
 *     the lift reads it once.  This is identical provided the byte does not
 *     change mid-call, which holds here (plain on-chip RAM, no I/O access);
 *  2. the bit order 0x40/0x20 -> 0x6D, 0x10/0x08/0x04 -> 0x69, 0x80 -> 0x68
 *     is confirmed from the branch targets; it is the only correct nesting.
 * =============================================================================
 */
#include <stdint.h>
#include <stddef.h>

#include "rx8_samples.h"

/* Lamp-status / warning-light addresses are not (yet) documented in
 * include/rx8_hw.h; they come from the verified lift c/warning_light_0x5AADE.c
 * (0xCD4C and 0xD2C5 are the 16-bit literals, sign-extended by mov.w). */
#define RX8_LAMP_STATUS_ADDR 0xFFFFCD4Cu  /* lamp status byte (bitmapped)   */
#define RX8_WARNING_LIGHT_ADDR 0xFFFFD2C5u /* warning-light value byte (out) */

/* 0x5AADE — map the lamp-status bits to a warning-light value.
 * 0x40/0x20 -> 0x6D (109), 0x10/0x08/0x04 -> 0x69 (105), 0x80 -> 0x68 (104),
 * else 0.  The 0x80 test comes LAST in the ROM, so it loses to every other
 * lit bit — the nested ?: below matches that priority exactly. */
void rx8_warning_light_5aade(void)
{
    uint8_t b = *(volatile uint8_t *)(uintptr_t)RX8_LAMP_STATUS_ADDR;
    uint8_t v = (b & 0x60) ? 0x6Du : (b & 0x1C) ? 0x69u
                : (b & 0x80) ? 0x68u : 0u;
    *(volatile uint8_t *)(uintptr_t)RX8_WARNING_LIGHT_ADDR = v;
}
