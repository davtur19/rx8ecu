/*
 * =============================================================================
 * rx8_bitfield_flag_status_decoder_339ac.c  —  FLAG-STATUS BIT DECODER
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x339AC  (74 bytes, 0x339AC..0x339F6)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/
 *               harness_bitfield_flag_status_decoder_339ac.py
 *               (host-gcc vs tools/sh2emu.py over edge + 20000 random 8-bit
 *               status bytes, comparing the side-effected status-code byte;
 *               0 mismatches).
 * Lift (truth): c/bitfield_flag_status_decoder_339AC.c
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A side-effect-only void leaf: it decodes three flag bits of the status byte
 * RAM[0xFFFFCD4E] into a status-code byte RAM[0xFFFFC04D] that the CAN-message
 * setup path consumes.  The dispatcher at 0x33974 reads RAM[0xFFFFC04D]
 * (literal 0x33A0C) and copies it into the outgoing message struct at
 * 0xFFFFC044, so the two bytes this leaf touches are plain on-chip RAM.
 *
 * The bit-test sequence at 0x339B4..0x339BC is the classic SH-2 boolean
 * idiom (`tst #imm,r0; movt r0; add #-1,r0; neg r0,r0; cmp/eq #1,r0; bt/s`),
 * repeated once per tested bit.  Branch targets, in execution order:
 *
 *     (b & 0x40) != 0  -> 0x339D4      (store r6 = 0x08)
 *     (b & 0x20) != 0  -> 0x339D4      (store r6 = 0x08)
 *     (b & 0x80) != 0  -> 0x339EA      (store r2 = 0x02)
 *     else             -> 0x339F0      (store r1 = 0x00)
 *
 * Disassembly of 60E1D400.bin @ 0x339AC (37 words, 74 bytes):
 *
 *     952F   mov.w  @(0x2F,PC),r5   ; r5 = 0xFFFFCD4E (input addr, sign-ext)
 *     D41C   mov.l  @(0x1C,PC),r4   ; r4 = 0xFFFFC04D (output addr, full 32-bit)
 *     6053   mov    r5,r0           ; r0 = &input
 *     6000   mov.b  @r0,r0          ; r0 = sign-extended byte @0xFFFFCD4E
 *     C840   tst    #0x40,r0        ; T = ((r0 & 0x40) == 0)
 *     0029   movt   r0              ; r0 = T
 *     70FF   add    #-1,r0
 *     600B   neg    r0,r0           ; r0 = 1 iff (b & 0x40), else 0
 *     8801   cmp/eq #1,r0           ; T = (r0 == 1)
 *     8D09   bt/s   0x339D4         ; (b & 0x40) -> store 8 and return
 *     E608   mov    #8,r6           ;   (delay slot) r6 = 0x08
 *     6053   mov    r5,r0
 *     6000   mov.b  @r0,r0          ; reload b (same byte, re-read)
 *     C820   tst    #0x20,r0
 *     0029   movt   r0
 *     70FF   add    #-1,r0
 *     600B   neg    r0,r0           ; r0 = 1 iff (b & 0x20), else 0
 *     8801   cmp/eq #1,r0
 *     8F02   bf/s   0x339D8         ; (b & 0x20) == 0 -> test 0x80
 *     0009   nop                    ;   (delay slot)
 *     A00E   bra    0x339F4         ; (b & 0x20) -> rts
 *     2460   mov.b  r6,@r4          ;   (delay slot) RAM[0xFFFFC04D] = 0x08
 *     6053   mov    r5,r0
 *     6000   mov.b  @r0,r0          ; reload b (same byte, re-read)
 *     C880   tst    #0x80,r0
 *     0029   movt   r0
 *     70FF   add    #-1,r0
 *     600B   neg    r0,r0           ; r0 = 1 iff (b & 0x80), else 0
 *     8801   cmp/eq #1,r0
 *     8F03   bf/s   0x339F0         ; (b & 0x80) == 0 -> store 0 and return
 *     0009   nop                    ;   (delay slot)
 *     E202   mov    #2,r2           ; r2 = 0x02
 *     A002   bra    0x339F4         ; (b & 0x80) -> rts
 *     2420   mov.b  r2,@r4          ;   (delay slot) RAM[0xFFFFC04D] = 0x02
 *     E100   mov    #0,r1           ; r1 = 0x00
 *     2410   mov.b  r1,@r4          ; RAM[0xFFFFC04D] = 0x00
 *     000B   rts
 *     0009   nop                    ;   (delay slot)
 *
 * The load-and-test pair `mov r5,r0; mov.b @r0,r0` at 0x339B0/0x339B2 is
 * repeated on every path, i.e. the status byte is re-read up to three times;
 * the C below deliberately performs a single volatile read instead (the byte
 * cannot change between reads on the ECU).  Sign extension of the loaded byte
 * is irrelevant: only bits 0x40/0x20/0x80 (all inside the low 8 bits) are
 * tested and the stored values 0x08/0x02/0x00 are positive constants.
 *
 * DISCREPANCIES vs THE LIFT (comment-only; behaviour identical)
 * ------------------------------------------------------------
 *  - c/bitfield_flag_status_decoder_339AC.c says the input is reached by
 *    "mov.w sign-extends 0xCD4E".  In the ROM the 0xCD4E literal is loaded by
 *    a PC-relative `mov.w @(0x2F,PC),r5` (the immediate at 0x33A0E) and the
 *    byte is then fetched by a separate `mov.b @r0,r0` — same net address
 *    0xFFFFCD4E, and the lift's C already models the byte read correctly.
 *  - The lift's comment "Return r0 is the last-loaded input byte
 *    (sign-extended)" is inaccurate: on every path r0 ends up holding the 0/1
 *    result of the last `movt`/`neg` boolean idiom (verified in the emulator),
 *    not the input byte.  Either way r0 is caller-garbage and the lift returns
 *    void, so behaviour is unaffected.
 *  - The output is written with `mov.b rX,@r4` byte stores (0x2460/0x2420/
 *    0x2410) to the full 32-bit literal 0xFFFFC04D (pool at 0x33A20) — a byte
 *    store, not the mov.l the adjacent dispatcher 0x33974 uses for its copy.
 * =============================================================================
 */
#include <stdint.h>
#include <stddef.h>

#include "rx8_samples.h"

/* Both addresses come from the verified lift c/bitfield_flag_status_decoder_339AC.c
 * (input byte pool word 0x33A0E = 0xCD4E; output pool word 0x33A20).  The
 * 0xFFFFCD48/0xFFFFCD49 "math flag out" bytes in include/rx8_hw.h sit in the
 * same status-word block, but 0xFFFFCD4E itself is not yet documented there. */
#define RX8_FLAG_STATUS_IN_ADDR  0xFFFFCD4Eu  /* flag/status input byte         */
#define RX8_STATUS_CODE_OUT_ADDR 0xFFFFC04Du  /* decoded status-code output byte */

/* 0x339AC — decode flag/status bits into a status-code byte.
 *   RAM[0xFFFFC04D] = (b & 0x40)||(b & 0x20) ? 0x08 : (b & 0x80) ? 0x02 : 0
 * where b = RAM[0xFFFFCD4E].  Matches the lift's `(b & 0x60)` grouping, which
 * is equivalent because bit 0x40 is tested strictly before bit 0x20. */
void rx8_bitfield_flag_status_decoder_339ac(void)
{
    uint8_t b = *(volatile uint8_t *)(uintptr_t)RX8_FLAG_STATUS_IN_ADDR;
    uint8_t v = (b & 0x60u) ? 0x08u : (b & 0x80u) ? 0x02u : 0x00u;
    *(volatile uint8_t *)(uintptr_t)RX8_STATUS_CODE_OUT_ADDR = v;
}
