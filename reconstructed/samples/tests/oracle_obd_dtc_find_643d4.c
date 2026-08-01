/* ============================================================================
 * oracle_obd_dtc_find_643d4.c — host test rig for rx8_obd_dtc_find_643d4
 * ============================================================================
 * Compile together with src/rx8_obd_dtc_find_643d4.c and pipe test vectors
 * on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     dtc <r4> <currow> <w0> ... <w20> <b0> ... <b20>   -> <result>
 *
 *   r4     : 16-bit DTC key passed in r4 (upper bits ignored by the ROM)
 *   currow : 16-bit active-row index (word @0xFFFF8D74)
 *   w0..   : the 21 rows' 16-bit words (table @0xFFFF8930, stride 0x34)
 *   b0..   : the 21 rows' byte-0x06 status bytes
 *
 * The oracle re-implements the *caller-side* set-up only: it mmap()s the page
 * backing the fixed RAM addresses (0xFFFF8000 covers 0xFFFF8930..0xFFFF8D76,
 * same MAP_FIXED trick as tests/host_oracle.c) and prints the int32_t return.
 * It contains NO copy of the search logic — that lives solely in
 * src/rx8_obd_dtc_find_643d4.c.
 *
 * Endianness: the LE host stores the 16-bit words natively, so the C lift's
 * volatile u16 read sees the same numeric word value the emulator's big-endian
 * mov.w read sees (the harness emits the byte order each side expects).
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* 0x643D4 — OBD DTC-table search leaf (see src/rx8_obd_dtc_find_643d4.c);
 * declared here rather than in rx8_samples.h, which is off-limits for this
 * task. */
int32_t rx8_obd_dtc_find_643d4(uint32_t r4);

#define DTC_BASE   0xFFFF8930u
#define DTC_STRIDE 0x34u
#define DTC_ROWS   0x15u
#define DTC_CURROW 0xFFFF8D74u

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

static uint8_t *rowp(uint32_t i)
{
    return (uint8_t *)(uintptr_t)(DTC_BASE + i * DTC_STRIDE);
}

int main(void)
{
    char line[2048];

    /* Back the page holding the DTC table (0xFFFF8930) through the currow
     * word (0xFFFF8D74) — all within page 0xFFFF8000. */
    map_page(0xFFFF8000u);

    while (fgets(line, sizeof line, stdin)) {
        char *tok;
        unsigned long r4, currow, w, b;
        uint32_t i;

        tok = strtok(line, " \t\r\n");
        if (!tok) {
            continue;                       /* blank line */
        }
        if (strcmp(tok, "dtc") != 0) {
            fprintf(stderr, "bad opcode: %s\n", tok);
            return 2;
        }
        r4 = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
        currow = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);

        for (i = 0; i < DTC_ROWS; i++) {
            w = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
            *(volatile uint16_t *)rowp(i) = (uint16_t)w;
        }
        for (i = 0; i < DTC_ROWS; i++) {
            b = strtoul(strtok(NULL, " \t\r\n"), NULL, 16);
            rowp(i)[0x06] = (uint8_t)b;
        }
        *(volatile uint16_t *)DTC_CURROW = (uint16_t)currow;

        printf("%08lX\n",
               (unsigned long)(uint32_t)rx8_obd_dtc_find_643d4((uint32_t)r4));
    }
    return 0;
}
