/* ============================================================================
 * oracle_obd_service_handler_63b46.c  —  host rig for
 * rx8_obd_service_handler_63b46 @0x63B46
 * ============================================================================
 * Compile together with src/rx8_obd_service_handler_63b46.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     obd <r4> <idx> <b0d> <b0e>        -> <ret> <p0D> <p0E>
 *
 *   r4   : full 32-bit sample value passed to the leaf (argument in r4)
 *   idx  : 16-bit "current DTC index" written to the word @0xFFFF8928
 *   b0d  : pre-state of the row's byte at +0x0D (previous sample)
 *   b0e  : pre-state of the row's byte at +0x0E (debounce accumulator)
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the page
 * backing the DTC context table (0xFFFF87D8..0xFFFF8928 all live in the
 * 0xFFFF8000 page — same MAP_FIXED trick as tests/host_oracle.c and the
 * 632D6/63312 sibling oracles), seeds the row-selection word and the two row
 * bytes, runs the reconstructed C, and prints the return value plus the two
 * side-effected bytes.  It contains NO copy of the function logic — that
 * lives solely in the reconstructed source under test.
 *
 * idx is restricted to the realistic table rows 0..0x14 (21 * 16 == 0x150
 * bytes, 0xFFFF87D8..0xFFFF8928) so the row pointer stays inside the mapped
 * page; the >0x14 pointer-wrap semantics are pinned emulator-only in the
 * harness (see harness_obd_service_handler_63b46.py).
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_obd_service_handler_63b46 is not (yet) declared in rx8_samples.h — the
 * reconstructed sources are dropped in without touching the shared header. */
uint32_t rx8_obd_service_handler_63b46(uint32_t r4);

#define CTX_BASE   0xFFFF87D8u   /* DTC context table base */
#define CTX_STRIDE 16u
#define CUR_INDEX  0xFFFF8928u   /* word: current DTC index being serviced */

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

    /* Back the page holding the whole DTC context table (0xFFFF8000 page). */
    map_page(CTX_BASE);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long r4, idx, b0d, b0e;

        if (sscanf(line, "obd %lx %lx %lx %lx", &r4, &idx, &b0d, &b0e) == 4) {
            uint8_t *p = (uint8_t *)(uintptr_t)(CTX_BASE
                                     + (uint32_t)((uint16_t)idx & 0xFFFFu)
                                     * CTX_STRIDE);
            *(volatile uint16_t *)CUR_INDEX = (uint16_t)idx;
            p[0x0D] = (uint8_t)b0d;
            p[0x0E] = (uint8_t)b0e;

            uint32_t ret = rx8_obd_service_handler_63b46((uint32_t)r4);

            printf("%08lX %02X %02X\n",
                   (unsigned long)ret,
                   (unsigned)*(volatile uint8_t *)(p + 0x0D),
                   (unsigned)*(volatile uint8_t *)(p + 0x0E));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
