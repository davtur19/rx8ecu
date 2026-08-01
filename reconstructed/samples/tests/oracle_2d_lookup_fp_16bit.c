/* ============================================================================
 * oracle_2d_lookup_fp_16bit.c — host test rig for rx8_2d_lookup_fp_16bit
 * ============================================================================
 * Compile together with src/rx8_2d_lookup_fp_16bit.c and pipe test vectors
 * on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     2d <desc_addr> <x_bits>                -> <result>
 *
 *   desc_addr : file offset of a real 1-D Map descriptor in the ROM (the
 *               emulator maps the binary 1:1, so file offset == ROM address)
 *   x_bits    : raw IEEE-754 single-precision bits of the input x — passed
 *               as bits so float->hex round-trips exactly on both sides of
 *               the pipe
 *
 * The oracle re-implements the *caller-side* set-up only: it loads the same
 * ROM image, parses the 20-byte descriptor header at desc_addr and hands the
 * reconstructed function a host-native copy of the axis/cells (the ROM
 * stores both big-endian, the host is little-endian, so the byte-swap below
 * is part of the setup, not of the logic).  It contains NO copy of the
 * lookup logic.  The descriptor struct is duplicated here from
 * src/rx8_2d_lookup_fp_16bit.c and MUST stay in sync with it.
 *
 * Usage: oracle_2d_lookup_fp_16bit [rom_path]
 *        (rom_path defaults to roms/stock/60E1D400.bin relative to CWD)
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rx8_samples.h"

/* Duplicate of the descriptor struct in src/rx8_2d_lookup_fp_16bit.c. */
typedef struct {
    uint16_t     count;
    uint8_t      type;
    uint8_t      _pad;
    const float *axis;
    const void  *values;
    float        scale;
    float        offset;
} Rx8Map1D;

/* 0x20C4 — 1-D lookup, float axis, u16 cells, no scale/offset. */
uint16_t rx8_2d_lookup_fp_16bit(const Rx8Map1D *m, float x);

#define MAX_CELLS 256

static const unsigned char *g_rom;
static size_t g_romlen;
static float     g_axis_buf[MAX_CELLS];   /* host-endian copies (see above) */
static uint16_t  g_vals_buf[MAX_CELLS];

static uint16_t be16(size_t p)
{
    return (uint16_t)(((uint16_t)g_rom[p] << 8) | g_rom[p + 1]);
}

static uint32_t be32(size_t p)
{
    return ((uint32_t)g_rom[p] << 24) | ((uint32_t)g_rom[p + 1] << 16)
         | ((uint32_t)g_rom[p + 2] << 8) | (uint32_t)g_rom[p + 3];
}

static int load_rom(const char *path)
{
    FILE *f = fopen(path, "rb");
    long n;
    unsigned char *buf;

    if (!f) {
        perror(path);
        return -1;
    }
    if (fseek(f, 0, SEEK_END) != 0 || (n = ftell(f)) < 0 ||
        fseek(f, 0, SEEK_SET) != 0) {
        perror("fseek/ftell");
        fclose(f);
        return -1;
    }
    buf = malloc((size_t)(n > 0 ? n : 1));
    if (!buf) {
        fclose(f);
        return -1;
    }
    if (fread(buf, 1, (size_t)n, f) != (size_t)n) {
        perror("fread");
        fclose(f);
        return -1;
    }
    fclose(f);
    g_rom = buf;
    g_romlen = (size_t)n;
    return 0;
}

static int build_map(Rx8Map1D *m, size_t desc)
{
    uint32_t axp, vp, count;
    uint32_t k;

    if (desc + 20 > g_romlen) {
        fprintf(stderr, "descriptor 0x%lX out of ROM\n", (unsigned long)desc);
        return -1;
    }
    count = be16(desc);
    axp = be32(desc + 4);
    vp = be32(desc + 8);
    if (count == 0 || count > MAX_CELLS) {
        fprintf(stderr, "bad count %lu @0x%lX\n",
                (unsigned long)count, (unsigned long)desc);
        return -1;
    }
    if ((size_t)axp + (size_t)count * 4 > g_romlen ||
        (size_t)vp + (size_t)count * 2 > g_romlen) {
        fprintf(stderr, "axis/values out of ROM @0x%lX\n", (unsigned long)desc);
        return -1;
    }
    /* ROM is big-endian; host-native copies for the reconstructed function. */
    for (k = 0; k < count; k++) {
        uint32_t bits = be32(axp + 4 * k);
        memcpy(&g_axis_buf[k], &bits, sizeof g_axis_buf[k]);
        g_vals_buf[k] = be16(vp + 2 * k);
    }

    m->count = (uint16_t)count;
    m->type = g_rom[desc + 2];
    m->_pad = g_rom[desc + 3];
    m->axis = g_axis_buf;
    m->values = g_vals_buf;
    m->scale = 0.0f;    /* never read by rx8_2d_lookup_fp_16bit */
    m->offset = 0.0f;   /* never read by rx8_2d_lookup_fp_16bit */
    return 0;
}

int main(int argc, char **argv)
{
    const char *rom_path = argc > 1 ? argv[1] : "roms/stock/60E1D400.bin";
    char line[256];

    if (load_rom(rom_path) != 0) {
        fprintf(stderr, "cannot load %s\n", rom_path);
        return 1;
    }

    while (fgets(line, sizeof line, stdin)) {
        unsigned long desc, xbits;
        uint32_t ub;
        float x;
        Rx8Map1D m;
        uint16_t result;

        if (sscanf(line, "2d %lx %lx", &desc, &xbits) != 2) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        if (build_map(&m, (size_t)desc) != 0) {
            return 2;
        }
        ub = (uint32_t)xbits;
        memcpy(&x, &ub, sizeof x);          /* exact float from raw bits */

        result = rx8_2d_lookup_fp_16bit(&m, x);
        printf("%04X\n", (unsigned)result);
    }
    return 0;
}
