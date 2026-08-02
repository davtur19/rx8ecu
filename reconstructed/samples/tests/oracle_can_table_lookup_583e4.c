/* ============================================================================
 * oracle_can_table_lookup_583e4.c  —  host rig for rx8_can_table_lookup_583e4
 * ============================================================================
 * Compile together with src/rx8_can_table_lookup_583e4.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     tbl <mask> <filter> <sig> <bitmask>       ->  <result>
 *
 *   mask    : r4  (u32, AND-ed with the accumulated sum)
 *   filter  : r5  (u8,  compared against entry byte+3)
 *   sig     : u16 RAM[0xFFFFD226] expected CAN id / signature
 *   bitmask : u16 RAM[0xFFFFD3F0] bitmask applied to entry word+4
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the
 * pages backing the two RAM input cells and the ROM table page(s) straight
 * from the stock bin (pointed at by $RX8_ROM_PATH), seeds every input byte
 * and prints the r0 return value.  It contains NO copy of the function
 * logic — that lives solely in the reconstructed source under test.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x0005F000  ROM page 1 of the 36-entry CAN table (0x5FFEE..)
 *   0x00060000  ROM page 2 of the 36-entry CAN table (..0x600C5)
 *   0xFFFFD000  RAM[0xFFFFD226] expected id, RAM[0xFFFFD3F0] bitmask
 * ==========================================================================*/
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

/* 0x583E4 — see src/rx8_can_table_lookup_583e4.c. */
uint32_t rx8_can_table_lookup_583e4(uint32_t mask, uint8_t filter);

#define SIG_ADDR   0xFFFFD226u   /* u16 expected CAN id (RAM input)  */
#define BM_ADDR    0xFFFFD3F0u   /* u16 bitmask (RAM input)          */
#define TBL_PAGE1  0x0005F000u   /* ROM page holding table head      */
#define TBL_PAGE2  0x00060000u   /* ROM page holding table tail      */

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
    char line[256];
    int romfd;

    if (!rom_path)
        rom_path = "../../../roms/stock/60E1D400.bin";
    romfd = open(rom_path, O_RDONLY);
    if (romfd < 0) {
        perror(rom_path);
        return 2;
    }

    /* RAM page covering the two input cells (0xFFFFD226 / 0xFFFFD3F0). */
    map_page(SIG_ADDR);

    /* ROM table pages, mapped straight from the stock bin so both sides
     * read byte-identical big-endian table rows. */
    map_rom_page(romfd, TBL_PAGE1);
    map_rom_page(romfd, TBL_PAGE2);
    close(romfd);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long mask, filter, sig, bitmask;
        if (sscanf(line, "tbl %lx %lx %lx %lx",
                   &mask, &filter, &sig, &bitmask) != 4) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the two RAM input cells big-endian (identical bytes on the
         * BE emulator side, assembled the same way by rx8_can_be16). */
        *(volatile uint8_t *)(uintptr_t)SIG_ADDR      = (uint8_t)(sig >> 8);
        *(volatile uint8_t *)(uintptr_t)(SIG_ADDR + 1) = (uint8_t)sig;
        *(volatile uint8_t *)(uintptr_t)BM_ADDR       = (uint8_t)(bitmask >> 8);
        *(volatile uint8_t *)(uintptr_t)(BM_ADDR + 1) = (uint8_t)bitmask;

        printf("%08X\n",
               (unsigned)rx8_can_table_lookup_583e4((uint32_t)mask,
                                                    (uint8_t)filter));
    }
    return 0;
}
