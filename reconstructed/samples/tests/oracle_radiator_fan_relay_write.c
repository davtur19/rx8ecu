/* ============================================================================
 * oracle_radiator_fan_relay_write.c  —  host test rig for
 *                                      rx8_radiator_fan_relay_write @0x259C0
 * ============================================================================
 * Reads one vector per line on stdin, whitespace-separated hex tokens:
 *
 *     rl <status>        -> <relay>
 *
 *   status : fan-status byte value (0x00..0xFF) placed at RAM[0xFFFF9ECD]
 *   relay  : the relay byte left at RAM[0xFFFFB5AB], printed as %02X
 *
 * The oracle contains NO copy of the relay logic — that lives solely in
 * src/rx8_radiator_fan_relay_write.c.  It only mirrors the *caller-side*
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
void rx8_radiator_fan_relay_write(void);

/* Fan status byte @0xFFFF9ECD (page 0xFFFF9000) and relay byte @0xFFFFB5AB
 * (page 0xFFFFB000).  Same addresses as the ROM literals (0x25ABC / 0x25AA6). */
#define STATUS_ADDR 0xFFFF9ECDu
#define RELAY_ADDR  0xFFFFB5ABu

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

    /* Back the pages holding the status byte and the relay byte. */
    map_page(STATUS_ADDR);
    map_page(RELAY_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long status;

        if (sscanf(line, "rl %lx", &status) == 1) {
            /* Seed the status byte, run the function, report the relay byte. */
            *(volatile uint8_t *)(uintptr_t)STATUS_ADDR = (uint8_t)status;
            rx8_radiator_fan_relay_write();
            printf("%02X\n",
                   (unsigned)*(volatile uint8_t *)(uintptr_t)RELAY_ADDR);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
