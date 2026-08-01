/* ============================================================================
 * oracle_bitfield_flag_selector_33a98.c  —  host test rig for
 *                                          rx8_bitfield_flag_selector_33a98 @0x33A98
 * ============================================================================
 * Reads one vector per line on stdin, whitespace-separated hex tokens:
 *
 *     bs <status>        -> <select>
 *
 *   status : flag status byte value (0x00..0xFF) placed at RAM[0xFFFFCD4E]
 *   select : the byte left at RAM[0xFFFFC05C] (top nibble = v << 4), printed
 *            as %02X
 *
 * The oracle contains NO copy of the selector logic — that lives solely in
 * src/rx8_bitfield_flag_selector_33a98.c.  It only mirrors the *caller-side*
 * set-up: both 0xFFFFCD4E and 0xFFFFC05C sit on the same on-chip RAM page
 * (0xFFFFC000), which is backed with one mmap(MAP_FIXED) page (same trick as
 * tests/host_oracle.c and c/tests/test_*_49ED0.c), so the volatile
 * fixed-address pointers in the sample compile and fault-free on the host.
 * This is exactly what the ROM does on the SH-2E, where both addresses are
 * plain on-chip RAM.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_samples.h (shared, untouched by this sample) does not declare the
 * function under test; declare its prototype here instead. */
void rx8_bitfield_flag_selector_33a98(void);

/* Flag status byte @0xFFFFCD4E and select-code byte @0xFFFFC05C — both on the
 * same 0xFFFFC000 page.  Same addresses as the ROM's mov.w/mov.l literals. */
#define IN_ADDR   0xFFFFCD4Eu
#define OUT_ADDR  0xFFFFC05Cu

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

    /* Back the page holding both the status byte and the select-code byte. */
    map_page(IN_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long status;

        if (sscanf(line, "bs %lx", &status) == 1) {
            /* Seed the status byte, run the function, report the select byte. */
            *(volatile uint8_t *)(uintptr_t)IN_ADDR = (uint8_t)status;
            rx8_bitfield_flag_selector_33a98();
            printf("%02X\n",
                   (unsigned)*(volatile uint8_t *)(uintptr_t)OUT_ADDR);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
