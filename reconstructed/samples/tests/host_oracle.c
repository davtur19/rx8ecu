/* ============================================================================
 * host_oracle.c  —  host test rig for the reconstructed samples
 * ============================================================================
 * Compile together with the reconstructed sources (see Makefile) and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     s32 <a> <b>                       -> <r>
 *     mix <key> <roll>                  -> <r>
 *     tbl <clr|step|step2|dec> <idx> <w0> <w2> <w4>
 *                                       -> <n0> <n2> <n4>
 *
 * The oracle re-implements the *caller-side* set-up only: it mmap()s the
 * pages that back the RAM tables (same trick as c/tests/test_*_49ED0.c) and
 * prints the numeric results.  It contains NO copy of the function logic —
 * that lives solely in the reconstructed sources under test.
 *
 * NOTE: for idx >= 9 the slot pointer wraps through 32-bit arithmetic to
 * addresses below mmap_min_addr on this host; those vectors are pinned on
 * the emulator side only (see harness_idx_table.py).
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"
#include "rx8_hw.h"

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

static uint8_t *slot_ptr(uint32_t idx)
{
    uint32_t addr = RX8_IDX_TABLE_BASE
                  + (uint32_t)(idx & 0xFFu) * RX8_IDX_TABLE_STRIDE;
    return (uint8_t *)(uintptr_t)addr;
}

int main(void)
{
    char line[256];

    /* Back the pages holding idx-table slots 0..8 (0xFFFFD000..0xFFFFF000). */
    map_page(0xFFFFD000u);
    map_page(0xFFFFE000u);
    map_page(0xFFFFF000u);

    while (fgets(line, sizeof line, stdin)) {
        char op[16];
        unsigned long a, b, c, d;

        if (sscanf(line, "s32 %lx %lx", &a, &b) == 2) {
            printf("%08lX\n",
                   (unsigned long)(uint32_t)rx8_add_s32_saturate(
                       (int32_t)(uint32_t)a, (int32_t)(uint32_t)b));
        } else if (sscanf(line, "mix %lx %lx", &a, &b) == 2) {
            printf("%08lX\n",
                   (unsigned long)rx8_immo_seed_mixer((uint32_t)a, (uint32_t)b));
        } else if (sscanf(line, "tbl %15s %lx %lx %lx %lx",
                          op, &a, &b, &c, &d) == 5) {
            uint8_t *p = slot_ptr((uint32_t)a);
            uint16_t w0 = (uint16_t)b, w2 = (uint16_t)c, w4 = (uint16_t)d;
            *(volatile uint16_t *)(p + 0) = w0;
            *(volatile uint16_t *)(p + 2) = w2;
            *(volatile uint16_t *)(p + 4) = w4;
            if (!strcmp(op, "clr")) {
                rx8_index_table_clear((uint32_t)a);
            } else if (!strcmp(op, "step")) {
                rx8_index_table_step((uint32_t)a);
            } else if (!strcmp(op, "step2")) {
                rx8_index_table_step2((uint32_t)a);
            } else if (!strcmp(op, "dec")) {
                rx8_index_table_dec((uint32_t)a);
            } else {
                fprintf(stderr, "unknown tbl op: %s\n", op);
                return 2;
            }
            printf("%04X %04X %04X\n",
                   *(volatile uint16_t *)(p + 0),
                   *(volatile uint16_t *)(p + 2),
                   *(volatile uint16_t *)(p + 4));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
