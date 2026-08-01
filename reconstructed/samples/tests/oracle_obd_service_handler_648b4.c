/* ============================================================================
 * oracle_obd_service_handler_648b4.c — host test rig for
 *                                       rx8_obd_service_handler_648b4 @0x648B4
 * ============================================================================
 * Compile together with src/rx8_obd_service_handler_648b4.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     obd <b> <wA> <wB>              -> <wA'> <wB'>
 *
 *   b      : byte value fed to the handler (r4; only the low 8 bits are used)
 *   wA, wB : current 16-bit (value,~value) run-sum cells at 0xFFFF8E98 /
 *            0xFFFF8E9A
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the page
 * backing the two cells (same MAP_FIXED trick as tests/host_oracle.c and
 * c/tests/test_*_49ED0.c) and seeds/reads the two 16-bit words.  It contains
 * NO copy of the function logic — that lives solely in the reconstructed
 * source under test.  Both cells share the 0xFFFF8000 page of the 32 KB
 * on-chip RAM window (0xFFFF6000..0xFFFFDFFF); 0xFFFF8E98 is well above
 * mmap_min_addr on this host, so the fixed mapping succeeds.
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* Not (yet) declared in rx8_samples.h — the reconstructed sources are dropped
 * in without touching the shared header. */
void rx8_obd_service_handler_648b4(uint8_t b);

#define OBD_RUNSUM_CELL_A 0xFFFF8E98u   /* running-delta (value,~value) cell */
#define OBD_RUNSUM_CELL_B 0xFFFF8E9Au   /* last-input   (value,~value) cell */

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

    map_page(OBD_RUNSUM_CELL_A);      /* covers both cells (same 0xFFFF8000 page) */

    while (fgets(line, sizeof line, stdin)) {
        unsigned long b, wA, wB;

        if (sscanf(line, "obd %lx %lx %lx", &b, &wA, &wB) == 3) {
            *(volatile uint16_t *)(uintptr_t)OBD_RUNSUM_CELL_A = (uint16_t)wA;
            *(volatile uint16_t *)(uintptr_t)OBD_RUNSUM_CELL_B = (uint16_t)wB;
            rx8_obd_service_handler_648b4((uint8_t)(b & 0xFFu));
            printf("%04X %04X\n",
                   *(volatile uint16_t *)(uintptr_t)OBD_RUNSUM_CELL_A,
                   *(volatile uint16_t *)(uintptr_t)OBD_RUNSUM_CELL_B);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
