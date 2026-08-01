/* ============================================================================
 * oracle_vis_intake_control.c  —  host rig for rx8_vis_intake_control
 * ============================================================================
 * Compile together with samples/src/rx8_vis_intake_control.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     vis <x> <y> <selc> <seld> <sele> <b5c8> <cmode>
 *         <t0> <t1> ... <t13>               -> <t0> ... <t13> <idx>
 *
 *   x,y,b5c8,t0..t13 : f32 inputs / table pre-states as raw 8-hex-digit bits
 *   selc,seld,sele   : the three Map2D selector bytes (RAM[0xFFFFB33C/D/E])
 *   cmode            : the counter-mode cal byte (ROM[0x73F68]); stock is 1
 *   idx              : table index byte the function publishes (RAM[0xFFFFB45C])
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the pages
 * backing the RAM cells AND the ROM descriptor/calibration pages, translates
 * the ROM's big-endian, 32-bit-pointer Map2D descriptors + axis/value arrays
 * into host-native form at their fixed addresses, seeds the input cells and
 * prints the 14 post-state table cells + index.  It contains NO copy of the
 * function logic — that lives solely in the reconstructed source under test.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x0006A000  ROM Map2D descriptors     (0x6AC60/0x6AC7C/0x6AC98/0x6ACB4)
 *   0x00073000  ROM calibration constants  (0x73F68/0x73F6C/0x73F74/0x73F78)
 *   0x00074000  ROM axis + values grids    (0x741B4..0x74FF4)
 *   0xFFFFA000  RAM[0xFFFFAA40] y input
 *   0xFFFFB000  RAM table 0xFFFFB408..0xFFFFB45C + 0xFFFFB5B8/B5C8
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_vis_intake_control is not in rx8_samples.h — the reconstructed source
 * itself carries the authoritative definition (src/rx8_vis_intake_control.c);
 * this prototype mirrors it exactly. */
void rx8_vis_intake_control(void);

#define RAM_X_ADDR      0xFFFFB5B8u
#define RAM_Y_ADDR      0xFFFFAA40u
#define RAM_SEL_C_ADDR  0xFFFFB33Cu
#define RAM_SEL_D_ADDR  0xFFFFB33Du
#define RAM_SEL_E_ADDR  0xFFFFB33Eu
#define RAM_TABLE_ADDR  0xFFFFB408u
#define RAM_IDX_ADDR    0xFFFFB45Cu
#define RAM_DP_IN_ADDR  0xFFFFB5C8u
#define ROM_CMODE_ADDR  0x00073F68u
#define ROM_CLAMP_ADDR  0x00073F6Cu   /* f32 84.0 */
#define ROM_DP_SC_ADDR  0x00073F74u   /* f32 2.0  */
#define ROM_DP_OF_ADDR  0x00073F78u   /* f32 2.0  */

/* The Map2D descriptor exactly as the reconstructed source declares it: the
 * ROM's 28-byte big-endian layout with 32-bit *address* fields (the four
 * descriptors at 0x6AC60/7C/98/B4 are only 28 bytes apart, so this struct
 * must stay exactly 28 bytes with no padding).  setup_rom() translates the
 * big-endian bytes to host-native in place. */
typedef struct {
    uint16_t          count_x;   /* +0  X-axis breakpoints                  */
    uint16_t          count_y;   /* +2  Y-axis breakpoints                  */
    uint32_t          axis_x;    /* +4  ROM address of the f32 axis         */
    uint32_t          axis_y;    /* +8  ROM address of the f32 axis         */
    uint32_t          values;    /* +12 ROM address of the u16 grid         */
    uint8_t           type;      /* +16 8 = u16 cells (the VIS maps)        */
    uint8_t           _pad[3];
    float             scale;     /* +20 result = scale*interp + offset      */
    float             offset;    /* +24                                     */
} rx8_map2d_t;

static void map_page(uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);
    void *p = mmap((void *)base, (size_t)page, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) {
        perror("mmap");
        exit(1);
    }
}

/* Copy the ROM file bytes over the mapped ROM pages, then translate every
 * big-endian 32-bit-pointer Map2D descriptor (+ its axis/value arrays) and
 * the calibration floats into host-native form, in place. */
static void setup_rom(const char *path)
{
    static const uintptr_t pages[] = { 0x0006A000u, 0x00073000u, 0x00074000u };
    long page = sysconf(_SC_PAGESIZE);
    FILE *f = fopen(path, "rb");
    if (!f) { perror(path); exit(1); }
    for (size_t i = 0; i < sizeof pages / sizeof pages[0]; i++) {
        unsigned char buf[8192];
        map_page(pages[i]);
        if (fseek(f, (long)pages[i], SEEK_SET) != 0) { perror("fseek"); exit(1); }
        size_t got = fread(buf, 1, (size_t)page, f);
        memcpy((void *)pages[i], buf, got);
    }
    fclose(f);

    /* Calibration floats: ROM big-endian -> host-native.  cmode at 0x73F68 is
     * a byte (no swap); the harness overrides it per vector. */
    static const uintptr_t cal_floats[3] = {
        0x00073F6Cu, 0x00073F74u, 0x00073F78u
    };
    for (unsigned k = 0; k < 3; k++) {
        uint8_t *p = (uint8_t *)cal_floats[k];
        uint8_t t = p[0]; p[0] = p[3]; p[3] = t;
        t = p[1]; p[1] = p[2]; p[2] = t;
    }

    /* Each of the four Map2D descriptors. */
    static const uintptr_t descs[4] = {
        0x0006AC60u, 0x0006AC7Cu, 0x0006AC98u, 0x0006ACB4u
    };
    for (int d = 0; d < 4; d++) {
        const uint8_t *be = (const uint8_t *)descs[d];

        /* Read the big-endian 32-bit-pointer descriptor. */
        uint16_t count_x = (uint16_t)((be[0] << 8) | be[1]);
        uint16_t count_y = (uint16_t)((be[2] << 8) | be[3]);
        uint32_t axp = ((uint32_t)be[4] << 24) | ((uint32_t)be[5] << 16)
                     | ((uint32_t)be[6] << 8)  | (uint32_t)be[7];
        uint32_t ayp = ((uint32_t)be[8] << 24) | ((uint32_t)be[9] << 16)
                     | ((uint32_t)be[10] << 8) | (uint32_t)be[11];
        uint32_t vp  = ((uint32_t)be[12] << 24) | ((uint32_t)be[13] << 16)
                     | ((uint32_t)be[14] << 8)  | (uint32_t)be[15];
        uint8_t  type = be[16];
        uint32_t scale_be, off_be;
        memcpy(&scale_be, be + 20, 4);
        memcpy(&off_be,  be + 24, 4);
        /* Byte-swap the axis float arrays and the u16 value grid in place. */
        for (unsigned i = 0; i < count_x; i++) {
            uint8_t *p = (uint8_t *)(uintptr_t)(axp + 4u * i);
            uint8_t t = p[0]; p[0] = p[3]; p[3] = t;
            t = p[1]; p[1] = p[2]; p[2] = t;
        }
        for (unsigned i = 0; i < count_y; i++) {
            uint8_t *p = (uint8_t *)(uintptr_t)(ayp + 4u * i);
            uint8_t t = p[0]; p[0] = p[3]; p[3] = t;
            t = p[1]; p[1] = p[2]; p[2] = t;
        }
        for (unsigned i = 0; i < (unsigned)count_x * count_y; i++) {
            uint8_t *p = (uint8_t *)(uintptr_t)(vp + 2u * i);
            uint8_t t = p[0]; p[0] = p[1]; p[1] = t;
        }

        /* scale/offset are big-endian f32 in the ROM: swap the bits before
         * re-storing as host-native floats in the rewritten descriptor. */
        uint32_t scale_hi = __builtin_bswap32(scale_be);
        uint32_t off_hi   = __builtin_bswap32(off_be);
        float scale, off;
        memcpy(&scale, &scale_hi, 4);
        memcpy(&off, &off_hi, 4);

        /* Rewrite the descriptor in host-native form (address fields keep
         * their numeric ROM values; they are cast to pointers on deref). */
        rx8_map2d_t *m = (rx8_map2d_t *)descs[d];
        m->count_x = count_x;
        m->count_y = count_y;
        m->axis_x  = axp;
        m->axis_y  = ayp;
        m->values  = vp;
        m->type    = type;
        m->scale   = scale;
        m->offset  = off;
    }
}

/* Host RAM cells are native floats (the reconstructed C reads them through
 * `*(volatile float*)`): store the raw 32-bit pattern as-is. */
static void wf(uintptr_t addr, uint32_t bits)
{
    *(volatile uint32_t *)(uintptr_t)addr = bits;
}

static uint32_t rf(uintptr_t addr)
{
    return *(volatile uint32_t *)(uintptr_t)addr;
}

int main(int argc, char **argv)
{
    char line[512];

    if (argc < 2) {
        fprintf(stderr, "usage: %s <rom.bin>\n", argv[0]);
        return 2;
    }
    setup_rom(argv[1]);
    map_page(0xFFFFA000u);
    map_page(0xFFFFB000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long x, y, selc, seld, sele, b5c8, cmode;
        unsigned long t[14];
        int n = sscanf(line,
                       "vis %lx %lx %lx %lx %lx %lx %lx "
                       "%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                       &x, &y, &selc, &seld, &sele, &b5c8, &cmode,
                       &t[0], &t[1], &t[2], &t[3], &t[4], &t[5], &t[6],
                       &t[7], &t[8], &t[9], &t[10], &t[11], &t[12], &t[13]);
        if (n != 21) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the ROM cmode byte (stock 0x01; 0x00 exercises the dead path). */
        *(volatile uint8_t *)(uintptr_t)ROM_CMODE_ADDR = (uint8_t)cmode;

        /* Seed the input cells + the table pre-states. */
        wf(RAM_X_ADDR,      (uint32_t)x);
        wf(RAM_Y_ADDR,      (uint32_t)y);
        *(volatile uint8_t *)(uintptr_t)RAM_SEL_C_ADDR = (uint8_t)selc;
        *(volatile uint8_t *)(uintptr_t)RAM_SEL_D_ADDR = (uint8_t)seld;
        *(volatile uint8_t *)(uintptr_t)RAM_SEL_E_ADDR = (uint8_t)sele;
        wf(RAM_DP_IN_ADDR,  (uint32_t)b5c8);
        for (int i = 0; i < 14; i++)
            wf(RAM_TABLE_ADDR + 4u * (uint32_t)i, (uint32_t)t[i]);

        rx8_vis_intake_control();

        for (int i = 0; i < 14; i++)
            printf("%08X ", rf(RAM_TABLE_ADDR + 4u * (uint32_t)i));
        printf("%02X\n",
               *(volatile uint8_t *)(uintptr_t)RAM_IDX_ADDR);
    }
    return 0;
}
