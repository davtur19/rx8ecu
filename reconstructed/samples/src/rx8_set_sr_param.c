/*
 * =============================================================================
 * rx8_set_sr_param.c  —  CONDITIONAL IPL RAISE WITH OLD-VALUE SAVE
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x2054
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_set_sr_param.py (host-gcc
 *               vs tools/sh2emu.py over random (SR, new-SR) pairs + edge
 *               vectors), in addition to the existing c/tests/
 *               test_setSR_getSR.py entry (50k random, 0 errors).
 * Lift (truth): c/setSR_PARAM.c  (same address; hand-annotated Ghidra RE by
 *               equinox311; ROM symbol `setSR_PARAM`).
 *
 * ROLE / CALLERS
 * --------------
 * This is the "raise IPL, saving the old value" entry point of the firmware's
 * interrupt-masking critical-section layer — 68 call sites, making it the
 * third SR accessor next to getSR @0x3920 and setSR @0x3934.  A caller stores
 * the old masked IPL through the pointer in r4, then hands the desired new SR
 * value in r5; the saved word is what the matching critical-section exit uses
 * to restore the previous IPL level.
 *
 * ROM SEMANTICS (SH-2, big-endian)
 * --------------------------------
 *     stc    sr,r0        r0 = SR
 *     and    #240,r0      r0 = SR & 0xF0            (IPL nibble, bits 7..4)
 *     cmp/hs r0,r5        T  = (r5 >= r0) unsigned
 *     bt/s   0x2060       if T, skip the clamp      (delay slot always runs)
 *       mov.l r0,@r4      *r4 = old masked IPL      (delay slot of bt/s)
 *     mov    r0,r5        clamp: r5 = old masked IPL (only when T == 0)
 *     rts
 *       ldc   r5,sr       SR = r5                   (delay slot of rts)
 *
 * Behavioural summary:
 *   1. old_masked = SR & 0xF0 — the IPL nibble only; the T/S/Q/M low bits are
 *      masked off and play no part.
 *   2. *store is ALWAYS written with old_masked: the bt/s delay slot fires on
 *      both the taken and the fall-through path.
 *   3. if new_sr >= old_masked (unsigned)  ->  SR = new_sr   (raise or keep).
 *   4. if new_sr <  old_masked (unsigned)  ->  SR = old_masked.  The SH-2
 *      hardware already prevents lowering the IPL below the current level via
 *      `ldc` in user mode; the ROM still clamps in software (belt-and-
 *      suspenders, preserved verbatim).
 *   5. r0 carries old_masked out in every case, which this function returns.
 *
 * The SR is modelled as module-level register state with explicit accessors
 * (`rx8_sr_read` / `rx8_sr_write`) standing in for `stc sr,Rn` / `ldc Rn,sr`,
 * power-on value 0x000000F0 (IPL=15, MD=1, BL=1, RB=1) as on the SH-2E core.
 * No interrupt model: SR is a plain uint32 and the firmware runs privileged,
 * so the hardware IPL-lowering restriction is intentionally not simulated —
 * matching the verified lift and the emulator it was verified against.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* Interrupt-priority level: SR bits 7..4 (ROM literal 240 == 0xF0). */
#define RX8_SR_IPL_MASK          0x000000F0u

/* SH-2 power-on reset default for SR: IPL=15, MD=1, BL=1, RB=1. */
#define RX8_SR_POWERON_DEFAULT   0x000000F0u

/* Current SR state — the C stand-in for the `stc`/`ldc` register access. */
static uint32_t _rx8_sr = RX8_SR_POWERON_DEFAULT;

uint32_t rx8_sr_read(void)
{
    return _rx8_sr;
}

void rx8_sr_write(uint32_t value)
{
    _rx8_sr = value;
}

uint32_t rx8_set_sr_param(uint32_t *store, uint32_t new_sr)
{
    /* stc sr,r0 ; and #240,r0 — current IPL nibble. */
    uint32_t old_masked = rx8_sr_read() & RX8_SR_IPL_MASK;

    /* mov.l r0,@r4 — delay slot of the bt/s: executes on BOTH paths. */
    *store = old_masked;

    /* cmp/hs r0,r5 ; mov r0,r5 — never lower the IPL below the current level. */
    if (new_sr < old_masked) {
        new_sr = old_masked;
    }

    /* ldc r5,sr — delay slot of the rts. */
    rx8_sr_write(new_sr);

    /* r0 still holds old_masked when the caller regains control. */
    return old_masked;
}
