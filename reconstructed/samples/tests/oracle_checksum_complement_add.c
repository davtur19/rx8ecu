/* ============================================================================
 * oracle_checksum_complement_add.c  —  host oracle for rx8_checksum_complement_add
 * ============================================================================
 * Compile together with the reconstructed source (see
 * harness_checksum_complement_add.py) and pipe test vectors on stdin; one
 * vector per line, whitespace-separated hex tokens:
 *
 *     sum <val>                    -> <r>     (16-bit checksum residual, hex)
 *
 * `val` is the 32-bit content of the redundant cell.  In the ROM the cell is
 * read through the pointer in r4 (`mov.l @r4,r3`); the harness performs that
 * caller-side load on the emulator side (placing the big-endian bytes in RAM)
 * and hands the same numeric value to this oracle, so both sides see an
 * identical uint32_t.  The oracle contains NO copy of the function logic —
 * that lives solely in rx8_checksum_complement_add.c under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>

#include "rx8_samples.h"

/* rx8_samples.h (shared, untouched by this sample) does not declare the
 * function under test; declare its prototype here instead. */
uint16_t rx8_checksum_complement_add(uint32_t value);

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long a;

        if (sscanf(line, "sum %lx", &a) == 1) {
            printf("%04lX\n",
                   (unsigned long)rx8_checksum_complement_add((uint32_t)a));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
