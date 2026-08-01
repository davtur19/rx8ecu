/* ============================================================================
 * oracle_shift_right_8.c  —  host test rig for rx8_shift_right_8 @0x467A
 * ============================================================================
 * Compile together with the reconstructed source under test (see
 * harness_shift_right_8.py) and pipe test vectors on stdin: one value per
 * line, hex with an optional 0x prefix:
 *
 *     <v>       -> <result>            (8 hex digits)
 *
 * The oracle contains NO copy of the function logic — that lives solely in
 * src/rx8_shift_right_8.c.  The prototype is re-declared here on purpose so
 * this rig stays self-contained and independent of rx8_samples.h (which is
 * left untouched).
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>

int32_t rx8_shift_right_8(int32_t val);

int main(void)
{
    char line[64];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long v;
        if (sscanf(line, "%lx", &v) != 1) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        printf("%08lX\n",
               (unsigned long)(uint32_t)rx8_shift_right_8((int32_t)(uint32_t)v));
    }
    return 0;
}
