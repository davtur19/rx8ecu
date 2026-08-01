/*
 * =============================================================================
 * rx8_memcpy_bytewise.c  —  BYTE-BY-BYTE MEMORY COPY, 4× UNROLLED
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x42B0
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_memcpy_bytewise.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge
 *               vectors; ROM RAM side-effects compared to the host C),
 *               in addition to the existing c/tests/test_memcpy_bytewise_
 *               unroll4.py entry.
 * Lift (truth): c/memcpy_bytewise_unroll4.c
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Denso's PCM code has a small hot-path "memcpy" that is deliberately
 * alignment-agnostic: it copies one byte at a time with `mov.b`, unrolled 4×
 * per loop iteration so a full iteration moves 4 bytes while issuing only
 * four unconditional branches per 4 bytes.  The SH-2E register protocol is
 * NOT the standard r4-r7 calling convention:
 *
 *     r0 = count (bytes to copy)
 *     r1 = destination pointer
 *     r2 = source pointer
 *     r4 = src + count  (end sentinel, computed once inside the function)
 *
 * Assembly (from the ROM at 0x42B0):
 *
 *     mov.l  r2,@-r15
 *     mov.l  r3,@-r15
 *     mov.l  r4,@-r15
 *     cmp/eq #0x00,r0           ; count == 0 -> return immediately
 *     bt     exit
 *     mov    r2,r4              ; r4 = src + count  (end bound)
 *     add    r0,r4
 * loop:
 *     mov.b  @r2+,r0            ; byte 0   (post-increment read)
 *     mov.b  r0,@r1
 *     cmp/hi r2,r4              ; r2 < r4  (unsigned) -> keep going
 *     bf     exit
 *     mov.b  @r2+,r0            ; byte 1
 *     mov.b  r0,@(0x1,r1)
 *     cmp/hi r2,r4
 *     bf     exit
 *     mov.b  @r2+,r0            ; byte 2
 *     mov.b  r0,@(0x2,r1)
 *     cmp/hi r2,r4
 *     bf     exit
 *     mov.b  @r2+,r0            ; byte 3
 *     mov.b  r0,@(0x3,r1)
 *     cmp/hi r2,r4
 *     add    #0x04,r1
 *     bt     loop
 * exit:
 *     mov.l  @r15+,r4
 *     mov.l  @r15+,r3
 *     rts
 *     mov.l  @r15+,r2           ; (delay slot)
 *
 * Semantics: straight memcpy — bytes are read from `src` and written to
 * `dst` strictly in order, so overlapping src/dst behaves exactly like the
 * hardware (forward overlap corrupts, same as a naive byte copy).  The
 * unroll-4 shape is preserved verbatim below (it is behaviourally observable
 * through the exact point where the copy stops).
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

void rx8_memcpy_bytewise(uint8_t *dst, const uint8_t *src, uint32_t count)
{
    if (count == 0) {
        return;                          /* cmp/eq #0x00,r0; bt exit */
    }

    const uint8_t *end = src + count;    /* r4 = src + count */
    do {
        dst[0] = src[0];                 /* byte 0 */
        if (src + 1 >= end) return;
        dst[1] = src[1];                 /* byte 1 */
        if (src + 2 >= end) return;
        dst[2] = src[2];                 /* byte 2 */
        if (src + 3 >= end) return;
        src  += 4;                       /* r2 advanced past byte 3 */
        dst[3] = src[-1];                /* byte 3, written @(0x3,r1) */
        dst  += 4;                       /* add #0x04,r1 */
    } while (src < end);                 /* cmp/hi r2,r4; bt loop */
}
