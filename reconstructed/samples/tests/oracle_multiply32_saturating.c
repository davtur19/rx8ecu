/* ============================================================================
 * oracle_multiply32_saturating.c  —  host test rig for
 *                                      rx8_multiply32_saturating @0x231C
 * ============================================================================
 * Compile together with samples/src/rx8_multiply32_saturating.c (see
 * harness_multiply32_saturating.py for the exact command) and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     mul <a> <b>                       -> <r>
 *
 * <a>/<b> are unsigned hex tokens; <r> is the saturating Q16.16 product
 * printed as %08lX.  The oracle contains NO copy of the multiply logic —
 * that lives solely in the reconstructed source under test.
 *
 * NOTE: this sample is not part of rx8_samples.h (that header was not
 * extended for it), so the prototype is declared locally.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>

int32_t rx8_multiply32_saturating(int32_t a, int32_t b);

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long a, b;

        if (sscanf(line, "mul %lx %lx", &a, &b) == 2) {
            int32_t r = rx8_multiply32_saturating((int32_t)(uint32_t)a,
                                                  (int32_t)(uint32_t)b);
            printf("%08lX\n", (unsigned long)(uint32_t)r);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
