/* ============================================================================
 * oracle_purge_control_state_update.c  —  host rig for rx8_purge_control_state_update
 * ============================================================================
 * Compile together with samples/src/rx8_purge_control_state_update.c and pipe
 * test vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     purge <c0> <c1> <c2> <c3> <c4> <c5> <trig> <fd> <alt> <flow0> <state0> <demand0>
 *                                             -> <flow> <state> <demand>
 *
 *   c0..c5      : the 6 calibration bytes the ROM reads at 0x792FC..0x79301
 *   trig        : purge trigger byte (RAM[0xFFFFBED0], the ROM's 0x104C8 leaf)
 *   fd          : purge flow demand byte (RAM[0xFFFF9F94])
 *   alt         : alternate trigger byte (RAM[0xFFFFCE6E])
 *   flow0/state0/demand0 : pre-state of the three purge cells the function
 *                 (re)writes (RAM[0xFFFFA4B0 / 0xFFFFA4B1 / 0xFFFFA4B3)
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the pages
 * backing the RAM cells AND the ROM calibration table, seeds every byte and
 * prints the three post-state bytes.  It contains NO copy of the function
 * logic — that lives solely in the reconstructed source under test.
 *
 * Pages mapped (all above mmap_min_addr on this host):
 *   0x00079000  ROM calibration table (0x792FC..0x79301)
 *   0xFFFF9000  RAM[0xFFFF9F94] flow demand
 *   0xFFFFA000  RAM[0xFFFFA4B0/1/2/3] purge cells
 *   0xFFFFB000  RAM[0xFFFFBED0] trigger (read by the 0x104C8 leaf)
 *   0xFFFFC000  RAM[0xFFFFCE6E] alt trigger
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_purge_control_state_update is not (yet) in rx8_samples.h — the shared
 * header is owned by the samples build.  The reconstructed source itself
 * carries the authoritative definition (src/rx8_purge_control_state_update.c);
 * this prototype mirrors it exactly. */
void rx8_purge_control_state_update(void);

#define ROM_TABLE_BASE      0x00079000u
#define ROM_TABLE_ADDR      0x000792FCu   /* 6 calibration bytes              */
#define FLOW_DEMAND_ADDR    0xFFFF9F94u   /* u8 purge flow demand input       */
#define ALT_TRIGGER_ADDR    0xFFFFCE6Eu   /* u8 alternate purge trigger       */
#define PURGE_TRIGGER_ADDR  0xFFFFBED0u   /* u8 purge trigger (leaf 0x104C8)  */
#define PURGE_FLOW_ADDR     0xFFFFA4B0u   /* u8 published flow counter        */
#define PURGE_STATE_ADDR    0xFFFFA4B1u   /* u8 selected purge state          */
#define PURGE_DEMAND_ADDR   0xFFFFA4B3u   /* u8 latched flow demand           */

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

    map_page(ROM_TABLE_BASE);
    map_page(FLOW_DEMAND_ADDR);
    map_page(ALT_TRIGGER_ADDR);
    map_page(PURGE_TRIGGER_ADDR);
    map_page(PURGE_FLOW_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long c0, c1, c2, c3, c4, c5;
        unsigned long trig, fd, alt, flow0, state0, demand0;
        int n = sscanf(line,
                       "purge %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %lx",
                       &c0, &c1, &c2, &c3, &c4, &c5,
                       &trig, &fd, &alt, &flow0, &state0, &demand0);
        if (n != 12) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        /* Seed the ROM calibration table exactly as the stock bin has it. */
        *(volatile uint8_t *)(uintptr_t)(ROM_TABLE_ADDR + 0) = (uint8_t)c0;
        *(volatile uint8_t *)(uintptr_t)(ROM_TABLE_ADDR + 1) = (uint8_t)c1;
        *(volatile uint8_t *)(uintptr_t)(ROM_TABLE_ADDR + 2) = (uint8_t)c2;
        *(volatile uint8_t *)(uintptr_t)(ROM_TABLE_ADDR + 3) = (uint8_t)c3;
        *(volatile uint8_t *)(uintptr_t)(ROM_TABLE_ADDR + 4) = (uint8_t)c4;
        *(volatile uint8_t *)(uintptr_t)(ROM_TABLE_ADDR + 5) = (uint8_t)c5;

        /* Seed the input RAM cells + the purge-cell pre-states. */
        *(volatile uint8_t *)(uintptr_t)PURGE_TRIGGER_ADDR   = (uint8_t)trig;
        *(volatile uint8_t *)(uintptr_t)FLOW_DEMAND_ADDR     = (uint8_t)fd;
        *(volatile uint8_t *)(uintptr_t)ALT_TRIGGER_ADDR     = (uint8_t)alt;
        *(volatile uint8_t *)(uintptr_t)PURGE_FLOW_ADDR      = (uint8_t)flow0;
        *(volatile uint8_t *)(uintptr_t)PURGE_STATE_ADDR     = (uint8_t)state0;
        *(volatile uint8_t *)(uintptr_t)PURGE_DEMAND_ADDR    = (uint8_t)demand0;

        rx8_purge_control_state_update();

        printf("%02X %02X %02X\n",
               *(volatile uint8_t *)(uintptr_t)PURGE_FLOW_ADDR,
               *(volatile uint8_t *)(uintptr_t)PURGE_STATE_ADDR,
               *(volatile uint8_t *)(uintptr_t)PURGE_DEMAND_ADDR);
    }
    return 0;
}
