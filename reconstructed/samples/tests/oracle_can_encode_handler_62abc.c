/* ============================================================================
 * oracle_can_encode_handler_62abc.c  —  host rig for rx8_can_encode_handler_62abc
 * ============================================================================
 * Compile together with samples/src/rx8_can_encode_handler_62abc.c and pipe
 * test vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     enc <dtc> <r5> <mode> <wa> <wb>
 *                                     -> <na> <nb>
 *
 *   dtc   : DTC index (u32; masked to 16 bits by the function; harness
 *           restricts it to 0..0x7F so the mode-table read at
 *           0xFFFF8D7C + (dtc&0xFFFF)*2 stays clear of the run-sum cells)
 *   r5    : value to fold (u32; only the low byte matters)
 *   mode  : per-DTC mode dispatch byte, seeded at the table slot
 *   wa    : pre-state of the run-sum cell word@0xFFFF8E98 (u16)
 *   wb    : pre-state of the run-sum cell word@0xFFFF8E9A (u16)
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the page
 * backing the mode table AND the two run-sum cells, seeds every byte and
 * prints the two post-state words.  It contains NO copy of the function logic
 * of can_encode_handler_62ABC — that lives solely in the reconstructed source
 * under test.  The only additional code here is the definition of the
 * external callee obd_service_handler_648B4 (verbatim port of the verified
 * lift c/obd_service_handler_648B4.c), which the sample declares `extern`
 * exactly as the lift does and which the emulator side executes from the real
 * ROM bytes.
 *
 * Endianness: the cells are accessed as uint16_t on both sides (the big-endian
 * target stores hi8(word) at the lower address; the numeric value is what the
 * comparison runs on), the same endian-safe pattern as the lift.
 *
 * Page mapped (above mmap_min_addr on this host):
 *   0xFFFF8000  mode table @0xFFFF8D7C .. 0xFFFF8E7A and run-sum cells
 *               @0xFFFF8E98 / 0xFFFF8E9A
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* The reconstructed source carries the authoritative definition; this
 * prototype mirrors it exactly (same pattern as oracle_purge_control_state_update.c). */
void rx8_can_encode_handler_62abc(uint32_t dtc, uint32_t r5);

#define MODE_TABLE      0xFFFF8D7Cu   /* per-DTC mode dispatch byte table */
#define RUN_SUM_1       0xFFFF8E98u   /* word: run-sum cell 1 (hi8 = s8 byte) */
#define RUN_SUM_2       0xFFFF8E9Au   /* word: run-sum cell 2 (hi8 = s8 byte) */

static inline uint16_t enc8(uint8_t x)      /* verified leaf 0x2420          */
{
    return (uint16_t)((x << 8) | (uint8_t)~x);
}

/* 0x648B4 — fold r4 into the two run-sum cells (verbatim port of the verified
 * lift c/obd_service_handler_648B4.c; the emulator runs the real ROM bytes). */
void obd_service_handler_648B4(uint32_t r4)
{
    uint8_t  b   = (uint8_t)(r4 & 0xFFu);
    uint16_t w98 = *(volatile uint16_t *)(uintptr_t)RUN_SUM_1;
    uint16_t w9A = *(volatile uint16_t *)(uintptr_t)RUN_SUM_2;
    int32_t  sum = (int32_t)(int8_t)((w98 >> 8) & 0xFF)
                 + (int32_t)(int8_t)((w9A >> 8) & 0xFF)
                 - (int32_t)(int8_t)b;
    *(volatile uint16_t *)(uintptr_t)RUN_SUM_1 = enc8((uint8_t)sum);
    *(volatile uint16_t *)(uintptr_t)RUN_SUM_2 = enc8(b);
}

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

    /* One page backs the mode table AND both run-sum cells (0xFFFF8D7C..0xFFFF8E9B). */
    map_page(MODE_TABLE);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long dtc, r5, mode, wa, wb;
        int n = sscanf(line, "enc %lx %lx %lx %lx %lx",
                       &dtc, &r5, &mode, &wa, &wb);
        if (n != 5) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the per-DTC mode byte exactly where the ROM reads it. */
        *(volatile uint8_t *)(uintptr_t)(MODE_TABLE
            + (((uint32_t)dtc & 0xFFFFu) << 1)) = (uint8_t)mode;

        /* Seed the run-sum cell pre-states. */
        *(volatile uint16_t *)(uintptr_t)RUN_SUM_1 = (uint16_t)wa;
        *(volatile uint16_t *)(uintptr_t)RUN_SUM_2 = (uint16_t)wb;

        rx8_can_encode_handler_62abc((uint32_t)dtc, (uint32_t)r5);

        printf("%04X %04X\n",
               *(volatile uint16_t *)(uintptr_t)RUN_SUM_1,
               *(volatile uint16_t *)(uintptr_t)RUN_SUM_2);
    }
    return 0;
}
