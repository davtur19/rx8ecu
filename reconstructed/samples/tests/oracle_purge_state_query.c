/* ============================================================================
 * oracle_purge_state_query.c  —  host test rig for rx8_purge_state_query
 * ============================================================================
 * Compile together with src/rx8_purge_state_query.c (see
 * harness_purge_state_query.py) and pipe test vectors on stdin; one vector
 * per line:
 *
 *     q <hh>                          -> <hh>
 *
 * where <hh> is the byte seeded at RAM[0xFFFFA4B1] and the output is the
 * result of rx8_purge_state_query() @0xF5DC.
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the RAM
 * page that backs 0xFFFFA4B1 (same trick as tests/host_oracle.c) and prints
 * the numeric result.  It contains NO copy of the function logic — that lives
 * solely in the reconstructed source under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_purge_state_query is not (yet) in rx8_samples.h — that header is owned
 * by the shared samples build.  The reconstructed source itself carries the
 * authoritative definition (src/rx8_purge_state_query.c); this prototype
 * mirrors it exactly. */
uint8_t rx8_purge_state_query(void);

/* Byte read by purge_state_query @0xF5DC (see rx8_purge_state_query.c). */
#define PURGE_STATE_ADDR 0xFFFFA4B1u

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
    char line[64];
    unsigned long v;

    /* Back the RAM page holding RAM[0xFFFFA4B1] (0xFFFFA000..0xFFFFAFFF). */
    map_page(0xFFFFA000u);

    while (fgets(line, sizeof line, stdin)) {
        if (sscanf(line, "q %lx", &v) != 1) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        *(volatile uint8_t *)PURGE_STATE_ADDR = (uint8_t)v;
        printf("%02X\n", (unsigned)rx8_purge_state_query());
    }
    return 0;
}
