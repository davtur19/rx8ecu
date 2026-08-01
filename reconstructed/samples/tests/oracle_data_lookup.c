/* ============================================================================
 * oracle_data_lookup.c — host test rig for rx8_data_lookup
 * ============================================================================
 * Compile together with src/rx8_data_lookup.c and pipe test vectors on stdin;
 * one vector per line, whitespace-separated hex tokens:
 *
 *     dl <n> <x_bits> <a0_bits> <a1_bits> ... <a{n-1}_bits>  ->  <i> <t_bits>
 *
 *   n       : number of axis breakpoints (count)
 *   x_bits  : raw IEEE-754 single-precision bits of the input x (fr0 in the
 *             ROM leaf's register convention) — passed as bits so float->hex
 *             round-trips exactly on both sides of the pipe
 *   a0..    : the n axis breakpoints, each as raw single-precision bits
 *
 * The result is printed as the index (r0 on the ROM) and the raw bits of the
 * interpolation fraction t (fr0 on the ROM).
 *
 * NOTE: rx8_data_lookup is declared here rather than in rx8_samples.h (which
 * is off-limits for this task) — the reconstructed name maps to the ROM leaf
 * at 0x2624 (see rx8_data_lookup.c).
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rx8_samples.h"

/* 0x2624 — 1-D axis-search leaf (see rx8_data_lookup.c). */
void rx8_data_lookup(int32_t n, const float *axis, float x,
                     int32_t *out_index, float *out_t);

#define MAX_AXIS 64

int main(void)
{
    char line[4096];

    while (fgets(line, sizeof line, stdin)) {
        char *tok;
        unsigned long n, xbits, abits;
        float axis[MAX_AXIS], x, t;
        int32_t index;
        uint32_t ubits;
        size_t k;

        tok = strtok(line, " \t\r\n");
        if (!tok) {
            continue;                       /* blank line */
        }
        if (strcmp(tok, "dl") != 0) {
            fprintf(stderr, "bad opcode: %s\n", tok);
            return 2;
        }
        n = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        xbits = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        if (n == 0 || n > MAX_AXIS) {
            fprintf(stderr, "bad axis count: %lu\n", n);
            return 2;
        }
        for (k = 0; k < n; k++) {
            abits = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
            ubits = (uint32_t)abits;
            memcpy(&axis[k], &ubits, sizeof axis[k]);   /* exact float from bits */
        }

        ubits = (uint32_t)xbits;
        memcpy(&x, &ubits, sizeof x);                   /* exact float from bits */

        rx8_data_lookup((int32_t)n, axis, x, &index, &t);

        memcpy(&ubits, &t, sizeof ubits);
        printf("%X %08X\n", (unsigned)(index & 0xFFFFFFFFu), ubits);
    }
    return 0;
}
