/* ============================================================================
 * oracle_set_immo_light.c  —  host test rig for rx8_set_immo_light @0x263C8
 * ============================================================================
 * Reads one vector per line on stdin, whitespace-separated hex tokens:
 *
 *     sml <on> <lamp>      -> <lamp>
 *
 *   on   : 32-bit r4 argument (the ROM examines only its low byte:
 *          `extu.b r4,r0; cmp/eq #0x01` — 1 lights, anything else off)
 *   lamp : 16-bit initial value placed at RAM[0xFFFFF754] (RX8_STATUS_WORD,
 *          immo-lamp bits 0x20/0x40)
 *
 * Per vector the rig seeds the lamp register, calls rx8_set_immo_light(on),
 * then prints the resulting 16-bit word after the call.  The oracle contains
 * NO copy of the function logic — that lives solely in
 * src/rx8_set_immo_light.c.  It only mirrors the *caller-side* set-up: the
 * 0xFFFFF754 status word (page 0xFFFFF000) is backed with mmap(MAP_FIXED)
 * (same trick as oracle_immo_bad_state_set.c and tests/host_oracle.c), so
 * the volatile fixed-address pointer in the sample compiles and fault-free
 * on the host.  This is exactly what the ROM does on the SH-2E, where
 * 0xFFFFF754 is plain on-chip RAM.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_hw.h"

/* rx8_samples.h (shared, untouched by this task) does not declare the
 * function under test; declare its prototype here (same approach as
 * oracle_immo_bad_state_set.c). */
void rx8_set_immo_light(uint8_t on);

#define LAMP_ADDR 0xFFFFF754u   /* RX8_STATUS_WORD, immo-lamp bits 0x20/0x40 */

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

    /* Back the page holding the side-effected cell (0xFFFFF754 on page
     * 0xFFFFF000, above mmap_min_addr on this host). */
    map_page(0xFFFFF000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long on, lamp;

        if (sscanf(line, "sml %lx %lx", &on, &lamp) == 2) {
            /* Seed the lamp register, run the function, report it back. */
            *(volatile uint16_t *)(uintptr_t)LAMP_ADDR = (uint16_t)lamp;

            rx8_set_immo_light((uint8_t)on);

            printf("%04X\n",
                   (unsigned)*(volatile uint16_t *)(uintptr_t)LAMP_ADDR);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
