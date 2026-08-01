/*
 * =============================================================================
 * rx8_fpu_nop_stub.c  —  RAW SR WRITE  (0x2064)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x2064
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_fpu_nop_stub.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge SR
 *               values; the resulting SR register compared bit-exactly).
 * Lift (truth): c/fpu_nop_stub.c  (verified there over 50000 random SR values
 *               via the SRCPU emulator subclass, c/tests/test_fpu_nop_stub.py)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Despite the "fpu_nop_stub" name (an IDA auto-label; there is no FPU and no
 * NOP here) the function is an unconditional write of r4 into the Status
 * Register, byte-for-byte:
 *
 *     0x2064  000B   rts             ; return (delay slot runs FIRST)
 *     0x2066  440E   ldc r4,sr       ; SR = r4  (full 32-bit write)
 *
 * i.e. exactly `setSR(r4)` minus the conditional fast-path / OS-handler logic
 * that the real setSR (0x3934) contains.  Called from 78 sites, it is used
 * whenever a caller has already computed the exact SR value it wants (most
 * commonly a saved interrupt-priority level restored at the end of a
 * critical section that was opened with getSR/setSR_PARAM @0x2054) and needs
 * the write with no side effects.
 *
 * CALLING CONVENTION
 * ------------------
 * SH-2 ABI entry: r4 = new SR value.  There is no register return value — the
 * whole effect is on the CPU Status Register.  On real silicon the delay-slot
 * `ldc r4,sr` runs before the `rts` returns, so the caller resumes with SR
 * already updated.
 *
 * HOST MODEL
 * ----------
 * A host process has no CPU status register to write, so the C implementation
 * below is the natural functional equivalent: the function takes the value to
 * be loaded into SR and returns the resulting SR.  The emulator's `ldc Rn,SR`
 * (tools/sh2emu.py) is a raw full-width store — every one of the 32 bits of
 * r4 lands in SR with no masking of "reserved" bits — so the map is exactly
 * the identity over uint32_t.  (The setSR_PARAM pair @0x2054 normally only
 * hands it the saved SR & 0xF0, but the ROM write itself is unconditional.)
 * =============================================================================
 */
#include <stdint.h>

/* 0x2064  rts; ldc r4,sr  —  raw SR write, no conditionals, no side effects.
 *
 * On the SH-2E target this is exactly:
 *     __asm__ volatile("ldc %0,sr" : : "r"(sr));
 * On the host we model the write as the pure function  sr -> new_sr. */
uint32_t rx8_fpu_nop_stub(uint32_t sr)
{
    return sr;
}
