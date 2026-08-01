/* ============================================================================
 * oracle_bitfield_flag_status_decoder_339ac.c — host test rig for
 *                                               rx8_bitfield_flag_status_decoder_339ac @0x339AC
 * ============================================================================
 * Reads one vector per line on stdin, whitespace-separated hex tokens:
 *
 *     bfs <status>        -> <code>
 *
 *   status : flag/status byte value (0x00..0xFF) placed at RAM[0xFFFFCD4E]
 *   code   : the decoded status-code byte left at RAM[0xFFFFC04D],
 *            printed as %02X
 *
 * The oracle contains NO copy of the decoder logic — that lives solely in
 * src/rx8_bitfield_flag_status_decoder_339ac.c.  It only mirrors the
 * *caller-side* set-up: the two 0xFFFFxxxx RAM bytes are backed with
 * mmap(MAP_FIXED) pages (same trick as tests/host_oracle.c and
 * c/tests/test_*_49ED0.c), so the volatile fixed-address pointers in the
 * sample compile and fault-free on the host.  Both addresses fall in the
 * same 4 KiB page (0xFFFFC000..0xFFFFCFFF) on the host; they are distinct
 * on-chip-RAM bytes on the SH-2E target.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_samples.h (shared, untouched by this sample) does not declare the
 * function under test; declare its prototype here instead. */
void rx8_bitfield_flag_status_decoder_339ac(void);

/* Flag/status input byte @0xFFFFCD4E and decoded status-code byte @0xFFFFC04D
 * (same addresses as the ROM pool words 0x33A0E and 0x33A20). */
#define STATUS_IN_ADDR 0xFFFFCD4Eu
#define CODE_OUT_ADDR  0xFFFFC04Du

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

    /* Back the pages holding the status byte and the status-code byte
     * (the second map_page call re-maps the same page, which is harmless). */
    map_page(STATUS_IN_ADDR);
    map_page(CODE_OUT_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long status;

        if (sscanf(line, "bfs %lx", &status) == 1) {
            /* Seed the status byte, run the function, report the code byte. */
            *(volatile uint8_t *)(uintptr_t)STATUS_IN_ADDR = (uint8_t)status;
            rx8_bitfield_flag_status_decoder_339ac();
            printf("%02X\n",
                   (unsigned)*(volatile uint8_t *)(uintptr_t)CODE_OUT_ADDR);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
