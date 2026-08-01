/*
 * setSR_PARAM  —  RX-8 PCM conditional IPL raise w/ old-value store @ ROM 0x2054
 *
 * Function name from the hand-annotated Ghidra RE by equinox311 (program 60E1D400).
 * 68 callers — this is the third SR accessor, used in contexts that need to keep the
 * old masked IPL value for later restoration (e.g. saving to a stack frame).
 *
 * Original SH-2 (big-endian):
 *     0x2054: stc   sr,r0              ; r0 = SR
 *     0x2056: and   #240,r0            ; r0 = SR & 0xF0  (240 = 0xF0; extract IPL)
 *     0x2058: cmp/hs r0,r5             ; T  = (r5 >= r0) unsigned
 *     0x205A: bt/s  0x2060             ; if r5 >= r0, jump to return (delay: *r4 = r0)
 *     0x205C: mov.l r0,@r4             ; (bt/s delay slot — ALWAYS executed) *r4 = old IPL
 *     0x205E: mov   r0,r5              ; r5 = r0  (override new_sr with old value)
 *     0x2060: rts                      ; return
 *     0x2062: ldc   r5,sr              ; delay slot: SR = r5
 *
 * Semantics:
 *   1. Read SR, mask to bits 7–4 (the IPL nibble).
 *   2. ALWAYS store the old masked value to *r4 (the bt/s delay-slot always fires).
 *   3. If new_sr (r5) >= old_masked  →  write new_sr to SR (raise or keep IPL).
 *   4. If new_sr (r5) <  old_masked  →  override r5 with old_masked and write that
 *      back (IPL unchanged — hardware can only raise, not lower, via ldc in general,
 *      so this is a belt-and-suspenders software guard).
 *
 * This is the canonical "raise IPL with save" entry point — it combines getSR's
 * conditional-raise logic with automatic saving of the prior value.  The caller
 * supplies a pointer *r4 where the old masked IPL is stored, and the desired new
 * IPL-or-SR value in r5.
 *
 * Hardware note: see setSR.c header for SH-2 `ldc` / `stc` details.
 *
 * Track A: verified via tools/sh2emu.py with SR modelled as a plain register —
 * see c/tests/test_setSR_getSR.py.
 */
#include <stdint.h>

/* ------------------------------------------------------------------ */
/*  SR register state — self-contained copy for independent testing.   */
/* ------------------------------------------------------------------ */
static uint32_t _sr = 0x000000F0;       /* power-on reset default */

static inline uint32_t read_sr(void) { return _sr; }
static inline void write_sr(uint32_t v) { _sr = v; }


/* ------------------------------------------------------------------ */
/*  setSR_PARAM — conditional IPL raise, storing the old mask          */
/* ------------------------------------------------------------------ */
void setSR_PARAM(uint32_t *store, uint32_t new_sr)
{
    uint32_t old_masked = read_sr() & 0x000000F0u;   /* stc sr,r0 ; and #240,r0 */

    *store = old_masked;                             /* mov.l r0,@r4 (delay slot) */

    if (new_sr < old_masked) {
        new_sr = old_masked;                         /* mov r0,r5 — can't lower IPL */
    }

    write_sr(new_sr);                                /* ldc r5,sr (delay slot of rts) */
}
