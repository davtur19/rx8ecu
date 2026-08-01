/*
 * ============================================================================
 * oracle_mod32_signed.c  —  host test rig for rx8_mod32_signed
 * ============================================================================
 * Pipe vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     mod <divisor> <dividend>      -> <remainder>          (8 hex digits)
 *
 * The oracle contains NO copy of the function logic — it lives solely in
 * src/rx8_mod32_signed.c under test.  Both arguments are 32-bit two's
 * complement; the result is printed as an unsigned 32-bit hex value so it can
 * be compared byte-for-byte against the emulator's r0.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>

#include "rx8_samples.h"

/* The reconstructed sample under test (declared here until it gains a home
 * in rx8_samples.h; rx8_mod32_signed.c is the definition). */
int32_t rx8_mod32_signed(int32_t divisor, int32_t dividend);

int main(void)
{
    char line[128];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long divisor, dividend;

        if (sscanf(line, "mod %lx %lx", &divisor, &dividend) == 2) {
            printf("%08lX\n",
                   (unsigned long)(uint32_t)rx8_mod32_signed(
                       (int32_t)(uint32_t)divisor, (int32_t)(uint32_t)dividend));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
