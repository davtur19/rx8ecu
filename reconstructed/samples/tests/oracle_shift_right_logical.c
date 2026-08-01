/* ============================================================================
 * oracle_shift_right_logical.c  —  host oracle for rx8_shift_right_logical_r0
 * ============================================================================
 * Compile together with src/rx8_shift_right_logical.c and pipe test vectors on
 * stdin; one vector per line as two whitespace-separated hex tokens:
 *
 *     <val> <cnt>                  -> <result>
 *
 * where <val> is the 32-bit value and <cnt> the shift count in 32-bit
 * two's-complement (so a negative count arrives as e.g. FFFFFFFF for -1).
 * The result is printed as one 8-digit hex line.
 *
 * This file contains NO copy of the shift logic — that lives solely in
 * src/rx8_shift_right_logical.c under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>

#include "rx8_samples.h"

/* 0x44E0 — logical right shift; value in r0, count in r1 (SH-2 convention). */
uint32_t rx8_shift_right_logical_r0(uint32_t val, int32_t cnt);

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long v, c;
        if (sscanf(line, "%lx %lx", &v, &c) != 2) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        printf("%08lX\n",
               (unsigned long)(uint32_t)rx8_shift_right_logical_r0(
                   (uint32_t)v, (int32_t)(uint32_t)c));
    }
    return 0;
}
