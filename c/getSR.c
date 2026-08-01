/*
 * getSR  —  RX-8 PCM raise-IPL-and-return-old @ ROM 0x3920
 *
 * Function name from the hand-annotated Ghidra RE by equinox311 (program 60E1D400).
 * 165 callers — the second most-called leaf in the firmware.
 *
 * NOTE: despite the name "getSR" (which suggests a read-only accessor), this function
 * CONDITIONALLY WRITES SR: it raises the interrupt-priority level (IPL) if the requested
 * value is higher than the current one.  It always returns the old (SR & 0xF0) mask,
 * which callers save and later pass to setSR(0x3934) to restore.
 *
 * Original SH-2 (big-endian):
 *     0x3920: mov.w 0x392e,r5          ; r5 = 0x00F0  (IPL mask, bits 7–4)
 *     0x3922: stc   sr,r0              ; r0 = SR
 *     0x3924: and   r5,r0              ; r0 = SR & 0xF0  (current IPL << 4)
 *     0x3926: cmp/hi r0,r4             ; T  = (r4 > r0) unsigned
 *     0x3928: bf    0x3930             ; if r4 <= r0, skip update (goto rts/nop)
 *     0x392A: rts                      ; return (executed when r4 > r0)
 *     0x392C: ldc   r4,sr              ; delay slot: SR = r4  (raise IPL)
 *     ...
 *     (at 0x3930): rts                 ; return (executed when r4 <= r0)
 *     (at 0x3932): nop                 ; delay slot
 *
 * Semantics:
 *   1. Read current SR and mask out everything but the IPL nibble (bits 7–4).
 *   2. If r4 > (SR & 0xF0)  →  write r4 to SR (raising the IPL), return old mask.
 *   3. If r4 <= (SR & 0xF0) →  leave SR unchanged, return current mask.
 *
 * Callers typically do:
 *     uint32_t old = getSR(0x000000F0);   // raise IPL to max
 *     // ... critical section ...
 *     setSR(old);                          // restore
 *
 * The returned value is always (previous SR & 0x00F0), which is a number in
 * {0x00, 0x10, 0x20, …, 0xF0} representing the interrupt priority level that was
 * active before the call.  This is passed verbatim to setSR(0x3934) to restore.
 *
 * Hardware note: see setSR.c header for SH-2 `ldc` / `stc` details.
 *
 * Track A: verified via tools/sh2emu.py with SR modelled as a plain register —
 * see c/tests/test_setSR_getSR.py.
 */
#include <stdint.h>

/* ------------------------------------------------------------------ */
/*  SR register state — each file owns its own copy (they're tested    */
/*  independently).  On real hardware there is one SR; the C lifts     */
/*  are verified one function at a time against the emulated ROM.      */
/* ------------------------------------------------------------------ */
static uint32_t _sr = 0x000000F0;       /* power-on reset default */

static inline uint32_t read_sr(void) { return _sr; }
static inline void write_sr(uint32_t v) { _sr = v; }


/* ------------------------------------------------------------------ */
/*  getSR — read and conditionally raise IPL, return old mask          */
/* ------------------------------------------------------------------ */
uint32_t getSR(uint32_t requested_sr)
{
    uint32_t old_masked = read_sr() & 0x000000F0u;   /* stc sr,r0 ; and #0xF0,r0 */

    if (requested_sr > old_masked) {
        /* requested IPL > current → raise it */
        write_sr(requested_sr);                      /* ldc r4,sr (delay slot of rts) */
    }
    /* else: leave SR unchanged (bf → rts/nop) */

    return old_masked;                               /* r0 */
}
