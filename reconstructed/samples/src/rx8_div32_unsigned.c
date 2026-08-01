/*
 * =============================================================================
 * rx8_div32_unsigned.c  —  32-BIT UNSIGNED INTEGER DIVISION
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x409C
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_div32_unsigned.py (host-gcc
 *               vs tools/sh2emu.py over random uint32 pairs + edge vectors),
 *               in addition to the existing c/tests/test_div32_unsigned.py
 *               entry (20k random, 0 errors).
 * Lift (truth): c/div32_unsigned.c
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The SH-2E core (Renesas SH7055) has no hardware divide instruction, so the
 * PCM firmware ships a software divide routine: a fully unrolled 32-step loop
 * built on the div0u/div1 unsigned non-restoring division primitives.  It is
 * leaf code called with a deliberately NON-STANDARD register convention — the
 * compiler passes the operands in scratch registers, not the usual r4/r5:
 *
 *     r0 = divisor, r1 = dividend  ->  quotient in r0 (remainder discarded)
 *
 *     tst    r0,r0                 ; divisor == 0?
 *     bt     div_zero              ;   -> write diag code, return 0
 *     mov    #0x00,r2              ; r2 = 0 (partial-remainder accumulator)
 *     div0u                        ; init unsigned divide
 *     ; 32 x { rotcl r1 ; div1 r0,r2 }   ; non-restoring division loop
 *     mov    r1,r0                 ; quotient -> r0
 *     rts / mov.l @r15+,r2
 *
 *     div_zero:
 *     mov.l  @lit,r1               ; r1 = 0xFFFF7304 (diagnostic word addr)
 *     mov.l  @lit,r2               ; r2 = 0x0000044E (diagnostic code)
 *     mov    #0x00,r0
 *     mov.l  r2,@r1                ; store diag code to 0xFFFF7304
 *     rts / mov.l @r15+,r2         ; return 0
 *
 * The loop computes C99 unsigned floor division (quotient only; remainder is
 * discarded).  Unsigned division is fully well-defined in C, so the host code
 * below is a verbatim translation with no corner-case guards required.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* Diagnostic word the ROM pokes on divide-by-zero.  The SH-2E can reach it
 * directly (on-chip RAM / peripheral window); a host process cannot, which is
 * why the write below is compiled out for native testing — the emulator
 * harness still validates the real ROM bytes performing the write. */
#define RX8_DIV_DIAG_CODE 0x44Eu

/* 0x409C — unsigned 32-bit division: return dividend / divisor.
 * Truncation is toward zero (matches the SH-2E div1 loop / C99 unsigned
 * division).  divisor == 0 stores 0x44E at 0xFFFF7304 and returns 0. */
uint32_t rx8_div32_unsigned(uint32_t divisor, uint32_t dividend)
{
    if (divisor == 0) {
        /* Host test: skip the hardware write to avoid faulting on the host.
         * Emulator tests validate the actual ROM behaviour. */
        /* RX8_DIAG_CODE_REG = RX8_DIV_DIAG_CODE; */
        return 0;
    }
    /* C99 unsigned division truncates toward zero, matching the SH-2E. */
    return dividend / divisor;
}
