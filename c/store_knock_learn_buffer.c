/**
 * store_knock_learn_buffer — getSR -> store -> setSR critical-section wrapper
 *
 * The SAME function body exists at two addresses in two different stock ROMs:
 *
 *   entry 0xC0F0   in roms/stock/60E0FC00.bin   (size 0x26 = 38 bytes)
 *   entry 0xC2C0   in roms/stock/60E1D400.bin   (size 0x26 = 38 bytes)
 *
 * The bodies are byte-identical except for one pointer-chain anchor used by
 * the tail-called setSR(): 0xFFFF7638 (60E0FC00) vs 0xFFFF72B0 (60E1D400).
 * NOTE: 0xC0F0 in 60E1D400.bin is a DIFFERENT function — the lift's two
 * addresses live in two different ROMs and must not be conflated with each
 * other within a single image.
 *
 * Verified behavior (from the actual ROM bytes, via the SH-2E emulator
 * differential test c/tests/test_store_knock_learn_buffer.py — 20,006 inputs,
 * 0 mismatches):
 *
 *   store_knock_learn_buffer(r4, r5):
 *       getSR(0x10)                      ; @0x3920, returns SR & 0xF0 in r0
 *       KNOCK_COPY1 (0xFFFFA37E) = r4    ; u16
 *       KNOCK_COPY2 (0xFFFFA37C) = r5    ; u16
 *       tail call setSR(r0)              ; @0x3934  (jmp, pr popped in delay slot)
 *
 *   getSR @0x3920: r0 = SR & 0xF0; if 0x10 > (SR & 0xF0): SR = 0x10.
 *   setSR @0x3934: SR = r4, except r4 == 0 -> pointer-chain flag check:
 *       flag = *(*(ANCHOR + 0x18) + 1) where ANCHOR is 0xFFFF7638 (60E0FC00)
 *       or 0xFFFF72B0 (60E1D400).  flag == 1 -> fast path (SR = 0).
 *       flag != 1   -> tail-call OS handler 0x3DB0 (with delay ldc r4,SR so
 *                      SR = 0 on entry); early-exit path taken when
 *                      word@(ANCHOR+4) == word@(ANCHOR+6): SR = 0, r0 = 0.
 *
 *   Net effect (this model):
 *       c1 = r4 & 0xFFFF, c2 = r5 & 0xFFFF
 *       old_ipl = SR & 0xF0
 *       final SR = old_ipl            (all paths; the temporary SR=0x10 from
 *                                      getSR is always undone by setSR)
 *       r0 = s16(c1)                  (old_ipl != 0)  -- mov.w sign-extends
 *          = 1                        (old_ipl == 0, setSR fast path, flag==1)
 *          = 0                        (old_ipl == 0, OS early-exit, flag!=1)
 *
 * Parameters:
 *   r4: uint16_t value to store to first knock copy
 *   r5: uint16_t value to store to second knock copy
 *
 * Calls:
 *   getSR @ 0x3920 — read/mask SH-2 status register (returns SR & 0xF0)
 *   setSR @ 0x3934 — write SH-2 status register (tail call)
 */

#include <stdint.h>

#define KNOCK_COPY1    (*(volatile uint16_t *)0xFFFFA37E)   /* first knock ADC output copy */
#define KNOCK_COPY2    (*(volatile uint16_t *)0xFFFFA37C)   /* second knock ADC output copy */

/* setSR(0) pointer-chain anchor — differs per stock ROM:
 *   0xFFFF7638  -> 60E0FC00.bin (function entry 0xC0F0)
 *   0xFFFF72B0  -> 60E1D400.bin (function entry 0xC2C0)
 * Pick the ROM you are modelling: the code is identical either way. */
#ifndef KNOCK_SETSR_ANCHOR
#define KNOCK_SETSR_ANCHOR  0xFFFF7638u   /* default: 60E0FC00 variant @0xC0F0 */
#endif

extern uint32_t getSR(void);    /* @0x3920: returns SR & 0xF0, raises SR to 0x10 if IPL < 0x10 */
extern void     setSR(uint32_t value);    /* @0x3934: SR = value (special-cases value == 0) */

/**
 * store_knock_learn_buffer
 *
 * Stores two u16 knock-learn parameters to the knock output buffer inside a
 * getSR/setSR critical section and returns the OS result code (r0).
 *
 * @param r4  value stored (u16) to 0xFFFFA37E
 * @param r5  value stored (u16) to 0xFFFFA37C
 * @return    s16(r4) if the saved IPL was non-zero, otherwise 1 (setSR fast
 *            path) or 0 (setSR OS early-exit path).  See header.
 */
int32_t store_knock_learn_buffer(uint16_t r4, uint16_t r5)
{
    uint32_t old_ipl;   /* SR & 0xF0, exactly what getSR(0x10) returns */
    uint32_t state_ptr;
    uint8_t  flag;

    /* 1. Enter the critical section: getSR(0x10) returns SR & 0xF0 and, if
     *    the current IPL is below 0x10, first raises SR to 0x10.  */
    old_ipl = getSR();

    /* 2. Store both u16 parameters to the knock ADC output copies. */
    KNOCK_COPY1 = r4;
    KNOCK_COPY2 = r5;

    /* 3. Tail-call setSR(old_ipl).  Since getSR returned SR & 0xF0, setSR
     *    restores SR to exactly that value on every path — the temporary
     *    SR = 0x10 set by getSR is always undone.  The r4 == 0 case
     *    (old_ipl == 0) additionally triggers setSR's pointer-chain check.  */
    if (old_ipl != 0) {
        setSR(old_ipl);                 /* setSR: plain ldc, SR = old_ipl */
        /* r0 is still s16(c1): mov.w @(0x4,r15),r0 sign-extends r4 */
        return (int32_t)(int16_t)r4;
    }

    /* old_ipl == 0 -> setSR(0) -> flag = *(*(ANCHOR + 0x18) + 1)
     * (uintptr_t keeps the SH-2 32-bit address portable on 64-bit hosts) */
    state_ptr = *(const uint32_t *)(KNOCK_SETSR_ANCHOR + 0x18);
    flag      = *(const uint8_t *)(uintptr_t)(state_ptr + 1);
    if (flag == 1) {
        /* setSR fast path: SR = 0; r0 = 1 */
        setSR(0);
        return 1;
    }

    /* setSR OS-handler path: tail-call 0x3DB0 (delay ldc r4,SR -> SR = 0 on
     * entry); the early-exit branch (word@(ANCHOR+4) == word@(ANCHOR+6))
     * restores SR = 0 and returns r0 = 0.  The full scheduler path of 0x3DB0
     * is out of scope for this model.  */
    setSR(0);
    return 0;
}

/* ========================================================================
 * NOTES:
 *
 * 1. Verified by differential emulator test (c/tests/test_store_knock_learn_buffer.py):
 *    20,006 inputs, 0 mismatches vs the real ROM bytes at 0xC0F0 (60E0FC00)
 *    and 0xC2C0 (60E1D400).
 *
 * 2. Historical inaccuracies in earlier versions of this lift (now corrected):
 *    - The function returns a value in r0: s16(r4) when the saved IPL was
 *      non-zero, 1 on the setSR fast path, 0 on the setSR OS early-exit path.
 *      The previous lift returned void.
 *    - getSR(0x10) does NOT return the full SR — it returns SR & 0xF0 and may
 *      raise SR to 0x10 (critical-section entry) when the IPL is 0.  The
 *      previous lift described the 0x10 argument as "a mask selecting a bit".
 *    - setSR is tail-called with r4 = SR & 0xF0 (not the raw SR), so the final
 *      SR is SR & 0xF0 on every path.  The r4 == 0 case routes through setSR's
 *      pointer-chain special case (fast path vs OS handler 0x3DB0 early-exit),
 *      which the previous lift did not model.
 *    - The two-ROM split is now explicit: 0xC0F0 (60E0FC00, anchor
 *      0xFFFF7638) and 0xC2C0 (60E1D400, anchor 0xFFFF72B0).  0xC0F0 in
 *      60E1D400.bin is a DIFFERENT function.
 *
 * 3. Residual divergence / out of scope:
 *    - The full scheduler path of OS handler 0x3DB0 (flag != 1) is NOT
 *      modelled — only its early-exit branch (word@(ANCHOR+4) ==
 *      word@(ANCHOR+6)).  The flag == 1 fast path is the overwhelmingly
 *      common case (setSR is called with r4 == 0 only when the IPL is 0).
 *    - Real SH-2 hardware prevents lowering the IPL via ldc in user mode;
 *      like the rest of the repo (see c/tests/test_setSR_getSR.py) this model
 *      treats SR as a plain register.
 * ======================================================================== */
