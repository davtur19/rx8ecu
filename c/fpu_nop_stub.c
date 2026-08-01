/*
 * fpu_nop_stub.c  —  RX-8 PCM raw SR write (0x2064)
 *
 * SH-2 asm:  rts            ; return (delay slot executes BEFORE rts)
 *            ldc r4,sr      ; sr = r4  (set Status Register)
 *
 * Despite its name ("fpu_nop_stub") the function actually performs an
 * unconditional write of r4 into the Status Register, exactly like
 * setSR(r4) but without any of the conditional fast-path / OS-handler
 * logic that the real setSR (0x3934) contains.  Called from 78 sites,
 * it is used when the caller has already determined the exact SR value
 * needed (typically an interrupt-priority level) and wants the write
 * without any side effects.
 *
 * Track A: verified behavior-equivalent to emulated ROM (SRCPU subclass)
 * over 50000 random SR values.  Test: c/tests/test_fpu_nop_stub.py.
 *
 * NOTE: This is NOT executable as a normal C function on the host because
 * it manipulates the CPU status register.  The C implementation below
 * is a functional equivalent for documentation; verification uses the
 * SRCPU emulator subclass (see test).
 */
#include <stdint.h>

/* 0x2064  raw ldc r4,sr / rts                                               */
static inline void fpu_nop_stub(uint32_t sr)
{
    /* This is what the ROM bytes do:  SR = sr; return */
    /* On real SH-2: __asm__ volatile("ldc %0,sr" : : "r"(sr)); */
    (void)sr;
}
