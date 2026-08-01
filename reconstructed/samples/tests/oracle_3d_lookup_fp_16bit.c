/* ============================================================================
 * oracle_3d_lookup_fp_16bit.c  —  host test rig for rx8_three_d_lookup_fp_16bit
 * ============================================================================
 * Compile together with src/rx8_3d_lookup_fp_16bit.c and pipe test vectors on
 * stdin.  Stateful protocol (the map grid is shipped once per map):
 *
 *     map <id> <cx> <cy> <ax0..axcx-1> <ay0..aycy-1> <v0..vcx*cy-1>
 *         all tokens hex; floats as their raw IEEE-754 bits, cells as u16.
 *     xy  <id> <xbits> <ybits>
 *         -> <result u16>
 *
 * The oracle contains NO copy of the function logic — it only parses the
 * descriptor and calls the reconstructed source under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "rx8_samples.h"

/* Map2D descriptor as consumed by rx8_three_d_lookup_fp_16bit (28 bytes on
 * the SH-2E; same layout on the host).  Declared here so this TU is
 * self-contained; the source under test carries an identical typedef. */
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
} Rx8Map2D;

extern uint16_t rx8_three_d_lookup_fp_16bit(const Rx8Map2D *m, float x, float y);

#define N_MAPS 8
#define N_AXIS 64
#define N_CELL (N_AXIS * N_AXIS)

static float    ax[N_MAPS][N_AXIS];
static float    ay[N_MAPS][N_AXIS];
static uint16_t val[N_MAPS][N_CELL];
static Rx8Map2D mtab[N_MAPS];
static int      have[N_MAPS];

static uint32_t next_hex(char **pp)
{
    char *p = *pp;
    while (*p == ' ' || *p == '\t') p++;
    if (!*p) return 0;
    char *end;
    unsigned long v = strtoul(p, &end, 16);
    *pp = end;
    return (uint32_t)v;
}

static float bits2f(uint32_t b)
{
    float f;
    memcpy(&f, &b, 4);
    return f;
}

static void do_map(char *p)
{
    uint32_t id = next_hex(&p);
    uint32_t cx = next_hex(&p);
    uint32_t cy = next_hex(&p);
    uint32_t i, nv = cx * cy;

    if (id >= N_MAPS || cx > N_AXIS || cy > N_AXIS || nv > N_CELL) {
        fprintf(stderr, "map out of range: id=%u cx=%u cy=%u\n", id, cx, cy);
        exit(2);
    }
    for (i = 0; i < cx; i++) ax[id][i] = bits2f(next_hex(&p));
    for (i = 0; i < cy; i++) ay[id][i] = bits2f(next_hex(&p));
    for (i = 0; i < nv; i++) val[id][i] = (uint16_t)next_hex(&p);

    mtab[id].count_x = (uint16_t)cx;
    mtab[id].count_y = (uint16_t)cy;
    mtab[id].axis_x  = ax[id];
    mtab[id].axis_y  = ay[id];
    mtab[id].values  = val[id];
    mtab[id].type    = 8;    /* u16 cells — unused by the function */
    mtab[id].scale   = 0.0f; /* unused by the function              */
    mtab[id].offset  = 0.0f; /* unused by the function              */
    have[id] = 1;
}

int main(void)
{
    char line[16384];

    while (fgets(line, sizeof line, stdin)) {
        if (!strncmp(line, "map", 3)) {
            do_map(line + 3);
        } else if (!strncmp(line, "xy", 2)) {
            char *p = line + 2;
            uint32_t id = next_hex(&p);
            uint32_t xb = next_hex(&p);
            uint32_t yb = next_hex(&p);
            if (id >= N_MAPS || !have[id]) {
                fprintf(stderr, "xy for unknown map %u\n", id);
                return 2;
            }
            printf("%04X\n",
                   (unsigned)rx8_three_d_lookup_fp_16bit(
                       &mtab[id], bits2f(xb), bits2f(yb)));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
