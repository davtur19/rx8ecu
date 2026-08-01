/*
 * =============================================================================
 * rx8_set_memory_not_valid2.c  —  BYTE-COPY LEAF ENTERED AT 0x3E5A8 (60E1D400)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x3E5A8
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_set_memory_not_valid2.py
 *               (host-gcc vs tools/sh2emu.py over edge + 20000 random vectors,
 *               0 mismatches; the RAM side effect is compared byte-exactly).
 * Lift (truth): c/SetMemoryNotValid2.c  —  WITH A DOCUMENTED DISCREPANCY (below)
 *
 * !! DISCREPANCY vs THE LIFT — READ FIRST !!
 * c/SetMemoryNotValid2.c claims 0x3E5A8 writes the constant 1 to a fixed
 * fault/memory-invalid flag and defines the flag address as 0xFFFFC63A.  That
 * lift was written against the *60E0FC00* image, where 0x3E5A8 is exactly that
 * leaf (annotated src/60E0FC00_annotated.s: `SetMemoryNotValid2__`):
 *
 *     mov.w @(0x3E6B8,pc),r2    ; r2 = sign-extended word 0xC639 -> 0xFFFFC639
 *     mov    #1,r3
 *     rts
 *     mov.b  r3,@r2             ; (delay slot) flag[0xFFFFC639] = 1
 *
 * In the stock 60E1D400.bin image used by every reconstruction harness the
 * bytes at 0x3E5A8 are entirely different (63 20 A0 0E 25 30 91 65 ...): the
 * address is NOT a function entry there — it is the middle of the IDA-named
 * `status_checker_3E58A` (0x3E58A-0x3E5CE), reached only by `bf/s` fall-in from
 * 0x3E5A4.  Starting the CPU at 0x3E5A8 (as the harness does) executes:
 *
 *     0x3E5A8  mov.b @r2,r3     ; r3 = sign-extend(*src)   (r2 = source ptr)
 *     0x3E5AA  bra   0x3E5CA    ; unconditional -> epilogue
 *     0x3E5AC  mov.b r3,@r5     ; (delay slot) *dst = r3   (r5 = dest ptr)
 *     0x3E5CA  rts
 *     0x3E5CC  nop
 *
 * i.e. a plain BYTE COPY  *dst = *src.  The block 0x3E5AE..0x3E5C8 — the
 * `RAM[0xFFFFC68D] == 1`-guarded, wrapping decrement of *dst — is dead from
 * this entry because of the unconditional `bra 0x3E5CA`, so it is NOT part of
 * the behaviour verified here.  Two further corrections to the lift:
 *   1. even for the 60E0FC00 image the lift's flag constant 0xFFFFC63A is
 *      OFF BY ONE — the pool word at 0x3E6B8 is 0xC639, so the real flag
 *      address is 0xFFFFC639 (c/README.md agrees; docs/SENSOR_PIPELINE.md
 *      repeats the lift's 0xFFFFC63A);
 *   2. the 60E0FC00 `SetMemoryNotValid2` leaf is not present at 0x3E5A8 in
 *      60E1D400.bin at all (byte search: no match for its opcode sequence),
 *      so the lift cannot be bit-verified against this ROM at this address.
 *
 * CALLING CONVENTION (non-ABI leaf, like rx8_div32_signed / interpolate leaves)
 * --------------------------------
 *     in: r2 = pointer to source byte, r5 = pointer to destination byte
 *     out: none — the observable is the RAM write RAM[r5] := RAM[r2]
 * No stack frame, no saved registers, returns via rts.  (In its native caller
 * `status_checker_3E58A` this path is the "copy raw cell byte into the caller's
 * destination" branch; the C below is the entry-visible behaviour.)
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* 0x3E5A8 — byte copy leaf: *dst = *src (ROM r2 = src, r5 = dst; see header
 * for the discrepancy against c/SetMemoryNotValid2.c and the calling
 * convention).  The low 8 bits of the sign-extended load are what the ROM's
 * `mov.b r3,@r5` stores, so the plain unsigned copy below is bit-exact. */
void rx8_set_memory_not_valid2(uint8_t *src, uint8_t *dst)
{
    *dst = *src;
}
