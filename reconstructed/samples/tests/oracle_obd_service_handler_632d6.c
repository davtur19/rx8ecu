/* ============================================================================
 * oracle_obd_service_handler_632d6.c — host test rig for
 *                                     rx8_obd_service_handler_632d6 @0x632D6
 * ============================================================================
 * Compile together with src/rx8_obd_service_handler_632d6.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     obd <flag> <pad>                      -> <word_after>
 *
 *   flag : the pending-flag byte (ROM byte@0xFFFF87CC, the HIGH byte of the
 *          16-bit cell — big-endian SH-2E semantics)
 *   pad  : the neighbouring low byte (byte@0xFFFF87CD)
 *
 * The oracle seeds the 16-bit cell with the word value (flag<<8)|pad and prints
 * the full cell word after the call as %04X.  It contains NO copy of the
 * function logic — that lives solely in src/rx8_obd_service_handler_632d6.c —
 * and mirrors only the caller-side set-up: the page backing 0xFFFF87CC is
 * mmap()ed MAP_FIXED exactly as the shared host_oracle.c and the c/tests host
 * companions do.  Because the flag is always stored/read through the uint16_t
 * WORD value, the results are endian-independent on the host.
 *
 * NOTE: rx8_obd_service_handler_632d6 is declared here rather than in
 * rx8_samples.h (which is off-limits for this task) — the reconstructed name
 * maps to the ROM function at 0x632D6 (see rx8_obd_service_handler_632d6.c).
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* 0x632D6 — OBD pending-flag clear leaf (see rx8_obd_service_handler_632d6.c). */
void rx8_obd_service_handler_632d6(void);

#define FLAG_CELL 0xFFFF87CCu

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

    map_page(0xFFFF8000u);          /* page holding 0xFFFF87CC */

    while (fgets(line, sizeof line, stdin)) {
        unsigned long flag, pad;

        if (sscanf(line, "obd %lx %lx", &flag, &pad) != 2) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
        /* value with flag as high byte = byte@FLAG in ROM (big-endian)
         * semantics; stored/read as a uint16_t WORD on both sides. */
        *(volatile uint16_t *)FLAG_CELL =
            (uint16_t)(((uint16_t)flag << 8) | (uint16_t)pad);

        rx8_obd_service_handler_632d6();

        printf("%04X\n",
               (unsigned)(*(volatile uint16_t *)FLAG_CELL));
    }
    return 0;
}
