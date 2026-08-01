/* ============================================================================
 * oracle_set_mem_inside_func_to1.c  —  host test rig for
 *                                       rx8_set_mem_inside_func_to1 @0x3E3F0
 * ============================================================================
 * Reads one vector per line on stdin, whitespace-separated hex tokens:
 *
 *     set <seed>        -> <flag>
 *
 *   seed : 8-bit value placed at RAM[0xFFFFC638] before the call (the flag
 *          byte the ROM function clobbers)
 *   flag : the byte left at RAM[0xFFFFC638] after the call, printed as %02X
 *
 * The oracle contains NO copy of the function logic — that lives solely in
 * src/rx8_set_mem_inside_func_to1.c.  It only mirrors the *caller-side*
 * set-up: the 0xFFFFC638 RAM byte is backed with an mmap(MAP_FIXED) page
 * (same trick as tests/host_oracle.c and c/tests/test_*_49ED0.c), so the
 * volatile fixed-address pointer in the sample compiles and faults-free on
 * the host.  This is exactly what the ROM does on the SH-2E, where the
 * address is plain on-chip RAM.
 *
 * NOTE (ROM image): the verified function lives in 60E0FC00.bin @0x3E3F0
 * (see rx8_set_mem_inside_func_to1.c header); 60E1D400.bin has unrelated
 * code at that address.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_samples.h (shared, untouched by this sample) does not declare the
 * function under test; declare its prototype here instead. */
void rx8_set_mem_inside_func_to1(void);

/* Fault / in-progress flag byte @0xFFFFC638 (page 0xFFFFC000).  Same address
 * as the ROM's sign-extended 16-bit literal 0xC638 (0x3E50A in 60E0FC00.bin). */
#define FLAG_ADDR 0xFFFFC638u

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

    /* Back the page holding the flag byte. */
    map_page(FLAG_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long seed;

        if (sscanf(line, "set %lx", &seed) == 1) {
            /* Seed the flag byte, run the function, report what is left. */
            *(volatile uint8_t *)(uintptr_t)FLAG_ADDR = (uint8_t)seed;
            rx8_set_mem_inside_func_to1();
            printf("%02X\n",
                   (unsigned)*(volatile uint8_t *)(uintptr_t)FLAG_ADDR);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
