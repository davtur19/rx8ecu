/* ============================================================================
 * oracle_obd_dtc_row_update_64258.c — host test rig for
 *                                        rx8_obd_dtc_row_update_64258 @0x64258
 * ============================================================================
 * Compile together with src/rx8_obd_dtc_row_update_64258.c (see
 * harness_obd_dtc_row_update_64258.py) and pipe test vectors on stdin; one
 * vector per line, space-separated hex tokens:
 *
 *     dtc <row> <b32> <b07> <b08>   -> <r32> <r07> <r08> <row'>
 *
 *   row   : active-row index (16-bit; realistic range 0..0x14)
 *   b32   : pre-state of byte p+0x32 (persistence counter A)
 *   b07   : pre-state of byte p+0x07 (counter A's "armed" companion)
 *   b08   : pre-state of byte p+0x08 (counter B's companion)
 *
 * The oracle re-implements the caller-side setup only: it mmap()s the page
 * backing the DTC table (0xFFFF8000..0xFFFF8FFF, same trick as host_oracle.c),
 * seeds the row-index word @0xFFFF8D74 and the three row bytes, runs the
 * reconstructed function, and prints the post-state of the three touched bytes
 * plus the row-index word (which the ROM must leave untouched).  It contains
 * NO copy of the function logic — that lives solely in the reconstructed
 * source under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"
#include "rx8_hw.h"

/* Prototype is NOT in rx8_samples.h (sample-project convention: only verified
 * "public" leaves are listed there); declared here for the rig. */
void rx8_obd_dtc_row_update_64258(void);

#define ROW_INDEX_ADDR 0xFFFF8D74u

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

static uint8_t *row_ptr(uint32_t row)
{
    return (uint8_t *)(uintptr_t)(RX8_DTC_TABLE_BASE
                                  + (uint32_t)(row & 0xFFFFu) * RX8_DTC_TABLE_STRIDE);
}

int main(void)
{
    /* Page 0xFFFF8000..0xFFFF8FFF backs the DTC table (rows 0..0x14 end at
     * 0xFFFF8D8A) and the row-index word at 0xFFFF8D74. */
    map_page(RX8_DTC_TABLE_BASE);

    char line[256];
    while (fgets(line, sizeof line, stdin)) {
        unsigned long row, b32, b07, b08;
        if (sscanf(line, "dtc %lx %lx %lx %lx", &row, &b32, &b07, &b08) == 4) {
            uint8_t *p = row_ptr((uint32_t)row);

            *(volatile uint16_t *)ROW_INDEX_ADDR = (uint16_t)row;
            p[0x32] = (uint8_t)b32;
            p[0x07] = (uint8_t)b07;
            p[0x08] = (uint8_t)b08;

            rx8_obd_dtc_row_update_64258();

            printf("%02X %02X %02X %04X\n",
                   p[0x32], p[0x07], p[0x08],
                   *(volatile uint16_t *)ROW_INDEX_ADDR);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
