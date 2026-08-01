/* ============================================================================
 * oracle_div32_unsigned.c  —  host test rig for rx8_div32_unsigned @0x409C
 * ============================================================================
 * Reads one vector per line on stdin, whitespace-separated hex tokens:
 *
 *     div <divisor> <dividend>       -> <quotient>
 *
 * and prints the 32-bit quotient as %08X.  The oracle contains NO copy of the
 * division logic — that lives solely in src/rx8_div32_unsigned.c.  The op token
 * mirrors the caller-side set-up used by the emulator harness (divisor in r0,
 * dividend in r1), but both operands are simply forwarded to the C function.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>

#include "rx8_samples.h"

/* rx8_samples.h (shared, untouched by this sample) does not declare the
 * function under test; declare its prototype here instead. */
uint32_t rx8_div32_unsigned(uint32_t divisor, uint32_t dividend);

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long divisor, dividend;

        if (sscanf(line, "div %lx %lx", &divisor, &dividend) == 2) {
            printf("%08lX\n",
                   (unsigned long)rx8_div32_unsigned((uint32_t)divisor,
                                                     (uint32_t)dividend));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
