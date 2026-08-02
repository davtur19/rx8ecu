/* ============================================================================
 * oracle_limit_knock_retard_max.c  —  host rig for
 * rx8_limit_knock_retard_max
 * ============================================================================
 * Compile together with src/rx8_limit_knock_retard_max.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens
 * (floats shipped as raw IEEE-754 single-precision bits so the round trip
 * through the pipe is exact on both sides):
 *
 *     lkr <rpm> <sensor> <flag> <sec> <arg>
 *                                         -> <result>
 *
 *   rpm    : f32 RAM[0xFFFFB5B8] engine speed (table interp axis)
 *   sensor : u8  RAM[0xFFFFB5A4] status byte (==1 / ==0 table-select gate)
 *   flag   : u8  RAM[0xFFFFBB55] flag byte (sensor==0 table-select gate)
 *   sec    : u8  RAM[0xFFFFBCA9] secondary byte (sensor==1 gate vs 5)
 *   arg    : f32 ABI argument fr4 — the knock-retard value being clamped
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the pages
 * backing the RAM cells AND the ROM calibration pages straight from the stock
 * bin (pointed at by $RX8_ROM_PATH), seeds every input cell and prints the
 * returned float (fr0) as raw bits.  It contains NO copy of the function
 * logic — that lives solely in the reconstructed source under test (including
 * the inlined ROM leaves 0x2068 table1D_lookup and 0x2404 clamp).
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x0006B000  ROM page (0x6B664 / 0x6B678 1D table descriptors)
 *   0x00079000  ROM page (0x79838 u8 threshold, 0x79878 f32 clamp upper,
 *                         0x798A4/0x798B8/0x798C0/0x798D0 axes + u8 cells)
 *   0xFFFFB000  RAM[0xFFFFB5B8 rpm / 0xFFFFB5A4 sensor /
 *                        0xFFFFBB55 flag / 0xFFFFBCA9 sec]
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <fcntl.h>

/* 0x13E6C — see src/rx8_limit_knock_retard_max.c. */
float rx8_limit_knock_retard_max(float knock_retard);

#define ROM_DESC_ADDR   0x0006B000u   /* 0x6B664/0x6B678 1D descriptors      */
#define ROM_CAL_ADDR    0x00079000u   /* threshold + clamp upper + tables    */
#define RAM_RPM_ADDR    0xFFFFB5B8u   /* f32  engine speed                   */
#define RAM_SENSOR_ADDR 0xFFFFB5A4u   /* u8   status byte                    */
#define RAM_FLAG_ADDR   0xFFFFBB55u   /* u8   flag byte                      */
#define RAM_SEC_ADDR    0xFFFFBCA9u   /* u8   secondary byte                 */

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

static void seed_f(float *cell, unsigned long bits)
{
    uint32_t u = (uint32_t)bits;
    memcpy(cell, &u, sizeof u);
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

    /* RAM page covering every input cell of the function. */
    map_page(RAM_RPM_ADDR);

    /* ROM calibration pages, mapped straight from the stock bin so both sides
     * read byte-identical big-endian constants and tables. */
    map_rom_page(romfd, ROM_DESC_ADDR);
    map_rom_page(romfd, ROM_CAL_ADDR);
    close(romfd);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long rpm, sensor, flag, sec, arg;
        float f, result;
        uint32_t u;

        if (sscanf(line,
                   "lkr %lx %lx %lx %lx %lx",
                   &rpm, &sensor, &flag, &sec, &arg) != 5) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the input RAM cells (floats from raw bits, endian-neutral). */
        seed_f((float *)(uintptr_t)RAM_RPM_ADDR, rpm);
        *(volatile uint8_t *)(uintptr_t)RAM_SENSOR_ADDR = (uint8_t)sensor;
        *(volatile uint8_t *)(uintptr_t)RAM_FLAG_ADDR   = (uint8_t)flag;
        *(volatile uint8_t *)(uintptr_t)RAM_SEC_ADDR    = (uint8_t)sec;

        u = (uint32_t)arg;            /* arg arrives as raw float bits      */
        memcpy(&f, &u, sizeof f);
        result = rx8_limit_knock_retard_max(f);

        memcpy(&u, &result, sizeof u);
        printf("%08X\n", (unsigned)u);
    }
    return 0;
}
