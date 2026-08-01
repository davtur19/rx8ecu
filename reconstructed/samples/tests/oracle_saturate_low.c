/* ============================================================================
 * oracle_saturate_low.c  —  host oracle for rx8_saturate_low
 * ============================================================================
 * Compile together with the reconstructed source (see
 * harness_saturate_low.py) and pipe test vectors on stdin; one vector per
 * line, whitespace-separated hex tokens:
 *
 *     f32 <sig_bits> <lower_bits>        -> <r_bits>    (IEEE-754 f32, hex)
 *
 * Each input token is the raw 32-bit IEEE-754 pattern of the argument, so the
 * host receives exactly the single-precision value the emulator loads into
 * the SH-2E FP register file (no double-rounding anywhere).  The result is
 * printed as the 32-bit pattern of the returned float for a bit-exact
 * comparison.  The oracle contains NO copy of the function logic — that lives
 * solely in rx8_saturate_low.c under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "rx8_samples.h"

/* rx8_samples.h (shared, untouched by this sample) does not declare the
 * function under test; declare its prototype here instead. */
float rx8_saturate_low(float sig, float lower);

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long a, b;

        if (sscanf(line, "f32 %lx %lx", &a, &b) == 2) {
            float sig, lower, r;
            unsigned long rb;

            memcpy(&sig, &a, sizeof sig);
            memcpy(&lower, &b, sizeof lower);
            r  = rx8_saturate_low(sig, lower);
            memcpy(&rb, &r, sizeof r);
            printf("%08lX\n", rb);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
