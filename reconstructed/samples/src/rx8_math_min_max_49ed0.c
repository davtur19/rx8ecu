/*
 * =============================================================================
 * rx8_math_min_max_49ed0.c  —  "MATH_MIN_MAX" FLAG-SETTER LEAF (0x49ED0)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x49ED0
 * Size        : 34 bytes (0x49ED0 .. 0x49EF1; 4 literal words at 0x49EF2+)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_math_min_max_49ed0.py
 *               (host-gcc vs tools/sh2emu.py over random + edge vectors,
 *               0 mismatches; return value AND both RAM side-effect bytes
 *               compared byte-exactly).
 * Lift (truth): c/math_min_max_49ED0.c  (verified in c/tests on the same ROM)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Despite the "math_min_max" symbol, this is a pure FLAG SETTER.  It reads a
 * fixed 16-bit RAM word at 0xFFFFF76C, tests bit 0x100, and stores the same
 * 0/1 flag byte to TWO separate flag bytes at 0xFFFFCD48 and 0xFFFFCD49
 * (the word at 0xFFFFF76C is left untouched).  Disassembly of 60E1D400.bin:
 *
 *     mov.w 0x49EF2,r6   ; r6 = 0xFFFFCD49   (output B; mov.w @(disp,PC)
 *     mov.w 0x49EF4,r5   ; r5 = 0xFFFFCD48     SIGN-EXTENDS the literal:
 *     mov.w 0x49EF6,r3   ; r3 = 0xFFFFF76C     disasm prints 0xCD49/0xCD48/
 *     mov.w @r3,r0       ; r0 = word@0xFFFFF76C   0xF76C, the real addresses
 *     extu.w r0,r0       ; r0 &= 0xFFFF            are 0xFFFFxxxx)
 *     mov.w 0x49EF8,r2   ; r2 = 0x00000100
 *     and   r2,r0        ; r0 &= 0x100
 *     tst   r0,r0        ; T = (bit clear)
 *     movt  r0           ; r0 = 1 if clear, else 0
 *     xor   #0x01,r0     ; r0 ^= 1   -> 0 if clear, 1 if set
 *     cmp/eq #0x01,r0    ; T = (bit set)
 *     movt  r0           ; r0 = flag
 *     cmp/eq #0x01,r0    ; T = (flag)
 *     movt  r4           ; r4 = flag
 *     mov.b r4,@r5       ; byte@0xFFFFCD48 = flag
 *     rts
 *     mov.b r4,@r6       ;  (delay) byte@0xFFFFCD49 = flag
 *
 * Semantics (verbatim from c/math_min_max_49ED0.c):
 *   v = (word16@0xFFFFF76C & 0x0100) ? 1 : 0;
 *   byte@0xFFFFCD48 = v; byte@0xFFFFCD49 = v;  return v.
 *
 * CALLING CONVENTION
 * ------------------
 * Non-ABI leaf: takes NO register arguments (the input address is a literal,
 * so r4-r7 are never read on entry) and returns the flag in r0.  It reads one
 * RAM word and writes two RAM bytes — real side effects the harness mirrors
 * byte-exactly on the host (pages 0xFFFFC000 / 0xFFFFF000 mmap'd MAP_FIXED,
 * same trick as tests/host_oracle.c).  No FPU, no stack, no delay hazards.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"

/* 0x49ED0 — set both flag bytes from input word bit 0x100; return the flag. */
uint32_t rx8_math_min_max_49ed0(void)
{
    uint32_t v = (RX8_MATH_FLAG_INPUT & 0x0100) ? 1 : 0;
    RX8_MATH_FLAG_OUT_A = (uint8_t)v;
    RX8_MATH_FLAG_OUT_B = (uint8_t)v;
    return v;
}
