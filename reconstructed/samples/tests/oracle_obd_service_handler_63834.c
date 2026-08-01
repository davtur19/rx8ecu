/* ============================================================================
 * oracle_obd_service_handler_63834.c — host rig for rx8_obd_service_handler_63834
 * ============================================================================
 * Compile together with samples/src/rx8_obd_service_handler_63834.c and pipe
 * test vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     obd <dtc> <cur> <c0> <t0> <c1> <t1> ... <c20> <t20>     -> <result>
 *
 *   dtc    : 32-bit value passed in r4 (only its low 16 bits are used)
 *   cur    : 16-bit "current DTC index" word seeded at 0xFFFF8928
 *   cN/tN  : the 21 table rows: 16-bit code word @base+N*16, type byte @+6
 *
 * The result is the sign-extended int32 the ROM returns in r0, printed as
 * %08X (or 00000000 when no non-current row matches).
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the page
 * backing the on-chip RAM window (0xFFFF8000, which covers the whole table
 * 0xFFFF87D8..0xFFFF8927 and the index word at 0xFFFF8928), seeds the 21
 * rows + the index word, runs the reconstructed C, and prints the return
 * value.  It contains NO copy of the function logic — that lives solely in
 * the reconstructed source under test.
 *
 * rx8_obd_service_handler_63834 is not (yet) declared in rx8_samples.h — the
 * reconstructed sources are dropped in without touching the shared header.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* 0x63834 — OBD mode-1 status read over the DTC context table (see
 * rx8_obd_service_handler_63834.c). */
int32_t obd_service_handler_63834(uint32_t r4);

#define BASE   0xFFFF87D8u   /* u8 DTC context table base (16-byte stride) */
#define STRIDE 16u
#define COUNT  21u
#define CUR    0xFFFF8928u   /* u16 current DTC index word                  */

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
    char line[512];

    /* Page 0xFFFF8000 backs the whole context table (0xFFFF87D8..0xFFFF8927)
     * and the current-index word (0xFFFF8928). */
    map_page(0xFFFF8000u);

    while (fgets(line, sizeof line, stdin)) {
        char *tok;
        unsigned long dtc, cur;

        tok = strtok(line, " \t\r\n");
        if (!tok) {
            continue;                       /* blank line */
        }
        if (strcmp(tok, "obd") != 0) {
            fprintf(stderr, "bad opcode: %s\n", tok);
            return 2;
        }
        dtc = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        cur = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        if (cur > 0xFFFFu) {
            fprintf(stderr, "bad cur: %lu\n", cur);
            return 2;
        }

        for (unsigned i = 0; i < COUNT; i++) {
            unsigned long code, typ;
            uint8_t *p = (uint8_t *)(uintptr_t)(BASE + i * STRIDE);
            code = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
            typ = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
            if (code > 0xFFFFu || typ > 0xFFu) {
                fprintf(stderr, "bad row %u: %lX %lX\n", i, code, typ);
                return 2;
            }
            *(volatile uint16_t *)(uintptr_t)p = (uint16_t)code;
            p[6] = (uint8_t)typ;
        }

        *(volatile uint16_t *)(uintptr_t)CUR = (uint16_t)cur;

        printf("%08lX\n", (unsigned long)(uint32_t)obd_service_handler_63834((uint32_t)dtc));
    }
    return 0;
}
