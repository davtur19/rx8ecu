/* ============================================================================
 * oracle_temperature_gauge_5aa5c.c  —  host test rig for
 *                                      rx8_temperature_gauge_5aa5c @0x5AA5C
 * ============================================================================
 * Reads one vector per line on stdin, whitespace-separated hex tokens:
 *
 *     tg <status>        -> <gauge>
 *
 *   status : temperature status byte value (0x00..0xFF) placed at
 *            RAM[0xFFFFCD4C]
 *   gauge  : the gauge value byte left at RAM[0xFFFFD2C4], printed as %02X
 *
 * The oracle contains NO copy of the mapping logic — that lives solely in
 * src/rx8_temperature_gauge_5aa5c.c.  It only mirrors the *caller-side*
 * set-up: the two 0xFFFFxxxx RAM bytes are backed with mmap(MAP_FIXED) pages
 * (same trick as tests/host_oracle.c and c/tests/test_*_49ED0.c), so the
 * volatile fixed-address pointers in the sample compile and fault-free on the
 * host.  This is exactly what the ROM does on the SH-2E, where both addresses
 * are plain on-chip RAM.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_samples.h (shared, untouched by this sample) does not declare the
 * function under test; declare its prototype here instead. */
void rx8_temperature_gauge_5aa5c(void);

/* Temperature status byte @0xFFFFCD4C (page 0xFFFFC000) and gauge value byte
 * @0xFFFFD2C4 (page 0xFFFFD000).  Same addresses as the ROM's sign-extended
 * `mov.w @(disp,PC)` literals (0xCD4C @ pool 0x5AB68, 0xD2C4 @ pool 0x5AB66). */
#define STATUS_ADDR 0xFFFFCD4Cu
#define GAUGE_ADDR  0xFFFFD2C4u

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

    /* Back the pages holding the status byte and the gauge value byte. */
    map_page(STATUS_ADDR);
    map_page(GAUGE_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long status;

        if (sscanf(line, "tg %lx", &status) == 1) {
            /* Seed the status byte, run the function, report the gauge byte. */
            *(volatile uint8_t *)(uintptr_t)STATUS_ADDR = (uint8_t)status;
            rx8_temperature_gauge_5aa5c();
            printf("%02X\n",
                   (unsigned)*(volatile uint8_t *)(uintptr_t)GAUGE_ADDR);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
