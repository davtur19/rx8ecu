/* ============================================================================
 * oracle_interpolate_u8_table.c — host test rig for rx8_interpolate_u8_table
 * ============================================================================
 * Compile together with src/rx8_interpolate_u8_table.c and pipe test vectors
 * on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     u8 <i> <t_bits> <n> <c0> <c1> ... <c{n-1}>      -> <result_bits>
 *
 *   i        : cell index (r0 in the ROM leaf's register convention)
 *   t_bits   : raw IEEE-754 single-precision bits of the interpolation
 *              fraction t (fr0) — passed as bits so float->hex round-trips
 *              exactly on both sides of the pipe
 *   n        : cell-array length (the oracle simply forwards every cell to the
 *              reconstructed function; no clamping is done on the host side,
 *              exactly like the ROM leaf)
 *   c0..     : the n cell values (uint8)
 *
 * The result is printed as the raw bits of the returned float (fr2 on the ROM).
 *
 * NOTE: rx8_interpolate_u8_table is declared here rather than in rx8_samples.h
 * (which is off-limits for this task) — the reconstructed name maps to the ROM
 * leaf at 0x26B0 (see rx8_interpolate_u8_table.c).
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rx8_samples.h"

/* 0x26B0 — u8-cell linear-interpolation leaf (see rx8_interpolate_u8_table.c). */
float rx8_interpolate_u8_table(int32_t index, const uint8_t *cells, float t);

#define MAX_CELLS 64

int main(void)
{
    char line[512];

    while (fgets(line, sizeof line, stdin)) {
        char *tok;
        unsigned long i, tbits, n;
        uint8_t cells[MAX_CELLS];
        float t, result;
        uint32_t rbits, i_tbits;
        size_t k;

        tok = strtok(line, " \t\r\n");
        if (!tok) {
            continue;                       /* blank line */
        }
        if (strcmp(tok, "u8") != 0) {
            fprintf(stderr, "bad opcode: %s\n", tok);
            return 2;
        }
        i = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        tbits = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        n = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        if (n == 0 || n > MAX_CELLS) {
            fprintf(stderr, "bad cell count: %lu\n", n);
            return 2;
        }
        for (k = 0; k < n; k++) {
            cells[k] = (uint8_t)strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        }

        i_tbits = (uint32_t)tbits;
        memcpy(&t, &i_tbits, sizeof t);     /* exact float from raw bits */

        result = rx8_interpolate_u8_table((int32_t)i, cells, t);

        memcpy(&rbits, &result, sizeof rbits);
        printf("%08X\n", rbits);
    }
    return 0;
}
