/* ============================================================================
 * oracle_immo_bad_state_set.c  —  host test rig for
 *                                 rx8_immo_bad_state_set @0x365B8
 * ============================================================================
 * Reads one vector per line on stdin, whitespace-separated hex tokens:
 *
 *     ibs <lamp> <can> <timeout> <state>      -> <lamp> <can> <timeout> <state>
 *
 *   lamp    : 16-bit initial value placed at RAM[0xFFFFF754] (status word,
 *             immo-lamp bits 0x20/0x40)
 *   can     :  8-bit initial value placed at RAM[0xFFFFC240] (CAN TX flag)
 *   timeout : 16-bit initial value placed at RAM[0xFFFFC284] (bad-state ctr)
 *   state   :  8-bit initial value placed at RAM[0xFFFFC28D] (result code)
 *
 * Per vector the rig seeds those four cells, calls rx8_immo_bad_state_set(),
 * then prints the four resulting cells after the call.  The oracle contains
 * NO copy of the function logic — that lives solely in
 * src/rx8_immo_bad_state_set.c.  It only mirrors the *caller-side* set-up:
 * the three 0xFFFFCxxx cells (page 0xFFFFC000) and the 0xFFFFF754 status
 * word (page 0xFFFFF000) are backed with mmap(MAP_FIXED) pages (same trick
 * as tests/host_oracle.c and oracle_radiator_fan_relay_write.c), so the
 * volatile fixed-address pointers in the sample compile and fault-free on
 * the host.  This is exactly what the ROM does on the SH-2E, where all four
 * addresses are plain on-chip RAM.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_samples.h (shared, untouched by this task) does not declare the
 * function under test; declare its prototype here (same approach as
 * oracle_div32_signed.c). */
void rx8_immo_bad_state_set(void);

#define LAMP_ADDR    0xFFFFF754u   /* status word, immo-lamp bits 0x20/0x40 */
#define CAN_TX_ADDR  0xFFFFC240u   /* CAN TX data flag byte                */
#define TIMEOUT_ADDR 0xFFFFC284u   /* bad-state timeout word               */
#define STATE_ADDR   0xFFFFC28Du   /* state/result code byte               */

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

    /* Back the pages holding the side-effected cells: 0xFFFFC240/0xFFFFC284/
     * 0xFFFFC28D live on page 0xFFFFC000, 0xFFFFF754 on page 0xFFFFF000. */
    map_page(0xFFFFC000u);
    map_page(0xFFFFF000u);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long lamp, can, timeout, state;

        if (sscanf(line, "ibs %lx %lx %lx %lx",
                   &lamp, &can, &timeout, &state) == 4) {
            /* Seed the four cells, run the function, report them back. */
            *(volatile uint16_t *)(uintptr_t)LAMP_ADDR    = (uint16_t)lamp;
            *(volatile uint8_t  *)(uintptr_t)CAN_TX_ADDR  = (uint8_t)can;
            *(volatile uint16_t *)(uintptr_t)TIMEOUT_ADDR = (uint16_t)timeout;
            *(volatile uint8_t  *)(uintptr_t)STATE_ADDR   = (uint8_t)state;

            rx8_immo_bad_state_set();

            printf("%04X %02X %04X %02X\n",
                   (unsigned)*(volatile uint16_t *)(uintptr_t)LAMP_ADDR,
                   (unsigned)*(volatile uint8_t  *)(uintptr_t)CAN_TX_ADDR,
                   (unsigned)*(volatile uint16_t *)(uintptr_t)TIMEOUT_ADDR,
                   (unsigned)*(volatile uint8_t  *)(uintptr_t)STATE_ADDR);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
