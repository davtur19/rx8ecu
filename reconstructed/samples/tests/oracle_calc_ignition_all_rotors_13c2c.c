/* ============================================================================
 * oracle_calc_ignition_all_rotors_13c2c.c — host rig for
 * rx8_calc_ignition_all_rotors_13c2c @0x13C2C
 * ============================================================================
 * Compile together with samples/src/rx8_calc_ignition_all_rotors_13c2c.c and
 * pipe test vectors on stdin; one vector per line, whitespace-separated hex
 * tokens (floats shipped as raw IEEE-754 single-precision bits so the round
 * trip through the pipe is exact on both sides):
 *
 *     ign <a740> <a748> <a749> <a75c0> <b5a4> <bb55> <bca9>
 *         <c0c4> <c0c5> <c0c7> <a73c> <a744> <b5b8> <a74c0> <a7500> <a7540>
 *                                              -> <a73c> <a744> <a734> <a738>
 *                                                 <a750> <a754> <a74c> <a75c>
 *
 *   a740/a748/a749/a75c0/b5a4/bb55/bca9/c0c4/c0c5/c0c7 : the ten input bytes
 *       (RAM[0xFFFFA740 / A748 / A749 / A75C / B5A4 / BB55 / BCA9 / C0C4 /
 *       C0C5 / C0C7])
 *   a73c, a744, b5b8  : float bits of the input RAM cells
 *       RAM[0xFFFFA73C engine speed / clamp input] (read and re-written),
 *       RAM[0xFFFFA744 previous timing] (read and re-written),
 *       RAM[0xFFFFB5B8 RPM]
 *   a74c0, a7500, a7540 : pre-state of the scratch floats
 *       RAM[0xFFFFA74C] (written only on the knock-detected==0 path),
 *       RAM[0xFFFFA750 / 0xFFFFA754] (always re-written by helper 0x13EE6)
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the pages
 * backing the RAM cells AND the two ROM pages the function reads (the 1-D
 * table descriptors @0x6B664..0x6B6B4 and the calibration/table-data page
 * @0x79838..0x7995C), seeds every byte and prints the eight post-state cells.
 * It contains NO copy of the function logic — that lives solely in the
 * reconstructed source under test — but it DOES supply the one extern the
 * source relies on: `rx8_table1d_lookup`, the faithful host model of the ROM's
 * generic 1-D lookup @0x2068 restricted to the type-4 (u8 cell) tables this
 * function uses (see the .c header's "FP EXACTNESS" block: axis search
 * @0x2624 with `!(x < axis[last])` NaN/+inf high-clamp, one-fsub-then-fused-
 * fmac interp `fmaf(t, v1 - v0, v0)` with the t == 0.0 fast path, then the
 * scale/offset fmac `fmaf(scale, interp, off)`).  On the emulator side the
 * REAL ROM bytes of 0x2068 run instead.
 *
 * The two ROM pages are NOT shipped inline: they are MAP_FIXED-mapped at the
 * same virtual addresses the ROM fetches and seeded once from the stock
 * 60E1D400.bin file with an explicit byte copy (the file is big-endian; the
 * source reads it back with big-endian byte assembly, so a raw host pointer
 * copy of the raw bytes is exactly what the source expects).  Offsets here ==
 * virtual addresses on this ROM image.  $RX8_ROM_PATH (set by the harness)
 * points at roms/stock/60E1D400.bin.
 *
 * Pages mapped:
 *   0x0006B000  ROM 1-D descriptors @0x6B664/0x6B678/0x6B68C/0x6B6A0/0x6B6B4
 *   0x00079000  ROM cal page: 0x79838/0x7983B u8, 0x79878..0x798A0 f32,
 *               axis/value arrays @0x798A4..0x7995C
 *   0xFFFFA000  RAM[0xFFFFA734..0xFFFFA75C] (all I/O cells)
 *   0xFFFFB000  RAM[0xFFFFB5A4/B5B8], RAM[0xFFFFBB55], RAM[0xFFFFBCA9]
 *   0xFFFFC000  RAM[0xFFFFC0C4/C0C5/C0C7]
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <math.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_calc_ignition_all_rotors_13c2c is not (yet) in rx8_samples.h — the
 * shared header is owned by the samples build.  The reconstructed source
 * itself carries the authoritative definition
 * (src/rx8_calc_ignition_all_rotors_13c2c.c); this prototype mirrors it. */
void rx8_calc_ignition_all_rotors_13c2c(void);

/* RAM cell addresses (see the .c header) */
#define RAM_LEAD_ADDR    0xFFFFA734u   /* f32 rotor lead  (out)             */
#define RAM_TRL_ADDR     0xFFFFA738u   /* f32 rotor trail (out)             */
#define RAM_CLAMP_ADDR   0xFFFFA73Cu   /* f32 clamp input (in) / result     */
#define RAM_ENABLE_ADDR  0xFFFFA740u   /* u8  ignition enable               */
#define RAM_TIMING_ADDR  0xFFFFA744u   /* f32 previous timing (in) / result */
#define RAM_FAULT_ADDR   0xFFFFA748u   /* u8  knock sensor fault            */
#define RAM_DETECT_ADDR  0xFFFFA749u   /* u8  knock detected                */
#define RAM_SCRATCH_ADDR 0xFFFFA74Cu   /* f32 light-retard scratch          */
#define RAM_LK1_ADDR     0xFFFFA750u   /* f32 0x13EE6 lookup1 scratch       */
#define RAM_LK2_ADDR     0xFFFFA754u   /* f32 0x13EE6 lookup2 scratch       */
#define RAM_ACTIVE_ADDR  0xFFFFA75Cu   /* u8  knock active (in) / r14 copy  */
#define RAM_RPM_ADDR     0xFFFFB5B8u   /* f32 RPM                           */
#define RAM_B5A4_ADDR    0xFFFFB5A4u   /* u8  0x13E6C table-select status    */
#define RAM_BB55_ADDR    0xFFFFBB55u   /* u8  0x13E6C table-select status    */
#define RAM_BCA9_ADDR    0xFFFFBCA9u   /* u8  0x13E6C table-select status    */
#define RAM_C0C4_ADDR    0xFFFFC0C4u   /* u8  ECT status                    */
#define RAM_C0C5_ADDR    0xFFFFC0C5u   /* u8  ECT corr-enable               */
#define RAM_C0C7_ADDR    0xFFFFC0C7u   /* u8  knock counter                 */

/* ROM pages the reconstructed source dereferences (descriptors + cal data). */
#define ROM_DESC_PAGE    0x0006B000u
#define ROM_CAL_PAGE     0x00079000u

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

/* Copy one ROM page (raw big-endian bytes) into a mapped virtual page.  The
 * reconstructed source reads these bytes back with explicit big-endian
 * assembly (rom_u8/rom_f32), so a raw copy of the file bytes is exactly what
 * it expects.  On this image, ROM file offset == virtual address. */
static void seed_rom_page(int fd, uint32_t va)
{
    unsigned char buf[4096];

    if (pread(fd, buf, sizeof buf, va) != (ssize_t)sizeof buf) {
        perror("pread ROM page");
        exit(2);
    }
    memcpy((void *)(uintptr_t)va, buf, sizeof buf);
}

/* ---- big-endian byte reads on the mapped pages ---- */
static uint8_t rb(uint32_t a)          { return *(const uint8_t *)(uintptr_t)a; }
static uint32_t r32(uint32_t a)
{
    return ((uint32_t)rb(a) << 24) | ((uint32_t)rb(a + 1) << 16)
         | ((uint32_t)rb(a + 2) << 8) | (uint32_t)rb(a + 3);
}
static float rf32(uint32_t a)
{
    uint32_t u = r32(a);
    float f;
    memcpy(&f, &u, sizeof f);
    return f;
}

/* ============================================================================
 * rx8_table1d_lookup — faithful host model of ROM 0x2068 restricted to the
 * type-4 (u8 cell) tables of this function (see the .c header "FP EXACTNESS"
 * block).  The emulator harness instead runs the ACTUAL ROM bytes of 0x2068.
 *
 *   axis search @0x2624: `!(x < axis[last])` clamps NaN/+inf high exactly like
 *   the ROM's fcmp/gt; t = (x - axis[i])/(axis[i+1] - axis[i]) is two fsubs +
 *   one fdiv.
 *   type-4 handler @0x26B0: one fsub then one fused fmac (single rounding
 *   each) -> fmaf(t, v1 - v0, v0), with the t == 0.0 fast path.
 *   0x2068 tail: scale/offset with one more fmac -> fmaf(scale, interp, off).
 * ==========================================================================*/
float rx8_table1d_lookup(const void *desc, float x)
{
    uint32_t d = (uint32_t)(uintptr_t)desc;
    int cnt = ((int)rb(d) << 8) | rb(d + 1);
    uint8_t typ = rb(d + 2);
    uint32_t axis = r32(d + 4);
    uint32_t vals = r32(d + 8);
    float scale = rf32(d + 12);
    float off = rf32(d + 16);
    int i;
    float t;

    if (typ != 4) {
        fprintf(stderr, "rx8_table1d_lookup: unsupported type %u @0x%08X\n",
                typ, d);
        return 0.0f;
    }

    if (!(x < rf32(axis + 4 * (cnt - 1)))) {        /* NaN/+inf clamps high  */
        i = cnt - 1;
        t = 0.0f;
    } else if (x < rf32(axis)) {                    /* clamps low            */
        i = 0;
        t = 0.0f;
    } else {
        for (i = 0; i + 1 < cnt; i++) {
            if (rf32(axis + 4 * i) <= x && x < rf32(axis + 4 * (i + 1)))
                break;
        }
        t = (x - rf32(axis + 4 * i))
          / (rf32(axis + 4 * (i + 1)) - rf32(axis + 4 * i));
    }

    {
        float v0 = (float)rb(vals + i);
        float interp;
        if (t == 0.0f) {
            interp = v0;
        } else {
            float v1 = (float)rb(vals + i + 1);
            interp = fmaf(t, v1 - v0, v0);
        }
        return fmaf(scale, interp, off);
    }
}

static void store_f32(uint32_t addr, uint32_t bits)
{
    float f;
    memcpy(&f, &bits, sizeof f);
    *(volatile float *)(uintptr_t)addr = f;
}

static uint32_t read_f32(uint32_t addr)
{
    float f = *(volatile float *)(uintptr_t)addr;
    uint32_t u;
    memcpy(&u, &f, sizeof u);
    return u;
}

int main(void)
{
    const char *rom_path = getenv("RX8_ROM_PATH");
    char line[512];
    int romfd;

    if (!rom_path)
        rom_path = "../../../roms/stock/60E1D400.bin";
    romfd = open(rom_path, O_RDONLY);
    if (romfd < 0) {
        perror(rom_path);
        return 2;
    }

    /* ROM pages (anonymous, seeded from the file — see above). */
    map_page(ROM_DESC_PAGE);
    map_page(ROM_CAL_PAGE);
    seed_rom_page(romfd, ROM_DESC_PAGE);
    seed_rom_page(romfd, ROM_CAL_PAGE);
    /* RAM pages. */
    map_page(RAM_LEAD_ADDR);
    map_page(RAM_RPM_ADDR);
    map_page(RAM_C0C4_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long a740, a748, a749, a75c0, b5a4, bb55, bca9;
        unsigned long c0c4, c0c5, c0c7;
        unsigned long a73c, a744, b5b8, a74c0, a7500, a7540;

        if (sscanf(line,
                   "ign %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx "
                   "%lx %lx %lx %lx %lx %lx",
                   &a740, &a748, &a749, &a75c0, &b5a4, &bb55, &bca9,
                   &c0c4, &c0c5, &c0c7,
                   &a73c, &a744, &b5b8, &a74c0, &a7500, &a7540) != 16) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the input RAM cells (bytes + float bits). */
        *(volatile uint8_t *)(uintptr_t)RAM_ENABLE_ADDR  = (uint8_t)a740;
        *(volatile uint8_t *)(uintptr_t)RAM_FAULT_ADDR   = (uint8_t)a748;
        *(volatile uint8_t *)(uintptr_t)RAM_DETECT_ADDR  = (uint8_t)a749;
        *(volatile uint8_t *)(uintptr_t)RAM_ACTIVE_ADDR  = (uint8_t)a75c0;
        *(volatile uint8_t *)(uintptr_t)RAM_B5A4_ADDR    = (uint8_t)b5a4;
        *(volatile uint8_t *)(uintptr_t)RAM_BB55_ADDR    = (uint8_t)bb55;
        *(volatile uint8_t *)(uintptr_t)RAM_BCA9_ADDR    = (uint8_t)bca9;
        *(volatile uint8_t *)(uintptr_t)RAM_C0C4_ADDR    = (uint8_t)c0c4;
        *(volatile uint8_t *)(uintptr_t)RAM_C0C5_ADDR    = (uint8_t)c0c5;
        *(volatile uint8_t *)(uintptr_t)RAM_C0C7_ADDR    = (uint8_t)c0c7;
        store_f32(RAM_CLAMP_ADDR,   (uint32_t)a73c);
        store_f32(RAM_TIMING_ADDR,  (uint32_t)a744);
        store_f32(RAM_RPM_ADDR,     (uint32_t)b5b8);
        store_f32(RAM_SCRATCH_ADDR, (uint32_t)a74c0);
        store_f32(RAM_LK1_ADDR,     (uint32_t)a7500);
        store_f32(RAM_LK2_ADDR,     (uint32_t)a7540);

        rx8_calc_ignition_all_rotors_13c2c();

        printf("%08X %08X %08X %08X %08X %08X %08X %02X\n",
               read_f32(RAM_CLAMP_ADDR),
               read_f32(RAM_TIMING_ADDR),
               read_f32(RAM_LEAD_ADDR),
               read_f32(RAM_TRL_ADDR),
               read_f32(RAM_LK1_ADDR),
               read_f32(RAM_LK2_ADDR),
               read_f32(RAM_SCRATCH_ADDR),
               *(volatile uint8_t *)(uintptr_t)RAM_ACTIVE_ADDR);
    }
    return 0;
}
