/* ============================================================================
 * oracle_invert_and_return_8bit.c — host test rig for rx8_invert_and_return_8bit
 * ============================================================================
 * Reads one vector per line from stdin:  `u8 <hi> <lo>` (hex tokens), calls
 * the reconstructed function with a 2-byte (hi,lo) cell, and prints the hex
 * result on stdout.  Contains NO copy of the function logic — that lives
 * solely in samples/src/rx8_invert_and_return_8bit.c.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>

#include "rx8_samples.h"

/* Reconstructed sample under test (declared in rx8_samples.h once added). */
uint8_t rx8_invert_and_return_8bit(const uint8_t *addr);

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long hi, lo;
        uint8_t cell[2];

        if (sscanf(line, "u8 %lx %lx", &hi, &lo) != 2) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        cell[0] = (uint8_t)hi;   /* upper bits, if any, are masked away */
        cell[1] = (uint8_t)lo;
        printf("%02X\n", rx8_invert_and_return_8bit(cell));
    }
    return 0;
}
