/* ============================================================================
 * oracle_calc_rotor_sync_idle_gate_b.c — host rig for
 *                                            rx8_calc_rotor_sync_idle_gate_b
 * ============================================================================
 * Compile together with samples/src/rx8_calc_rotor_sync_idle_gate_b.c and pipe
 * test vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     gate <rpm> <prev> <flag0> <clen> <clac> <warm> <enA> <enB> <rA> <rB>
 *                                      -> <flag> <prev'> <lA> <lB>
 *
 *   rpm/prev : raw IEEE-754 single-precision bits of the current / previous
 *              RPM sample (RAM[0xFFFFB5B8] / RAM[0xFFFFA694]) — passed as bits
 *              so float<->hex round-trips exactly on both sides of the pipe
 *   flag0    : pre-state byte at RAM[0xFFFFA690] (sentinel: proves the flag
 *              write always happens)
 *   clen/clac/warm : closed-loop-enable / closed-loop-active / warmup bytes
 *   enA/enB  : pre-state of the rotor-enable bytes RAM[0xFFFFA6A3/A6A4]
 *   rA/rB    : rotor-A / rotor-B run-status bytes (RAM[0xFFFFA444/A445])
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the three
 * pages backing the RAM footprint and the ROM page holding the two calibration
 * floats (0x72BC4 = 40.0, 0x72BC8 = 2000.0), seeds every byte, and prints the
 * post-state.  It contains NO copy of the function logic — that lives solely in
 * the reconstructed source under test.
 *
 * The ROM path is taken from argv[1] (absolute, supplied by the harness); it
 * defaults to roms/stock/60E1D400.bin relative to the caller's cwd.
 *
 * NOTE on the ROM cal page: this host environment intercepts file-backed mmap
 * (the mapping comes back zero-filled/anonymous), so instead of mmap()ing the
 * ROM file the oracle maps an anonymous page at 0x72000 and copies the two
 * f32 calibration words out of the ROM file with a plain pread().  The ROM
 * stores them BIG-endian (42 20 00 00 = 40.0, 44 FA 00 00 = 2000.0) while the
 * x86-64 host dereferences native floats, so each word is byte-swapped on the
 * way into the page — the C then reads exactly 40.0f / 2000.0f, the same
 * values the emulator's big-endian `fmov.s @Rm,FRn` obtains from the ROM.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x00072000  ROM calibration table (0x72BC4/0x72BC8, mapped from the ROM file)
 *   0xFFFFA000  RAM[0xFFFFA444/A445/A690/A694/A6A3/A6A4]
 *   0xFFFFB000  RAM[0xFFFFB5A4/B5B8]
 *   0xFFFFC000  RAM[0xFFFFCABC]
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <fcntl.h>

#include "rx8_samples.h"

/* Declared here rather than in rx8_samples.h (off-limits for this task) — the
 * reconstructed name maps to the ROM rotor-sync gate at 0x12BC8 (see
 * src/rx8_calc_rotor_sync_idle_gate_b.c). */
void rx8_calc_rotor_sync_idle_gate_b(void);

#define ROM_TABLE_BASE     0x00072000u   /* page-aligned base of cal table  */
#define ROM_TABLE_OFF      0x00072000u   /* same value in the ROM file      */
#define ROM_CAL_40         0x00072BC4u   /* f32 40.0   (drop threshold)     */
#define ROM_CAL_2000       0x00072BC8u   /* f32 2000.0 (rpm threshold)      */
#define ROTOR_A_ADDR       0xFFFFA444u
#define ROTOR_B_ADDR       0xFFFFA445u
#define ENGINE_RPM_ADDR    0xFFFFB5B8u   /* float */
#define PREV_RPM_ADDR      0xFFFFA694u   /* float */
#define GATE_FLAG_ADDR     0xFFFFA690u
#define CL_ENABLE_ADDR     0xFFFFB5A4u
#define CL_ACTIVE_ADDR     0xFFFFAADAu
#define WARMUP_ADDR        0xFFFFCABCu
#define ENABLE_A_ADDR      0xFFFFA6A3u
#define ENABLE_B_ADDR      0xFFFFA6A4u

#define ROM_PATH "roms/stock/60E1D400.bin"

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

static void map_rom_page(const char *rom_path)
{
    /* Back the page holding the ROM's calibration table at its virtual
     * address (0x72000) so *(const float*)0x72BC4 / 0x72BC8 read the stock
     * words 40.0 / 2000.0.  File-backed mmap is unreliable on this host, so
     * map an anonymous page and pread() the two words out of the ROM file. */
    long page = sysconf(_SC_PAGESIZE);
    int fd = open(rom_path, O_RDONLY);
    if (fd < 0) {
        perror(rom_path);
        exit(1);
    }
    void *p = mmap((void *)ROM_TABLE_BASE, (size_t)page,
                   PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == MAP_FAILED) {
        perror("mmap(rom cal page)");
        exit(1);
    }
    uint8_t cal[8];
    if (pread(fd, cal, sizeof cal, (off_t)ROM_CAL_40) != (ssize_t)sizeof cal) {
        perror("pread(rom cal)");
        exit(1);
    }
    /* ROM is big-endian: swap each f32 word so the LE host reads 40.0/2000.0. */
    for (size_t i = 0; i < 8; i += 4) {
        for (size_t j = 0; j < 4; j++) {
            ((uint8_t *)ROM_TABLE_BASE + (ROM_CAL_40 - ROM_TABLE_BASE))[i + j] =
                cal[i + 3 - j];
        }
    }
    close(fd);
}

int main(int argc, char **argv)
{
    char line[256];
    const char *rom_path = (argc > 1) ? argv[1] : ROM_PATH;

    map_rom_page(rom_path);
    map_page(ROTOR_A_ADDR);
    map_page(ENGINE_RPM_ADDR);
    map_page(WARMUP_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long rpm_bits, prev_bits, flag0, clen, clac, warm, enA, enB, rA, rB;
        int n = sscanf(line,
                       "gate %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                       &rpm_bits, &prev_bits, &flag0, &clen, &clac,
                       &warm, &enA, &enB, &rA, &rB);
        if (n != 10) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        float rpm, prev;
        memcpy(&rpm, &rpm_bits, sizeof rpm);      /* exact float from bits */
        memcpy(&prev, &prev_bits, sizeof prev);

        /* Seed the RAM pre-state. */
        *(volatile uint8_t *)ROTOR_A_ADDR   = (uint8_t)rA;
        *(volatile uint8_t *)ROTOR_B_ADDR   = (uint8_t)rB;
        *(volatile float *)ENGINE_RPM_ADDR  = rpm;
        *(volatile float *)PREV_RPM_ADDR    = prev;
        *(volatile uint8_t *)GATE_FLAG_ADDR = (uint8_t)flag0;
        *(volatile uint8_t *)CL_ENABLE_ADDR = (uint8_t)clen;
        *(volatile uint8_t *)CL_ACTIVE_ADDR = (uint8_t)clac;
        *(volatile uint8_t *)WARMUP_ADDR    = (uint8_t)warm;
        *(volatile uint8_t *)ENABLE_A_ADDR  = (uint8_t)enA;
        *(volatile uint8_t *)ENABLE_B_ADDR  = (uint8_t)enB;

        rx8_calc_rotor_sync_idle_gate_b();

        uint32_t prev_out;
        float    prevf = *(volatile float *)PREV_RPM_ADDR;
        memcpy(&prev_out, &prevf, sizeof prev_out);

        printf("%02X %08X %02X %02X\n",
               *(volatile uint8_t *)GATE_FLAG_ADDR,
               prev_out,
               *(volatile uint8_t *)ENABLE_A_ADDR,
               *(volatile uint8_t *)ENABLE_B_ADDR);
    }
    return 0;
}
