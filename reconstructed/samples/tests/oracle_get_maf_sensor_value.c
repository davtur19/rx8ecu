/* ============================================================================
 * oracle_get_maf_sensor_value.c  —  host test rig for rx8_get_maf_sensor_value
 * ============================================================================
 * Compile together with src/rx8_get_maf_sensor_value.c and pipe test vectors
 * on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     maf <adc>                    -> <flow_bits> <status>
 *
 *   adc       : 16-bit MAF raw ADC count (0x0000..0xFFFF).  The oracle places
 *               it at RAM[0xFFFF9EEA] (u16), calls the function under test and
 *               reports the two RAM side-effects it leaves behind:
 *               flow   = raw IEEE-754 single-precision bits of RAM[0xFFFF9F78]
 *               status = byte RAM[0xFFFF9F7C] (0=OK, 1=high, 2=low)
 *
 * The oracle contains NO copy of rx8_get_maf_sensor_value's logic — that lives
 * solely in src/rx8_get_maf_sensor_value.c.  It mirrors the *caller-side*
 * set-up: the 0xFFFF9EEA/9F78/9F7C RAM bytes are backed with mmap(MAP_FIXED)
 * pages (same trick as tests/host_oracle.c) and the ROM pages holding the MAF
 * calibration descriptor (0x6A0E4), its axis (0x6FB18) and f32 values
 * (0x6FBD8) and the two range-limit words (0x6CF02/0x6CF04) are mmap()ed from
 * the ROM file at their virtual addresses, so both sides read identical bytes.
 *
 * The one host-side piece that is NOT the function under test is
 * `rx8_twod_lookup()` — the ROM's TwoDLookup @0x2068 is a real `jsr` callee
 * whose actual bytes the EMULATOR executes, but which a host binary cannot.
 * Its type-0 semantics (axis search + f32-cell handler @0x2678, fsub then one
 * fused fmac) are already Track-A verified at 0x2068 (c/2DLookup.c) and are
 * modelled here as the callable stand-in.  See rx8_get_maf_sensor_value.c.
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <fcntl.h>
#include <math.h>

/* 0x745C — see src/rx8_get_maf_sensor_value.c. */
void rx8_get_maf_sensor_value(void);

#define RX8_MAF_ADC_ADDR      0xFFFF9EEAu
#define RX8_MAF_FLOW_ADDR     0xFFFF9F78u
#define RX8_MAF_STATUS_ADDR   0xFFFF9F7Cu

/* ROM file backing the calibration pages (overridable; default = repo stock
 * ROM that the harness loads into the emulator). */
#ifndef ROM_PATH
#define ROM_PATH "/home/davide/ailocal/rx8ecu/roms/stock/60E1D400.bin"
#endif

/* ---- big-endian helpers (SH-2E ROM is big-endian) ----------------------- */
static uint16_t be16(const uint8_t *p)
{
    return (uint16_t)((uint16_t)p[0] << 8) | p[1];
}

static uint32_t be32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16)
         | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

static float befloat(const uint8_t *p)
{
    uint32_t u = be32(p);
    float f;
    memcpy(&f, &u, sizeof f);
    return f;
}

/* TwoDLookup @0x2068, type-0 (f32 cells) path only — the MAF descriptor is
 * type 0.  Semantics per the verified lift c/2DLookup.c TwoDLookup + f32
 * handler @0x2678: axis search clamps low/high (NaN clamps high), then
 * interp = fmaf(t, v1 - v0, v0) with a t==0 fast path returning v0 verbatim. */
float rx8_twod_lookup(const void *desc_ptr, float x)
{
    const uint8_t *d = (const uint8_t *)desc_ptr;
    int n = (int)be16(d);                 /* +0 count                       */
    const uint8_t *axis = (const uint8_t *)(uintptr_t)be32(d + 4);   /* +4 */
    const uint8_t *values = (const uint8_t *)(uintptr_t)be32(d + 8); /* +8 */
    int i;
    float t, v0, v1;

    /* Axis search (helper @0x2624).  `!(x < axis[n-1])` reproduces the ROM's
     * fcmp/gt exactly, so NaN clamps high like the hardware. */
    if (!(x < befloat(axis + (n - 1) * 4))) { i = n - 1; t = 0.0f; }
    else if (x < befloat(axis))             { i = 0;     t = 0.0f; }
    else {
        i = 0;
        while (i + 1 < n &&
               !(befloat(axis + 4 * i) <= x && x < befloat(axis + 4 * (i + 1))))
            i++;
        t = (x - befloat(axis + 4 * i)) /
            (befloat(axis + 4 * (i + 1)) - befloat(axis + 4 * i));
    }

    v0 = befloat(values + 4 * i);
    v1 = befloat(values + 4 * (i + 1 < n ? i + 1 : i));

    /* f32 handler @0x2678: fcmp/eq t,0 -> return cells[i] verbatim; else one
     * fsub (single rounding) + one fused fmac (single rounding). */
    if (t == 0.0f) return v0;
    return fmaf(t, v1 - v0, v0);
}

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

static void map_rom_page(int fd, uintptr_t addr)
{
    long page = sysconf(_SC_PAGESIZE);
    uintptr_t base = addr & ~((uintptr_t)page - 1);
    void *p = mmap((void *)base, (size_t)page, PROT_READ,
                   MAP_PRIVATE | MAP_FIXED, fd, (off_t)base);
    if (p == MAP_FAILED) {
        perror("mmap(rom)");
        exit(1);
    }
}

static uint32_t f2b(float f)
{
    union { float f; uint32_t u; } x;
    x.f = f;
    return x.u;
}

int main(void)
{
    char line[64];
    int fd;

    /* RAM: page 0xFFFF9000 backs ADC@0xFFFF9EEA, flow@0xFFFF9F78, status@0xFFFF9F7C. */
    map_page(RX8_MAF_ADC_ADDR);

    /* ROM: calibration descriptor (0x6A0E4), limits (0x6CF02/04), axis +
     * values (0x6FB18 / 0x6FBD8) — pages 0x6A000, 0x6C000, 0x6F000. */
    fd = open(ROM_PATH, O_RDONLY);
    if (fd < 0) {
        perror(ROM_PATH);
        return 2;
    }
    map_rom_page(fd, 0x6A000u);
    map_rom_page(fd, 0x6C000u);
    map_rom_page(fd, 0x6F000u);
    close(fd);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long adc;

        if (sscanf(line, "maf %lx", &adc) == 1 && adc <= 0xFFFFu) {
            *(volatile uint16_t *)(uintptr_t)RX8_MAF_ADC_ADDR = (uint16_t)adc;
            rx8_get_maf_sensor_value();
            printf("%08X %02X\n",
                   (unsigned)f2b(*(volatile float *)(uintptr_t)RX8_MAF_FLOW_ADDR),
                   (unsigned)*(volatile uint8_t *)(uintptr_t)RX8_MAF_STATUS_ADDR);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
