/* ============================================================================
 * oracle_get_engine_on_time_for_oil_metering.c — host rig for
 * rx8_get_engine_on_time_for_oil_metering @0xE492
 * ============================================================================
 * Compile together with samples/src/rx8_get_engine_on_time_for_oil_metering.c
 * and pipe test vectors on stdin; one vector per line, whitespace-separated
 * hex tokens:
 *
 *     omp <flag> <timer>            -> <timer_after>
 *
 *   flag  : byte seeded at RAM 0xFFFFA428 (the engine-running flag; the ROM
 *           accumulates ONLY when it is exactly 0x01)
 *   timer : 16-bit word seeded at RAM 0xFFFFA422 (the engine-on timer)
 *
 * The oracle re-implements only the *caller-side* set-up: it mmap()s the page
 * backing the two fixed RAM cells (same MAP_FIXED trick as tests/host_oracle.c
 * and tests/oracle_purge_flow_decrement.c) and prints the timer word after the
 * call, so the harness can verify the RAM side-effect byte-exactly.  It
 * contains NO copy of the function logic — that lives solely in the
 * reconstructed source under test.
 *
 * NOTE on the addresses: the ROM loads the cells with `mov.w @(disp,PC)` from
 * the 16-bit literals 0xA422 / 0xA428, which SIGN-EXTEND to the on-chip RAM
 * window addresses 0xFFFFA422 / 0xFFFFA428 used here (see the source header).
 * A native 16-bit store on the little-endian host gives the C lift the same
 * numeric word value the emulator's big-endian mov.w read sees.
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#include "rx8_samples.h"

/* rx8_get_engine_on_time_for_oil_metering is not (yet) declared in
 * rx8_samples.h — the reconstructed sources are dropped in without touching
 * the shared header. */
void rx8_get_engine_on_time_for_oil_metering(void);

#define OMP_FLAG_ADDR   0xFFFFA428u   /* u8  engine-running flag            */
#define OMP_TIMER_ADDR  0xFFFFA422u   /* u16 engine-on timer (in/out)       */

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

    /* Both cells live in the 0xFFFFA000 page of the 32 KB on-chip RAM window
     * (0xFFFF6000..0xFFFFDFFF); the address is well above mmap_min_addr, so
     * the fixed mapping succeeds. */
    map_page(OMP_FLAG_ADDR);

    while (fgets(line, sizeof line, stdin)) {
        unsigned long flag, timer;

        if (sscanf(line, "omp %lx %lx", &flag, &timer) == 2) {
            *(volatile uint8_t *)(uintptr_t)OMP_FLAG_ADDR = (uint8_t)flag;
            *(volatile uint16_t *)(uintptr_t)OMP_TIMER_ADDR = (uint16_t)timer;

            rx8_get_engine_on_time_for_oil_metering();

            printf("%04X\n", *(volatile uint16_t *)(uintptr_t)OMP_TIMER_ADDR);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
