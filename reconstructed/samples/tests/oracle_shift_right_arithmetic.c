/* ============================================================================
 * oracle_shift_right_arithmetic.c  —  host test rig for
 *                                      rx8_shift_right_arithmetic @0x43C8
 * ============================================================================
 * Compile together with samples/src/rx8_shift_right_arithmetic.c (see
 * harness_shift_right_arithmetic.py for the exact command) and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     sra <val> <cnt>                       -> <r>
 *
 * <val>/<cnt> are unsigned hex tokens; <r> is the arithmetic (sign-extending)
 * right shift printed as %08lX.  The oracle contains NO copy of the shift
 * logic — that lives solely in the reconstructed source under test.
 *
 * NOTE: this sample is not part of rx8_samples.h (that header was not
 * extended for it), so the prototype is declared locally.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <string.h>

int32_t rx8_shift_right_arithmetic(int32_t val, int32_t cnt);

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long v, c;

        if (sscanf(line, "sra %lx %lx", &v, &c) == 2) {
            int32_t r = rx8_shift_right_arithmetic((int32_t)(uint32_t)v,
                                                   (int32_t)(uint32_t)c);
            printf("%08lX\n", (unsigned long)(uint32_t)r);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
