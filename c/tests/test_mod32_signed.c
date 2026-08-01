/*
 * Behavior test for the Track-A lift of mod32_signed (ROM 0x4144).
 *
 * Verifies that the C lift of mod32_signed (dividend % divisor, truncating
 * toward zero) matches C's built-in signed integer remainder for all edge
 * cases and random inputs.
 *
 * Build/run on the host (no SH toolchain needed):
 *   cc -O2 c/mod32_signed.c c/tests/test_mod32_signed.c -o /tmp/t && /tmp/t
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <limits.h>

extern int32_t mod32_signed(int32_t divisor, int32_t dividend);

int main(void)
{
    /* Edge cases: (divisor, dividend, expected) */
    struct { int32_t d, v, exp; } edges[] = {
        { 1, 0, 0 },
        { 1, 1, 0 },
        { 2, 5, 1 },           /* 5 % 2 = 1 */
        { 5, 17, 2 },          /* 17 % 5 = 2 */
        { -1, -1, 0 },         /* -1 % -1 = 0 */
        { 1, -1, 0 },          /* -1 % 1 = 0 */
        { -1, 1, 0 },          /* 1 % -1 = 0 */
        { 3, 7, 1 },
        { -3, 7, 1 },          /* 7 % -3 = 1  (trunc toward zero) */
        { 3, -7, -1 },         /* -7 % 3 = -1 */
        { -3, -7, -1 },        /* -7 % -3 = -1 */
        { 5, 12, 2 },          /* 12 % 5 = 2 */
        { -5, 12, 2 },         /* 12 % -5 = 2 */
        { 5, -12, -2 },        /* -12 % 5 = -2 */
        { -5, -12, -2 },       /* -12 % -5 = -2 */
        { INT32_MAX, 100, 100 },   /* 100 % INT32_MAX = 100 */
        { INT32_MIN, 100, 100 },   /* 100 % INT32_MIN = 100 */
        { 100, 0, 0 },             /* 0 % 100 = 0 */
        { -100, 0, 0 },
        { 65536, 123456, 123456 % 65536 },  /* host-computed */
        { 2, -2147483647-1, 0 },            /* INT32_MIN % 2 = 0 */
        { -2, -2147483647-1, 0 },           /* INT32_MIN % -2 = 0 */
    };

    int n_edge = sizeof(edges) / sizeof(edges[0]);
    for (int i = 0; i < n_edge; i++) {
        int32_t r = mod32_signed(edges[i].d, edges[i].v);
        if (r != edges[i].exp) {
            printf("FAIL EDGE divisor=%d dividend=%d → %d expected %d\n",
                   edges[i].d, edges[i].v, r, edges[i].exp);
            return 1;
        }
    }

    /* Random tests */
    srand(2);
    for (long i = 0; i < 100000L; i++) {
        int32_t divisor = (int32_t)(unsigned)(rand() | (rand() << 15));
        if (divisor == 0) divisor = 1;
        int32_t dividend = (int32_t)(unsigned)(rand() | (rand() << 15));
        int32_t result = mod32_signed(divisor, dividend);
        int32_t expected = dividend % divisor;
        if (result != expected) {
            printf("MISMATCH divisor=%d dividend=%d lift=%d expected=%d\n",
                   divisor, dividend, result, expected);
            return 1;
        }
    }

    /* Division by zero */
    int32_t r = mod32_signed(0, 100);
    if (r != 0) {
        printf("FAIL: div0 returned %d expected 0\n", r);
        return 1;
    }

    printf("OK  mod32_signed == C remainder  (100K random, %d edge cases)\n", n_edge);
    return 0;
}
