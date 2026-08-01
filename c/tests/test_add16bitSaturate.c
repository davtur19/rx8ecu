/*
 * Behavior test for the Track-A lift of add16bitSaturate (ROM 0x2460).
 *
 * `ref()` is a MECHANICAL transcription of the actual SH-2 instructions (register
 * by register), so it encodes what the ROM does, not our interpretation. The lift
 * is proven behavior-equivalent by exhaustive edges + 20M random inputs.
 *
 * Build/run on the host (no SH toolchain needed):
 *   cc -O2 c/add16bitSaturate.c c/tests/test_add16bitSaturate.c -o /tmp/t && /tmp/t
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

/* exact transcription of the SH-2 sequence at 0x2460 */
static uint16_t ref(uint16_t a, uint16_t b)
{
    uint32_t r4 = (uint16_t)a;          /* extu.w r4,r4 */
    uint32_t r5 = (uint16_t)b;          /* extu.w r5,r5 */
    r4 = (r4 + r5) & 0xFFFFFFFFu;       /* add r5,r4    */
    r5 = 0x0000FFFFu;                   /* mov.l pool,r5 (pool @0x2474 == 0x0000FFFF) */
    if (r4 >= r5) r4 = r5;              /* cmp/hs r5,r4 ; fallthrough mov r5,r4 */
    uint32_t r0 = r4;                   /* mov r4,r0    */
    return (uint16_t)r0;                /* rts (return in r0) */
}

extern uint16_t add16bitSaturate(uint16_t, uint16_t);

int main(void)
{
    for (uint32_t a = 0; a <= 0xFFFF; a++) {
        uint16_t bs[] = {0, 1, 2, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF, (uint16_t)(0xFFFF - a)};
        for (int i = 0; i < 8; i++) {
            uint16_t b = bs[i];
            if (add16bitSaturate((uint16_t)a, b) != ref((uint16_t)a, b)) {
                printf("MISMATCH a=%u b=%u lift=%u ref=%u\n",
                       a, b, add16bitSaturate((uint16_t)a, b), ref((uint16_t)a, b));
                return 1;
            }
        }
    }
    srand(1);
    for (long i = 0; i < 20000000L; i++) {
        uint16_t a = (uint16_t)(rand() & 0xFFFF), b = (uint16_t)(rand() & 0xFFFF);
        if (add16bitSaturate(a, b) != ref(a, b)) {
            printf("MISMATCH a=%u b=%u\n", a, b);
            return 1;
        }
    }
    printf("OK  add16bitSaturate == asm-transcription  (all 65536 x 8 edges + 20M random)\n");
    return 0;
}
