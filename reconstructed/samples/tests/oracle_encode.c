/* ============================================================================
 * oracle_encode.c  —  host oracle for rx8_encode @0x2420
 * ============================================================================
 * Compile together with the reconstructed source (see harness_encode.py) and
 * pipe test vectors on stdin; one vector per line, whitespace-separated hex
 * tokens:
 *
 *     enc <val>        -> <r>     (16-bit result, hex)
 *
 * `val` is the full 32-bit raw register image that the emulator places in r4
 * (hex).  The ROM's `extu.b` keeps only the low byte, so the oracle passes it
 * through a uint8_t parameter — the narrowing happens exactly where the
 * hardware does it.  The oracle contains NO copy of the function logic; that
 * lives solely in rx8_encode.c under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>

#include "rx8_samples.h"

/* 0x2420 — value/complement byte encoder; 8-bit value in r4, 16-bit
 * (value,~value) word in r0.  Declared here rather than in rx8_samples.h so
 * this sample stays self-contained and leaves the shared header untouched. */
uint16_t rx8_encode(uint8_t x);

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        char op[16];
        unsigned long a;

        if (sscanf(line, "%15s %lx", op, &a) == 2) {
            uint8_t x = (uint8_t)(uint32_t)a;   /* extu.b semantics */
            printf("%04X\n", (unsigned)rx8_encode(x));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
