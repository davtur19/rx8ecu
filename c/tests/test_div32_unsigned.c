/*
 * Host test for the Track-A lift of div32_unsigned (ROM 0x409C).
 *
 * Verifies that the C lift of div32_unsigned (dividend / divisor, unsigned,
 * truncating) matches C's built-in unsigned division for edge cases and
 * random inputs.
 *
 * Build/run on the host (no SH toolchain needed):
 *   cc -O2 c/div32_unsigned.c c/tests/test_div32_unsigned.c -o /tmp/t && /tmp/t
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

extern uint32_t div32_unsigned(uint32_t divisor, uint32_t dividend);

int main(void)
{
    /* Edge cases: (divisor, dividend, expected) */
    struct { uint32_t d, v, exp; } edges[] = {
        { 1, 0, 0 },
        { 1, 1, 1 },
        { 2, 5, 2 },
        { 5, 17, 3 },
        { 7, 100, 14 },
        { 0xFFFFFFFFu, 0xFFFFFFFFu, 1 },
        { 0xFFFFFFFFu, 0xFFFFFFFEu, 0 },
        { 0x80000000u, 0xFFFFFFFFu, 1 },
        { 0x00010000u, 0xFFFFFFFFu, 0xFFFFu },
        { 0x00000010u, 0xFFFFFFFFu, 0x0FFFFFFFu },
        { 0x10000u, 0x12345678u, 0x1234u },
        { 0x100u, 0x12345678u, 0x123456u },
        { 0x7FFFFFFFu, 0x7FFFFFFFu, 1 },
        { 0x7FFFFFFFu, 0x80000000u, 1 },
        { 0x80000000u, 0x80000000u, 1 },
        { 3, 0, 0 },
        { 10, 0, 0 },
        { 2, 1, 0 },
        { 2, 3, 1 },
    };

    int n_edge = sizeof(edges) / sizeof(edges[0]);
    for (int i = 0; i < n_edge; i++) {
        uint32_t r = div32_unsigned(edges[i].d, edges[i].v);
        if (r != edges[i].exp) {
            printf("FAIL EDGE divisor=0x%08X dividend=0x%08X → 0x%08X expected 0x%08X\n",
                   edges[i].d, edges[i].v, r, edges[i].exp);
            return 1;
        }
    }

    /* Random tests: unsigned division is exact in C for both operands. */
    srand(12345);
    for (int i = 0; i < 20000; i++) {
        uint32_t d = ((uint32_t)rand() << 16) | (uint32_t)rand();
        uint32_t v = ((uint32_t)rand() << 16) | (uint32_t)rand();
        if (d == 0) { i--; continue; }
        uint32_t r = div32_unsigned(d, v);
        uint32_t exp = v / d;
        if (r != exp) {
            printf("FAIL RAND divisor=0x%08X dividend=0x%08X → 0x%08X expected 0x%08X\n",
                   d, v, r, exp);
            return 1;
        }
    }

    /* Division by zero: lift returns 0 (hardware write is skipped on host). */
    if (div32_unsigned(0, 100) != 0) {
        printf("FAIL div-by-zero returned non-zero\n");
        return 1;
    }

    printf("OK  div32_unsigned @0x409C  (%d edge + 20000 random, excl div0)\n", n_edge);
    return 0;
}
