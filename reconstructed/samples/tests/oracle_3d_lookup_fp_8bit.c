/* ============================================================================
 * oracle_3d_lookup_fp_8bit.c — host test rig for rx8_3d_lookup_fp_8bit
 * ============================================================================
 * Compile together with src/rx8_3d_lookup_fp_8bit.c and pipe test vectors on
 * stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     f8 <cx> <cy> <ax0..ax{cx-1}> <ay0..ay{cy-1}> <v0..v{cx*cy-1}> <xbits> <ybits>
 *          -> <result byte as %02X>
 *
 *   cx, cy : X/Y breakpoint counts
 *   ax*    : raw IEEE-754 single-precision bits of the X breakpoints
 *   ay*    : raw bits of the Y breakpoints
 *   v*     : the cx*cy u8 cell values (row-major [count_y][count_x])
 *   xbits  : raw bits of the X lookup input
 *   ybits  : raw bits of the Y lookup input
 *
 * Every float crosses the pipe as its raw bit pattern so both sides operate on
 * the exact single-precision value (no text round-trip loss).  The result is
 * printed as %02X — the uint8_t return value, r0 (masked 0xFF) on the ROM.
 *
 * NOTE: Map2D and rx8_3d_lookup_fp_8bit are declared here rather than in
 * rx8_samples.h (which is off-limits for this task) — the reconstructed name
 * maps to the ROM function at 0x2120 (see rx8_3d_lookup_fp_8bit.c).
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rx8_samples.h"

/* 0x2120 — u8-cell bilinear FP lookup (see rx8_3d_lookup_fp_8bit.c). */
typedef struct {
    uint16_t     count_x;
    uint16_t     count_y;
    const float *axis_x;
    const float *axis_y;
    const void  *values;
    uint8_t      type;
    uint8_t      _pad[3];
    float        scale;
    float        offset;
} Map2D;

uint8_t rx8_3d_lookup_fp_8bit(const Map2D *m, float x, float y);

#define MAX_AXIS  64
#define MAX_CELLS (MAX_AXIS * MAX_AXIS)

static float bits2f(uint32_t b)
{
    float f;
    memcpy(&f, &b, sizeof f);
    return f;
}

int main(void)
{
    char line[2048];

    while (fgets(line, sizeof line, stdin)) {
        char *tok;
        unsigned long cx, cy;
        float ax[MAX_AXIS], ay[MAX_AXIS], x, y;
        uint8_t vals[MAX_CELLS];
        Map2D m;
        size_t k;

        tok = strtok(line, " \t\r\n");
        if (!tok) {
            continue;                       /* blank line */
        }
        if (strcmp(tok, "f8") != 0) {
            fprintf(stderr, "bad opcode: %s\n", tok);
            return 2;
        }
        cx = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        cy = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        if (cx < 2 || cx > MAX_AXIS || cy < 2 || cy > MAX_AXIS) {
            fprintf(stderr, "bad dims: %lu x %lu\n", cx, cy);
            return 2;
        }
        for (k = 0; k < cx; k++) {
            ax[k] = bits2f((uint32_t)strtoul(strtok(NULL, " \t\r\n"), NULL, 16));
        }
        for (k = 0; k < cy; k++) {
            ay[k] = bits2f((uint32_t)strtoul(strtok(NULL, " \t\r\n"), NULL, 16));
        }
        for (k = 0; k < cx * cy; k++) {
            vals[k] = (uint8_t)strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        }
        x = bits2f((uint32_t)strtoul(strtok(NULL, " \t\r\n"), NULL, 16));
        y = bits2f((uint32_t)strtoul(strtok(NULL, " \t\r\n"), NULL, 16));

        m.count_x = (uint16_t)cx;
        m.count_y = (uint16_t)cy;
        m.axis_x = ax;
        m.axis_y = ay;
        m.values = vals;

        printf("%02X\n", rx8_3d_lookup_fp_8bit(&m, x, y));
    }
    return 0;
}
