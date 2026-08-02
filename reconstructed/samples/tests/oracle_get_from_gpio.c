/* ============================================================================
 * oracle_get_from_gpio.c  —  host rig for rx8_get_from_gpio
 * ============================================================================
 * Compile together with samples/src/rx8_get_from_gpio.c and pipe test vectors
 * on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     gpio <sel> <F0> <F1> <F2> <F3> <F4> <F5> <F6> <F72C> <F764>
 *                                              -> <ret> <F0> <F1> <F2> <F3>
 *                                                 <F4> <F5> <F6> <F72C> <F764>
 *
 *   sel    : run-time selector byte (ROM r4, extu.b)
 *   F0..F6 : the 7 u8 port cells (0xFFFFF000..0xFFFFF006)
 *   F72C   : u16 pattern scatter latch
 *   F764   : u16 leaf RMW latch
 *
 * The oracle re-implements only the caller-side set-up: it mmap()s the pages
 * backing the port cells, seeds every cell and prints the post-state after
 * rx8_get_from_gpio() runs.  It contains NO copy of the function logic — that
 * lives solely in the reconstructed source under test.
 *
 * Pages mapped: 0xFFFFF000 (u8 ports) and 0xFFFFF700 (F72C/F764 latches).
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

uint8_t rx8_get_from_gpio(uint8_t input);

#define CELL_P0     0xFFFFF000u   /* u8 */
#define CELL_P1     0xFFFFF001u
#define CELL_P2     0xFFFFF002u
#define CELL_P3     0xFFFFF003u
#define CELL_P4     0xFFFFF004u
#define CELL_P5     0xFFFFF005u
#define CELL_P6     0xFFFFF006u
#define CELL_F72C   0xFFFFF72Cu   /* u16 */
#define CELL_F764   0xFFFFF764u   /* u16 */

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

int main(void)
{
    char line[256];

    map_page(0xFFFFF000u);
    map_page(0xFFFFF700u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long sel, f0, f1, f2, f3, f4, f5, f6, f72c, f764;
        int n = sscanf(line, "gpio %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                       &sel, &f0, &f1, &f2, &f3, &f4, &f5, &f6, &f72c, &f764);
        if (n != 10) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        *(volatile uint8_t *)(uintptr_t)CELL_P0   = (uint8_t)f0;
        *(volatile uint8_t *)(uintptr_t)CELL_P1   = (uint8_t)f1;
        *(volatile uint8_t *)(uintptr_t)CELL_P2   = (uint8_t)f2;
        *(volatile uint8_t *)(uintptr_t)CELL_P3   = (uint8_t)f3;
        *(volatile uint8_t *)(uintptr_t)CELL_P4   = (uint8_t)f4;
        *(volatile uint8_t *)(uintptr_t)CELL_P5   = (uint8_t)f5;
        *(volatile uint8_t *)(uintptr_t)CELL_P6   = (uint8_t)f6;
        *(volatile uint16_t *)(uintptr_t)CELL_F72C = (uint16_t)f72c;
        *(volatile uint16_t *)(uintptr_t)CELL_F764 = (uint16_t)f764;

        uint8_t ret = rx8_get_from_gpio((uint8_t)sel);

        printf("%02X %02X %02X %02X %02X %02X %02X %02X %04X %04X\n",
               ret,
               *(volatile uint8_t *)(uintptr_t)CELL_P0,
               *(volatile uint8_t *)(uintptr_t)CELL_P1,
               *(volatile uint8_t *)(uintptr_t)CELL_P2,
               *(volatile uint8_t *)(uintptr_t)CELL_P3,
               *(volatile uint8_t *)(uintptr_t)CELL_P4,
               *(volatile uint8_t *)(uintptr_t)CELL_P5,
               *(volatile uint8_t *)(uintptr_t)CELL_P6,
               *(volatile uint16_t *)(uintptr_t)CELL_F72C,
               *(volatile uint16_t *)(uintptr_t)CELL_F764);
    }
    return 0;
}