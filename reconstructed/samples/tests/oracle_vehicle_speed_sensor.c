/* ============================================================================
 * oracle_vehicle_speed_sensor.c  —  host rig for rx8_vehicle_speed_sensor
 * ============================================================================
 * Compile together with src/rx8_vehicle_speed_sensor.c and pipe test vectors
 * on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     vss <s7> <s8> <s9> <a428> <raw> <prev> <c1> <c2>
 *                                   -> <A6AC> <A6B0> <A6CC> <A6D0> <A6D4> <A6D8>
 *
 *   s7   : u8  RAM8[0xFFFFA6B7]  status select (==1 -> bias 1.0)
 *   s8   : u8  RAM8[0xFFFFA6B8]  status select (==1 -> bias 1.0)
 *   s9   : u8  RAM8[0xFFFFA6B9]  status select (==1 -> bias 5.0)
 *   a428 : u8  RAM8[0xFFFFA428]  filter gate  (==0 -> zero both f32 cells)
 *   raw  : f32 RAM[0xFFFFA6AC]   raw speed, shipped as IEEE-754 bits
 *   prev : f32 RAM[0xFFFFA6B0]   previous/output speed, bits
 *   c1   : f32 RAM[0xFFFFA6BC]   pivot A, bits
 *   c2   : f32 RAM[0xFFFFA6C0]   pivot B, bits
 *   -> the six post-state f32 cells, reported as raw bits.
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the RAM
 * page backing all the cells and the ROM cal page (0x6F000, seeded straight
 * from the ROM file so the pivot/status constants @0x6F704/0x6F708/0x6F71C..
 * 0x6F758 read byte-identically on both sides), seeds the inputs and prints
 * the six post-state cells.  It contains NO copy of the function logic — that
 * lives solely in the reconstructed source under test.
 *
 * The RAM inputs are stored as their raw IEEE-754 bits via 32-bit writes; on
 * the little-endian host the same bit pattern dereferences to the identical
 * float the big-endian emulator computes, and every float cell written by the
 * function is read back as its 32-bit pattern — so host == emulator bit-exact.
 *
 * Pages mapped:
 *   0xFFFFA000  RAM (cells @0xFFFFA428..0xFFFFA6D8)
 *   0x0006F000  ROM cal constants (f32 threshold + 1.0 / 5.0 bias block)
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <fcntl.h>

/* 0x133F8 — see src/rx8_vehicle_speed_sensor.c. */
void rx8_vehicle_speed_sensor(void);

#define VSS_RAW    0xFFFFA6ACu
#define VSS_OUT    0xFFFFA6B0u
#define VSS_BIAS1  0xFFFFA6CCu
#define VSS_BIAS2  0xFFFFA6D0u
#define VSS_BIAS3  0xFFFFA6D4u
#define VSS_BIAS4  0xFFFFA6D8u

#ifndef ROM_PATH
#define ROM_PATH "/home/davide/ailocal/rx8ecu/roms/stock/60E1D400.bin"
#endif

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

int main(void)
{
    const char *rom_path = getenv("RX8_ROM_PATH");
    char line[128];
    int fd;

    if (!rom_path)
        rom_path = ROM_PATH;
    fd = open(rom_path, O_RDONLY);
    if (fd < 0) {
        perror(rom_path);
        return 2;
    }

    /* RAM page backing every cell this function reads and writes. */
    map_page(VSS_RAW);
    /* ROM cal constants page (f32 0.1 thresholds + 1.0/5.0 biases). */
    map_rom_page(fd, 0x0006F000u);
    close(fd);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long s7, s8, s9, a428, raw, prev, c1, c2;
        union { uint32_t u; float f; } ux;

        if (sscanf(line, "vss %lx %lx %lx %lx %lx %lx %lx %lx",
                   &s7, &s8, &s9, &a428, &raw, &prev, &c1, &c2) != 8) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the RAM pre-states (raw float bits via uint32 writes). */
        *(volatile uint32_t *)(uintptr_t)0xFFFFA6ACu = (uint32_t)raw;
        *(volatile uint32_t *)(uintptr_t)0xFFFFA6B0u = (uint32_t)prev;
        *(volatile uint32_t *)(uintptr_t)0xFFFFA6BCu = (uint32_t)c1;
        *(volatile uint32_t *)(uintptr_t)0xFFFFA6C0u = (uint32_t)c2;
        *(volatile uint8_t  *)(uintptr_t)0xFFFFA6B7u = (uint8_t)s7;
        *(volatile uint8_t  *)(uintptr_t)0xFFFFA6B8u = (uint8_t)s8;
        *(volatile uint8_t  *)(uintptr_t)0xFFFFA6B9u = (uint8_t)s9;
        *(volatile uint8_t  *)(uintptr_t)0xFFFFA428u = (uint8_t)a428;

        rx8_vehicle_speed_sensor();

        (void)ux;
        printf("%08X %08X %08X %08X %08X %08X\n",
               *(volatile uint32_t *)(uintptr_t)0xFFFFA6ACu,
               *(volatile uint32_t *)(uintptr_t)0xFFFFA6B0u,
               *(volatile uint32_t *)(uintptr_t)0xFFFFA6CCu,
               *(volatile uint32_t *)(uintptr_t)0xFFFFA6D0u,
               *(volatile uint32_t *)(uintptr_t)0xFFFFA6D4u,
               *(volatile uint32_t *)(uintptr_t)0xFFFFA6D8u);
    }
    return 0;
}