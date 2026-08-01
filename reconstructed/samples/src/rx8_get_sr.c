/*
 * =============================================================================
 * rx8_get_sr.c  —  RAISE IPL AND RETURN OLD STATUS-REGISTER MASK
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x3920
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_get_sr.py (host-gcc vs
 *               tools/sh2emu.py over random SR/request pairs), in addition
 *               to the existing emulator test c/tests/test_setSR_getSR.py
 *               (50k random inputs, 0 errors).
 * Lift (truth): c/getSR.c  (same address; the hand-annotated Ghidra RE by
 *               equinox311 names this leaf `getSR`).
 *
 * WHAT THIS IS
 * ------------
 * Despite the accessor-like name, this is NOT a read-only read of the SH-2
 * status register: it CONDITIONALLY WRITES SR.  The firmware uses it as the
 * entry half of its interrupt-masking critical-section layer:
 *
 *     uint32_t old = rx8_get_sr(0x000000F0);   // raise IPL to max
 *     // ... critical section ...
 *     rx8_set_sr(old);                          // 0x3934 - restore
 *
 * The ROM sequence (big-endian SH-2):
 *
 *     0x3920: mov.w @lit,r5        ; r5 = 0x00F0   (IPL mask, SR bits 7-4)
 *     0x3922: stc   sr,r0          ; r0 = SR
 *     0x3924: and   r5,r0          ; r0 = SR & 0xF0 (current IPL << 4)
 *     0x3926: cmp/hi r0,r4         ; T  = (r4 > r0) unsigned
 *     0x3928: bf    0x3930         ; r4 <= r0 -> leave SR untouched
 *     0x392A: rts                  ; r4 >  r0 -> return, and in the delay
 *     0x392C: ldc   r4,sr          ;   slot write SR = r4 (raise IPL)
 *     0x3930: rts                  ; r4 <= r0 path
 *     0x3932: nop                  ;   (delay slot)
 *
 * SEMANTICS
 * ---------
 *   1. Mask the current SR down to the IPL nibble (bits 7-4): old = SR & 0xF0.
 *   2. If requested > old -> SR = requested (raising the interrupt priority
 *      level; the full requested value is stored, exactly like `ldc r4,sr`).
 *   3. Otherwise leave SR unchanged.
 *   4. Always return `old`, a value in {0x00, 0x10, ..., 0xF0} — the level
 *      that was active before the call.  Callers hand it verbatim to setSR
 *      (0x3934) to restore, so the mask is the observable contract.
 *
 * Hardware note: the SH-2 SR is a CPU register; on the target these stc/ldc
 * are real instructions.  The model below keeps a plain uint32 SR so the
 * logic can be checked one function at a time (same arrangement as the lift,
 * c/getSR.c).  No interrupt model: low SR bits are stored verbatim.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* ---------------------------------------------------------------------------
 * SR register model — power-on reset default for the SH-2 core:
 * IPL = 15 (0xF0), MD = 1, BL = 1, RB = 1  ->  0x000000F0.
 * On real hardware there is exactly one SR; the reconstructed sources are
 * verified one leaf at a time, so each keeps its own copy.
 * ------------------------------------------------------------------------- */
static uint32_t _sr = 0x000000F0u;

/* Test-support accessors (host harness only): the equivalence harness seeds
 * the SR state before every vector, mirroring the emulator's `sr=` argument
 * to cpu.call().  These are NOT part of the firmware contract. */
void rx8_sr_set_state(uint32_t sr) { _sr = sr; }
uint32_t rx8_sr_get_state(void) { return _sr; }

/* ---------------------------------------------------------------------------
 * rx8_get_sr — mask current SR, raise IPL if requested is higher, return old.
 * ------------------------------------------------------------------------- */
uint32_t rx8_get_sr(uint32_t requested_sr)
{
    uint32_t old_masked = _sr & 0x000000F0u;   /* stc sr,r0 ; and #0xF0,r0 */

    if (requested_sr > old_masked) {
        /* Requested IPL > current -> raise it (ldc r4,sr, the delay slot of
         * the rts).  The whole requested value lands in SR, low bits and all,
         * exactly as the ROM's `ldc` stores r4. */
        _sr = requested_sr;
    }
    /* else: leave SR unchanged (bf -> rts/nop at 0x3930). */

    return old_masked;                         /* r0 */
}
