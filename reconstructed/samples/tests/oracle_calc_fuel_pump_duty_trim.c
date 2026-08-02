/* ============================================================================
 * oracle_calc_fuel_pump_duty_trim.c  —  host rig for
 * rx8_calc_fuel_pump_duty_trim @0x135F6
 * ============================================================================
 * Compile together with samples/src/rx8_calc_fuel_pump_duty_trim.c and pipe
 * test vectors on stdin; one vector per line, whitespace-separated hex tokens
 * (floats shipped as raw IEEE-754 single-precision bits so the round trip
 * through the pipe is exact on both sides):
 *
 *     fpd <mode> <src> <base> <va> <vb> <vc> <vd> <front0> <rear0>
 *                                            -> <base> <front> <rear>
 *
 *   mode   : u8  value of the calibration mode byte at ROM[0x6E430] —
 *            the oracle re-seeds its mapped ROM cal page with this value
 *            every line (the emulator side overrides the same byte in its
 *            RAM overlay), so all three modes are exercised.
 *   src    : f32 bits of RAM[0xFFFFA63C]  (mode-0 flat-copy source)
 *   base   : f32 bits of RAM[0xFFFFA6F4]  (base duty; also mode-0 output)
 *   va/vb  : f32 bits RAM[0xFFFFA6FC / 0xFFFFA70C]  (mode-1 front comps)
 *   vc/vd  : f32 bits RAM[0xFFFFA700 / 0xFFFFA710]  (mode-1 rear comps)
 *   front0 : f32 pre-state of RAM[0xFFFFA6E4] (front duty out)
 *   rear0  : f32 pre-state of RAM[0xFFFFA6E8] (rear duty out)
 *
 * Output (one line per vector): the three post-state cells as raw f32 bits —
 *   RAM[0xFFFFA6F4] (base duty, rewritten only in mode 0),
 *   RAM[0xFFFFA6E4] (front channel duty, rewritten in modes 1/2),
 *   RAM[0xFFFFA6E8] (rear channel duty, rewritten in modes 1/2).
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the
 * pages backing the RAM cells AND the ROM calibration page, seeds every byte
 * and prints the three post-state floats.  It contains NO copy of the
 * function logic — that lives solely in the reconstructed source under test.
 *
 * The two safe-mode f32 constants @0x6E438/@0x6E43C are NOT shipped inline:
 * the ROM page holding the pump-duty cal block (0x6E430..0x6E43C) is
 * MAP_FIXED-mapped at the same virtual address the ROM uses and seeded once
 * from the ROM file with explicit big-endian assembly (the file is
 * big-endian; the host is little-endian, so a raw pointer read of an f32
 * would byte-swap — this is why the bytes are decoded to numeric values
 * before being stored).  The mode byte at 0x6E430 is re-seeded from the
 * vector on every line.  Values are validated by the harness against the
 * ROM.  $RX8_ROM_PATH (set by the harness) points at
 * roms/stock/60E1D400.bin.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x0006E000  ROM cal page (mode @0x6E430, safe front @0x6E438,
 *                             safe rear @0x6E43C)
 *   0xFFFFA000  RAM[0xFFFFA63C..0xFFFFA710] (all eight f32 cells)
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_calc_fuel_pump_duty_trim is not (yet) in rx8_samples.h — the shared
 * header is owned by the samples build.  The reconstructed source itself
 * carries the authoritative definition
 * (src/rx8_calc_fuel_pump_duty_trim.c); this prototype mirrors it. */
void rx8_calc_fuel_pump_duty_trim(void);

#define ROM_MODE_ADDR       0x0006E430u   /* u8  mode selector (0 stock)  */
#define ROM_SAFE_FRONT_ADDR 0x0006E438u   /* f32 safe front duty (0.0f)   */
#define ROM_SAFE_REAR_ADDR  0x0006E43Cu   /* f32 safe rear duty  (0.0f)   */
#define RAM_TRIM_SRC_ADDR   0xFFFFA63Cu   /* f32 mode-0 flat-copy source  */
#define RAM_FRONT_OUT_ADDR  0xFFFFA6E4u   /* f32 front channel duty out   */
#define RAM_REAR_OUT_ADDR   0xFFFFA6E8u   /* f32 rear channel duty out    */
#define RAM_BASE_DUTY_ADDR  0xFFFFA6F4u   /* f32 base duty (in / m0 out)  */
#define RAM_COMP_A_ADDR     0xFFFFA6FCu   /* f32 mode-1 front comp 1      */
#define RAM_COMP_B_ADDR     0xFFFFA70Cu   /* f32 mode-1 front comp 2      */
#define RAM_COMP_C_ADDR     0xFFFFA700u   /* f32 mode-1 rear comp 1       */
#define RAM_COMP_D_ADDR     0xFFFFA710u   /* f32 mode-1 rear comp 2       */

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

/* Seed the ROM pump-duty cal page with the actual stock-60E1D400.bin
 * constants.  The file is big-endian, so the two f32 values are assembled by
 * hand and stored as host-endian numeric values; the reconstructed source
 * then reads them back through the very same (mapped) virtual addresses the
 * ROM fetches.  Offsets here == virtual addresses on this ROM image. */
static void seed_rom_cal(int fd)
{
    unsigned char b[4];
    uint32_t bits;
    float v;

    if (pread(fd, b, 4, ROM_SAFE_FRONT_ADDR) != 4) {
        perror("pread safe front");
        exit(2);
    }
    bits = ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16)
         | ((uint32_t)b[2] << 8) | (uint32_t)b[3];
    memcpy(&v, &bits, sizeof v);
    *(volatile float *)(uintptr_t)ROM_SAFE_FRONT_ADDR = v;

    if (pread(fd, b, 4, ROM_SAFE_REAR_ADDR) != 4) {
        perror("pread safe rear");
        exit(2);
    }
    bits = ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16)
         | ((uint32_t)b[2] << 8) | (uint32_t)b[3];
    memcpy(&v, &bits, sizeof v);
    *(volatile float *)(uintptr_t)ROM_SAFE_REAR_ADDR = v;
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

    /* ROM calibration page (anonymous, seeded from the file — see above). */
    map_page(ROM_MODE_ADDR);
    seed_rom_cal(romfd);
    /* RAM page backing all eight f32 cells. */
    map_page(RAM_TRIM_SRC_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long mode, src, base, va, vb, vc, vd, front0, rear0;

        if (sscanf(line,
                   "fpd %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                   &mode, &src, &base, &va, &vb, &vc, &vd, &front0, &rear0)
            != 9) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the mode selector byte (overridden every line so all three
         * branches are exercised; the safe f32 constants stay at their stock
         * ROM values from seed_rom_cal). */
        *(volatile uint8_t *)(uintptr_t)ROM_MODE_ADDR = (uint8_t)mode;

        /* Seed the RAM pre-states (byte-exact numeric values). */
        *(volatile uint32_t *)(uintptr_t)RAM_TRIM_SRC_ADDR  = (uint32_t)src;
        *(volatile uint32_t *)(uintptr_t)RAM_FRONT_OUT_ADDR = (uint32_t)front0;
        *(volatile uint32_t *)(uintptr_t)RAM_REAR_OUT_ADDR  = (uint32_t)rear0;
        *(volatile uint32_t *)(uintptr_t)RAM_BASE_DUTY_ADDR = (uint32_t)base;
        *(volatile uint32_t *)(uintptr_t)RAM_COMP_A_ADDR    = (uint32_t)va;
        *(volatile uint32_t *)(uintptr_t)RAM_COMP_B_ADDR    = (uint32_t)vb;
        *(volatile uint32_t *)(uintptr_t)RAM_COMP_C_ADDR    = (uint32_t)vc;
        *(volatile uint32_t *)(uintptr_t)RAM_COMP_D_ADDR    = (uint32_t)vd;

        rx8_calc_fuel_pump_duty_trim();

        printf("%08X %08X %08X\n",
               *(volatile uint32_t *)(uintptr_t)RAM_BASE_DUTY_ADDR,
               *(volatile uint32_t *)(uintptr_t)RAM_FRONT_OUT_ADDR,
               *(volatile uint32_t *)(uintptr_t)RAM_REAR_OUT_ADDR);
    }
    return 0;
}
