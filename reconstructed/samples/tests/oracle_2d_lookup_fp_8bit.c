/* ============================================================================
 * oracle_2d_lookup_fp_8bit.c — host test rig for rx8_2d_lookup_fp_8bit
 * ============================================================================
 * Compile together with src/rx8_2d_lookup_fp_8bit.c and pipe test vectors
 * on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     fp8 <count> <x_bits> <ax0> ... <ax{count-1}> <v0> ... <v{count-1}>
 *                                            -> <result 2 hex digits>
 *
 *   count  : number of axis breakpoints (= number of cells), 2..64
 *   x_bits : raw IEEE-754 single-precision bits of the lookup input x (fr4)
 *            — passed as bits so float->hex round-trips exactly on both
 *            sides of the pipe
 *   axN    : raw bits of the ascending breakpoints (the descriptor's axis)
 *   vN     : the count u8 cell values (the descriptor's values array)
 *
 * The result is printed as the truncated, masked uint8 the ROM returns in r0
 * after ftrc fr2,fpul / extu.b r0,r0.
 *
 * NOTE: rx8_2d_lookup_fp_8bit and rx8_map1d_t are declared/defined here rather
 * than in rx8_samples.h (which is off-limits for this task) — the reconstructed
 * name maps to the ROM function at 0x20AC (see rx8_2d_lookup_fp_8bit.c).
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rx8_samples.h"

/* 0x20AC — float-input 1-D lookup over u8 cells (see rx8_2d_lookup_fp_8bit.c). */
typedef struct {
    uint16_t     count;
    uint8_t      type;
    uint8_t      _pad;
    const float *axis;
    const void  *values;
    float        scale;
    float        offset;
} rx8_map1d_t;

uint8_t rx8_2d_lookup_fp_8bit(const rx8_map1d_t *m, float x);

#define MAX_N 64

int main(void)
{
    char line[2048];

    while (fgets(line, sizeof line, stdin)) {
        char *tok;
        unsigned long count, xbits;
        float axis[MAX_N], x;
        uint8_t cells[MAX_N], result;
        uint32_t u;
        size_t k;

        tok = strtok(line, " \t\r\n");
        if (!tok) {
            continue;                       /* blank line */
        }
        if (strcmp(tok, "fp8") != 0) {
            fprintf(stderr, "bad opcode: %s\n", tok);
            return 2;
        }
        count = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        xbits = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        if (count < 2 || count > MAX_N) {
            fprintf(stderr, "bad count: %lu\n", count);
            return 2;
        }
        for (k = 0; k < count; k++) {
            u = (uint32_t)strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
            memcpy(&axis[k], &u, sizeof u);      /* exact float from raw bits */
        }
        for (k = 0; k < count; k++) {
            cells[k] = (uint8_t)strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        }

        u = (uint32_t)xbits;
        memcpy(&x, &u, sizeof x);               /* exact float from raw bits */

        rx8_map1d_t desc;
        desc.count = (uint16_t)count;
        desc.type = 4;                          /* u8 cells */
        desc._pad = 0;
        desc.axis = axis;
        desc.values = cells;
        desc.scale = 0.0f;
        desc.offset = 0.0f;

        result = rx8_2d_lookup_fp_8bit(&desc, x);

        printf("%02X\n", (unsigned)result);     /* uint8 result */
    }
    return 0;
}
