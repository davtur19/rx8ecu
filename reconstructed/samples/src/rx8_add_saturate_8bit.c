/*
 * =============================================================================
 * rx8_add_saturate_8bit.c  —  SATURATING UNSIGNED 8-BIT ADD
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x2478
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_add_saturate_8bit.py
 *               (host-gcc vs tools/sh2emu.py over edge vectors + 20000 random
 *               u8 pairs; 0 mismatches).
 * Lift (truth): c/addSaturate8Bit.c  (same address; function name from the
 *               hand-annotated Ghidra RE by equinox311, program 60E0FC00 —
 *               byte-identical helper across the N3J1 family, matched into
 *               60E1D400 by content signature).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The SH-2E core has no automatic saturating arithmetic, and Denso's scalar
 * math cluster reaches for this tiny helper wherever an unsigned 8-bit
 * accumulator must never wrap (brightness / duty-ramp style counters).  The
 * ROM path, from tools/disasm_sh2e.py, is a pure register-only leaf:
 *
 *     0x2478: extu.b r4,r4          ; add1 = (uint8)add1   (input mask)
 *     0x247A: extu.b r5,r5          ; add2 = (uint8)add2   (input mask)
 *     0x247C: add    r5,r4          ; r4 = add1 + add2            (0..510)
 *     0x247E: extu.w r4,r3          ; r3 = r4
 *     0x2480: mov.w  @(pc),r5       ; r5 = 255   (literal @0x248E = 0x00FF)
 *     0x2482: cmp/ge r5,r3          ; T  = (r3 >= 255)   (signed; r3 >= 0
 *                                    ;                  always, so signed ==
 *                                    ;                  unsigned here)
 *     0x2484: bf/s   0x248A         ; !T (sum < 255) -> return the raw sum
 *     0x2486: nop
 *     0x2488: mov    r5,r4          ; T  (sum >= 255) -> clamp to 255
 *     0x248A: rts
 *     0x248C: mov    r4,r0          ;   (delay slot) r0 = result
 *
 * Semantics: min(add1 + add2, 255) — a plain unsigned 8-bit saturating add.
 * Both inputs are re-truncated to 8 bits by `extu.b`, so any caller-side
 * garbage in the register high bits is irrelevant.
 *
 * CALLING CONVENTION (SH-2E, register-only leaf)
 *   in  r4 = add1 (u8, extu.b-masked), r5 = add2 (u8, extu.b-masked)
 *   out r0 = result (u8)
 * No RAM side-effects, no stack frame, no callee-saved register traffic.
 * SH2.call() seeds exactly r4/r5 and returns r0, so the harness invokes the
 * leaf with the plain `cpu.call(0x2478, r4=.., r5=..)` — no call_leaf driver
 * needed (cf. harness_add_s32.py, which does the same for addS32Saturate).
 *
 * LIFT-vs-ROM DISCREPANCIES FIXED
 *   None.  The lift in c/addSaturate8Bit.c was verified byte-for-byte against
 *   the disassembly before this sample was written, and the emulator smoke
 *   tests (0+0=0, 255+0=255, 254+1=255, 128+128=255, 255+255=255) all agree.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* 0x2478 — saturating unsigned 8-bit add:  min(add1 + add2, 255).
 * Computed in `unsigned` so the intermediate never overflows int and the
 * single clamp reproduces the ROM's `cmp/ge #255` decision exactly. */
uint8_t rx8_add_saturate_8bit(uint8_t add1, uint8_t add2)
{
    unsigned sum = (unsigned)add1 + (unsigned)add2;   /* 0..510 */
    return sum >= 255u ? (uint8_t)255u : (uint8_t)sum;
}
