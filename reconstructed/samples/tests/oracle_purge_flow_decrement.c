/* ============================================================================
 * oracle_purge_flow_decrement.c  —  host rig for rx8_purge_flow_decrement
 * ============================================================================
 * Compile together with samples/src/rx8_purge_flow_decrement.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     purg <flow> <dec_en>            -> <flow> <dec_en>
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the page
 * backing the purge-flow RAM cells (same MAP_FIXED trick as
 * tests/host_oracle.c and c/tests/test_*_49ED0.c) and seeds/reads the two
 * bytes.  It contains NO copy of the function logic — that lives solely in
 * the reconstructed source under test.
 *
 * Both cells live in the 0xFFFFA000 page of the 32 KB on-chip RAM window
 * (0xFFFF6000..0xFFFFDFFF); 0xFFFFA4B0 and 0xFFFFA4B2 are well above
 * mmap_min_addr on this host, so the fixed mapping succeeds.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_purge_flow_decrement is not (yet) declared in rx8_samples.h — the
 * reconstructed sources are dropped in without touching the shared header. */
void rx8_purge_flow_decrement(void);

#define PURGE_FLOW_ADDR    0xFFFFA4B0u   /* u8 remaining purge-flow ticks */
#define PURGE_DEC_EN_ADDR  0xFFFFA4B2u   /* u8 countdown "armed" latch    */

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

    map_page(PURGE_FLOW_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long flow, dec_en;

        if (sscanf(line, "purg %lx %lx", &flow, &dec_en) == 2) {
            *(volatile uint8_t *)(uintptr_t)PURGE_FLOW_ADDR = (uint8_t)flow;
            *(volatile uint8_t *)(uintptr_t)PURGE_DEC_EN_ADDR = (uint8_t)dec_en;
            rx8_purge_flow_decrement();
            printf("%02X %02X\n",
                   *(volatile uint8_t *)(uintptr_t)PURGE_FLOW_ADDR,
                   *(volatile uint8_t *)(uintptr_t)PURGE_DEC_EN_ADDR);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
