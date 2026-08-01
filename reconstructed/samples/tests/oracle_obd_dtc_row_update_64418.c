/* ============================================================================
 * oracle_obd_dtc_row_update_64418.c  —  host rig for rx8_obd_dtc_row_update_64418
 * ============================================================================
 * Compile together with samples/src/rx8_obd_dtc_row_update_64418.c and pipe
 * test vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     dtc <row> <b32> <b08> <r4>        -> <b32'> <b08'>
 *
 * where b32/b08 are the pre-state bytes at p+0x32 / p+0x08 of the active row
 * and b32'/b08' the post-state bytes.
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the pages
 * backing the on-chip RAM window (same MAP_FIXED trick as tests/host_oracle.c
 * and c/tests/test_obd_dtc_row_update_0x64418.c), seeds the row-index word
 * (0xFFFF8D74) and the two row cells, runs the reconstructed C, and prints
 * the two resulting bytes.  It contains NO copy of the function logic — that
 * lives solely in the reconstructed source under test.
 *
 * The seeded row-index word is written/read through `volatile uint16_t` on the
 * host, which is self-consistent (the C lift reads it the same way); the two
 * compared cells are single bytes, so no endianness subtleties survive the
 * comparison.  Rows must stay <= 0x1AA (426) so p+0x32 stays inside the
 * mapped pages; the harness guarantees that for every vector it feeds here.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_obd_dtc_row_update_64418 is not (yet) declared in rx8_samples.h — the
 * reconstructed sources are dropped in without touching the shared header. */
void rx8_obd_dtc_row_update_64418(uint32_t r4);

#define ROW_ADDR  0xFFFF8D74u   /* u16 active DTC row index                */
#define BASE      0xFFFF8930u   /* u8 DTC table base (0x34 stride)         */
#define STRIDE    0x34u

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

    /* Pages 0xFFFF8000..0xFFFFD000 back the on-chip RAM window rows 0..0x1AA
     * (p+0x32 <= 0xFFFFDFEA for row 0x1AA), plus the row-index word. */
    for (uintptr_t page = 0xFFFF8000u; page <= 0xFFFFD000u; page += 0x1000u)
        map_page(page);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long row, b32, b08, r4;

        if (sscanf(line, "dtc %lx %lx %lx %lx", &row, &b32, &b08, &r4) == 4) {
            uint8_t *p = (uint8_t *)(uintptr_t)(BASE + (uint32_t)row * STRIDE);
            *(volatile uint16_t *)(uintptr_t)ROW_ADDR = (uint16_t)row;
            p[0x32] = (uint8_t)b32;
            p[0x08] = (uint8_t)b08;
            rx8_obd_dtc_row_update_64418((uint32_t)r4);
            printf("%02X %02X\n", p[0x32], p[0x08]);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
