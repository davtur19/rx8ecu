/* ============================================================================
 * oracle_index_lookup.c — host test rig for rx8_index_lookup @0x2658
 * ============================================================================
 * Compile together with samples/src/rx8_index_lookup.c and pipe test vectors
 * on stdin:
 *
 *     axis <id> <cx> <cy> <x0> <x1> ... <y0> <y1> ...
 *              (id: descriptor slot 0..3; axis values are 32-bit IEEE-754
 *               bit patterns, big-endian value order; cx+cy values total)
 *              -> no output (setup only)
 *
 *     lk <id> <x> <y>
 *              (id selects the slot set up earlier; x/y are float bit
 *               patterns)  ->  <ix> <iy> <tx> <ty>
 *                                (ix/iy hex, tx/ty as float bit patterns)
 *
 * The rig decodes the descriptor axes shipped by the harness (they mirror the
 * real ROM Map2D descriptors at the SAME addresses the emulator reads from,
 * so both sides see identical breakpoint arrays) and prints the four results.
 * It contains NO copy of the search logic — that lives solely in the
 * reconstructed source under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>

/* Declared locally: rx8_samples.h cannot be extended (parallel agents), and
 * this rig only needs this one function.  Struct mirrors rx8_map2d_axes_t
 * from rx8_index_lookup.c (identical layout, counts + axis pointers). */
typedef struct {
    uint16_t     count_x;
    uint16_t     count_y;
    const float *axis_x;
    const float *axis_y;
} rx8_map2d_axes_t;

void rx8_index_lookup(const rx8_map2d_axes_t *m, float x, float y,
                      int32_t *ix, int32_t *iy, float *tx, float *ty);

#define MAX_DESC 4
#define MAX_AXIS 64

static float b2f(uint32_t u)
{
    union { float f; uint32_t u; } x;
    x.u = u;
    return x.f;
}

static uint32_t f2b(float f)
{
    union { float f; uint32_t u; } x;
    x.f = f;
    return x.u;
}

typedef struct {
    uint16_t cx;
    uint16_t cy;
    float xs[MAX_AXIS];
    float ys[MAX_AXIS];
} slot_t;

static slot_t slots[MAX_DESC];

int main(void)
{
    char line[2048];

    while (fgets(line, sizeof line, stdin)) {
        char op[8];
        if (sscanf(line, "axis %7s", op) == 1) {
            /* axis <id> <cx> <cy> <x0..> <y0..> : variable arity -> tokenise */
            char *p = line;
            unsigned long vals[128 + 3];
            int tok = 0;
            while (*p) {
                char *q;
                while (*p == ' ' || *p == '\t' || *p == '\n') p++;
                if (!*p) break;
                q = p;
                while (*q && *q != ' ' && *q != '\t' && *q != '\n') q++;
                { char save = *q; *q = '\0'; vals[tok] = strtoul(p, 0, 16); *q = save; }
                p = q;
                tok++;
            }
            if (tok < 4) { fprintf(stderr, "bad axis vector: %s", line); return 2; }
            {
                unsigned long id = vals[1], cx = vals[2], cy = vals[3], k;
                if (id >= MAX_DESC || cx > MAX_AXIS || cy > MAX_AXIS ||
                    tok != 4 + (int)(cx + cy)) {
                    fprintf(stderr, "axis out of range: %s", line);
                    return 2;
                }
                slots[id].cx = (uint16_t)cx;
                slots[id].cy = (uint16_t)cy;
                for (k = 0; k < cx; k++)
                    slots[id].xs[k] = b2f((uint32_t)vals[4 + k]);
                for (k = 0; k < cy; k++)
                    slots[id].ys[k] = b2f((uint32_t)vals[4 + cx + k]);
            }
        } else if (sscanf(line, "lk %7s", op) == 1) {
            unsigned long id, xb, yb;
            if (sscanf(line, "lk %lx %lx %lx", &id, &xb, &yb) != 3) {
                fprintf(stderr, "bad lk vector: %s", line);
                return 2;
            }
            if (id >= MAX_DESC) {
                fprintf(stderr, "lk id out of range: %s", line);
                return 2;
            }
            {
                rx8_map2d_axes_t m;
                int32_t ix = 0, iy = 0;
                float tx = 0.0f, ty = 0.0f;
                m.count_x = slots[id].cx;
                m.count_y = slots[id].cy;
                m.axis_x = slots[id].xs;
                m.axis_y = slots[id].ys;
                rx8_index_lookup(&m, b2f((uint32_t)xb), b2f((uint32_t)yb),
                                 &ix, &iy, &tx, &ty);
                printf("%lX %lX %08lX %08lX\n",
                       (unsigned long)(uint32_t)ix,
                       (unsigned long)(uint32_t)iy,
                       (unsigned long)(uint32_t)f2b(tx),
                       (unsigned long)(uint32_t)f2b(ty));
            }
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
