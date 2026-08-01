/*
 * Behavior test for the Track-A lift of div32_signed (ROM 0x3FE8).
 *
 * Verifies that the C lift of div32_signed (dividend / divisor, truncating
 * toward zero) matches C's built-in signed integer division for all edge
 * cases and random inputs.
 *
 * Build/run on the host (no SH toolchain needed):
 *   cc -O2 c/div32_signed.c c/tests/test_div32_signed.c -o /tmp/t && /tmp/t
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <limits.h>

extern int32_t div32_signed(int32_t divisor, int32_t dividend);

int main(void)
{
    /* Edge cases: (divisor, dividend, expected) */
    struct { int32_t d, v, exp; } edges[] = {
        { 1, 0, 0 },
        { 1, 1, 1 },
        { 2, 5, 2 },
        { 5, 17, 3 },
        { -1, -1, 1 },           /* -1 / -1 = 1 */
        { 1, -1, -1 },           /* 1 / -1 = -1 */
        { -1, 1, -1 },           /* -1 / 1 = -1 */
        { 1073741824, INT32_MIN, -2 },  /* INT32_MIN / 2^30 = -2 */
        { -1, INT32_MIN, INT32_MIN },   /* INT32_MIN / -1 = INT32_MIN (SH-2E wraps; C division is UB for this pair) */
        { INT32_MAX, INT32_MAX, 1 },
        { INT32_MIN, INT32_MIN, 1 },    /* MIN_INT / MIN_INT = 1 */
        { INT32_MIN, 0, 0 },            /* 0 / MIN_INT = 0 */
        { 3, 0, 0 },
        { 10, 0, 0 },
        { -1, 0, 0 },
        { -2, 3, -1 },           /* 3 / -2 = -1 */
        { 2, -5, -2 },           /* -5 / 2 = -2 */
        { -3, -7, 2 },           /* -7 / -3 = 2 */
        { 100, 1, 0 },           /* 1 / 100 = 0 */
        { -100, 1, 0 },
        { 1, 1, 1 },
        { -1, -2, 2 },           /* -2 / -1 = 2 */
        { 65536, 123456, 1 },    /* 123456 / 65536 = 1 */
        { 3, 7, 2 },
        { 3, -7, -2 },
        { -3, 7, -2 },
        { -3, -7, 2 },
    };

    int n_edge = sizeof(edges) / sizeof(edges[0]);
    for (int i = 0; i < n_edge; i++) {
        int32_t r = div32_signed(edges[i].d, edges[i].v);
        if (r != edges[i].exp) {
            printf("FAIL EDGE divisor=%d dividend=%d → %d expected %d\n",
                   edges[i].d, edges[i].v, r, edges[i].exp);
            return 1;
        }
    }

    /* Random tests */
    srand(1);
    for (long i = 0; i < 100000L; i++) {
        int32_t divisor = (int32_t)(unsigned)(rand() | (rand() << 15));
        if (divisor == 0) divisor = 1;  /* skip div0 (tested separately) */
        int32_t dividend = (int32_t)(unsigned)(rand() | (rand() << 15));
        int32_t result = div32_signed(divisor, dividend);
        int32_t expected = dividend / divisor;
        if (result != expected) {
            printf("MISMATCH divisor=%d dividend=%d lift=%d expected=%d\n",
                   divisor, dividend, result, expected);
            return 1;
        }
    }

    /* Division by zero */
    int32_t r = div32_signed(0, 100);
    if (r != 0) {
        printf("FAIL: div0 returned %d expected 0\n", r);
        return 1;
    }

    printf("OK  div32_signed == C division  (100K random, %d edge cases)\n", n_edge);
    return 0;
}
