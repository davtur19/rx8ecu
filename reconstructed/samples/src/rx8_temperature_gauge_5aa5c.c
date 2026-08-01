/*
 * =============================================================================
 * rx8_temperature_gauge_5aa5c.c  —  TEMPERATURE GAUGE VALUE SETTER (LEAF)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x5AA5C  (130 bytes, to 0x5AADE)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_temperature_gauge_5aa5c.py
 *               (host-gcc vs tools/sh2emu.py over edge + random vectors,
 *               comparing the side-effected gauge byte; 0 mismatches).
 *               The lift was ALSO exhaustively checked on the emulator for
 *               ALL 256 possible status-byte values before the harness ran.
 * Lift (truth): c/temperature_gauge_0x5AA5C.c  (address 0x5AA5C)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A side-effect-only gauge-value setter leaf: it reads the temperature status
 * byte at RAM[0xFFFFCD4C] and writes a gauge value byte to RAM[0xFFFFD2C4]:
 *
 *   b = byte@0xFFFFCD4C
 *   v = (b & 0x7C) ? 7 : (b & 0x80) ? 6 : 0      // 0x7C = 0x40|0x20|0x10|0x08|0x04
 *   byte@0xFFFFD2C4 = v
 *
 * So any of the five bits 0x40..0x04 forces the gauge to its max code 7;
 * otherwise bit 0x80 alone forces code 6; otherwise the gauge is 0.
 * This mirrors the warning-light function right after it (0x5AADE), which
 * tests the same status byte with the same pattern.
 *
 * Disassembly of 60E1D400.bin @ 0x5AA5C (from src/60E1D400_annotated.s):
 *
 *     9583   mov.w @(0x10,PC),r5   ; r5 = 0xFFFFD2C4 (gauge value byte)
 *     9483   mov.w @(0x10,PC),r4   ; r4 = 0xFFFFCD4C (temperature status byte)
 *     6043   mov r4,r0
 *     6000   mov.b @r0,r0          ; r0 = sign-extended status byte
 *     C840   tst #64,r0            ; T = ((b & 0x40) == 0)
 *     0029   movt r0               ; r0 = T
 *     70FF   add #-1,r0            ; r0 = T - 1
 *     600B   neg r0,r0             ; r0 = 1 if bit set, else 0
 *     8801   cmp/eq #1,r0          ; T = (bit set)
 *     8D24   bt/s 0x5AABA          ; bit 0x40 set -> the r2=7 path
 *     0009   nop
 *     ...    (identical 8-word block for 0x20, 0x10, 0x08)
 *     C804   tst #4,r0             ; ... and for 0x04
 *     ...     movt/add#-1/neg/cmp/eq ...
 *     8F02   bf/s 0x5AABE          ; bit 0x04 clear -> test bit 0x80 instead
 *     0009   nop
 * 0x5AABA:  A00A   bra 0x5AAD2     ; (only reached when a 0x40..0x04 bit set)
 * 0x5AABC:  E207   mov #7,r2       ;   (delay) r2 = 7
 * 0x5AABE:  6043   mov r4,r0
 * 0x5AAC0:  6000   mov.b @r0,r0    ; re-read the status byte
 * 0x5AAC2:  C880   tst #128,r0     ; bit 0x80 test, same pattern
 *     ...
 * 0x5AACC:  8F03   bf/s 0x5AAD6    ; bit 0x80 clear -> the v=0 path
 * 0x5AACE:  0009   nop
 * 0x5AAD0:  E206   mov #6,r2       ; r2 = 6
 * 0x5AAD2:  A002   bra 0x5AADA
 * 0x5AAD4:  2520   mov.b r2,@r5    ;   (delay) byte@0xFFFFD2C4 = r2
 * 0x5AAD6:  E100   mov #0,r1       ; v = 0 path
 * 0x5AAD8:  2510   mov.b r1,@r5    ; byte@0xFFFFD2C4 = 0
 * 0x5AADA:  000B   rts
 * 0x5AADC:  0009   nop
 *
 * The 8-word `tst/movt/add #-1/neg/cmp-eq/branch` block is the compiler's
 * idiom for `if (b & imm) goto ...` (the lift documents it identically).
 * The gauge write happens exactly once on every path (r2 on the 7/6 paths,
 * r1 on the 0 path), so a single store at the end is a faithful collapse.
 *
 * NOTE (discrepancy vs the lift's header comment): the lift states the return
 * r0 is "the last-loaded input byte (sign-extended), not meaningful".  In the
 * ROM the final r0 is actually the 0/1 outcome of the last
 * `movt/add#-1/neg/cmp-eq` block, not the sign-extended input byte: on the
 * v=7 and v=6 paths r0 == 1, on the v=0 path r0 == 0 (verified in the
 * emulator).  The register is caller-don't-care, so the lift's void signature
 * is kept.
 *
 * RAM SIDE EFFECT: writes one byte @0xFFFFD2C4 — the harness compares that
 * byte (the emulator's RAM overlay) against the host's mmap-backed page.
 * The status byte @0xFFFFCD4C is RE-READ up to six times by the ROM (once
 * per bit test); the harness seeds it once before the call and the function
 * writes a different address, so the single volatile read below is
 * behaviourally identical under the test.  (A hardware status register that
 * changed mid-call could in principle be sampled differently, but both
 * addresses are plain on-chip RAM.)
 * =============================================================================
 */
#include <stdint.h>
#include <stddef.h>

#include "rx8_samples.h"

/* Status/gauge addresses are not documented in include/rx8_hw.h; they come
 * from the verified lift c/temperature_gauge_0x5AA5C.c.  The ROM loads them
 * via `mov.w @(disp,PC)` which SIGN-EXTENDS the 0xD2C4/0xCD4C literals to
 * 0xFFFFD2C4/0xFFFFCD4C (the disassembler prints only the low 16 bits). */
#define RX8_TEMP_STATUS_ADDR 0xFFFFCD4Cu   /* temperature status byte        */
#define RX8_GAUGE_VALUE_ADDR 0xFFFFD2C4u   /* gauge value byte (output)      */

/* 0x5AA5C — map the temperature status byte to the gauge value code:
 * any of bits 0x40|0x20|0x10|0x08|0x04 -> 7, else bit 0x80 -> 6, else 0. */
void rx8_temperature_gauge_5aa5c(void)
{
    uint8_t b = *(volatile uint8_t *)(uintptr_t)RX8_TEMP_STATUS_ADDR;
    uint8_t v = (b & 0x7Cu) ? 7u : (b & 0x80u) ? 6u : 0u;
    *(volatile uint8_t *)(uintptr_t)RX8_GAUGE_VALUE_ADDR = v;
}
