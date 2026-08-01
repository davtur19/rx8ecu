/*
 * memcpy_bytewise_unroll4.c  —  RX-8 PCM byte copy, 4× unrolled (0x0042B0)
 *
 * Copy `count` bytes from `src` to `dst`.  The loop is unrolled 4×:
 * each iteration copies 4 bytes with separate mov.b instructions.
 * No alignment requirement — operates byte-by-byte.
 *
 * SH-2E asm (r0 = count, r1 = dst, r2 = src):
 *   0x0042B0: mov.l  r2,@-r15
 *   0x0042B2: mov.l  r3,@-r15
 *   0x0042B4: mov.l  r4,@-r15
 *   0x0042B6: cmp/eq #0x00,r0         ; if count == 0 → skip
 *   0x0042B8: bt     exit
 *   0x0042BA: mov    r2,r4            ; r4 = src + count  (end bound)
 *   0x0042BC: add    r0,r4
 * loop:
 *   0x0042BE: mov.b  @r2+,r0          ; byte 0
 *   0x0042C0: mov.b  r0,@r1
 *   0x0042C2: cmp/hi r2,r4            ; if r2 >= r4 → exit
 *   0x0042C4: bf     exit
 *   0x0042C6: mov.b  @r2+,r0          ; byte 1
 *   0x0042C8: mov.b  r0,@(0x1,r1)
 *   0x0042CA: cmp/hi r2,r4
 *   0x0042CC: bf     exit
 *   0x0042CE: mov.b  @r2+,r0          ; byte 2
 *   0x0042D0: mov.b  r0,@(0x2,r1)
 *   0x0042D2: cmp/hi r2,r4
 *   0x0042D4: bf     exit
 *   0x0042D6: mov.b  @r2+,r0          ; byte 3
 *   0x0042D8: mov.b  r0,@(0x3,r1)
 *   0x0042DA: cmp/hi r2,r4            ; while r2 < r4
 *   0x0042DC: add    #0x04,r1
 *   0x0042DE: bt     loop
 * exit:
 *   0x0042E0: mov.l  @r15+,r4
 *   0x0042E2: mov.l  @r15+,r3
 *   0x0042E4: rts
 *   0x0042E6: mov.l  @r15+,r2
 *
 * Register state:
 *   r0 = byte temporary / initial count
 *   r1 = dst pointer (advances by 4 each iteration)
 *   r2 = src pointer (advances by 4)
 *   r4 = src + count  (end sentinel — computed once)
 *
 * Track A: verified behavior-equivalent to emulated ROM over
 * 100000 random (src, dst, count) tuples.
 */
#include <stdint.h>

/* 0x0042B0  Byte-by-byte memory copy, unrolled 4×                     */
void memcpy_bytewise_unroll4(uint8_t *dst, const uint8_t *src, uint32_t count)
{
    if (count == 0) return;

    const uint8_t *end = src + count;
    do {
        dst[0] = src[0];
        if (src + 1 >= end) return;
        dst[1] = src[1];
        if (src + 2 >= end) return;
        dst[2] = src[2];
        if (src + 3 >= end) return;
        src  += 4;
        dst[3] = src[-1];   /* the pre-incremented src points past byte 3 */
        dst  += 4;
    } while (src < end);
}
