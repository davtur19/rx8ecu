/* ============================================================================
 * oracle_set_sr_param.c — host test rig for rx8_set_sr_param @0x2054
 * ============================================================================
 * Compile together with the reconstructed source (see
 * tests/harness_set_sr_param.py) and pipe vectors on stdin; one vector per
 * line:
 *
 *     set <cur_sr> <new_sr>     -> <stored> <final_sr> <ret>
 *
 * The oracle performs only the caller-side set-up (seed the SR state, poison
 * the store word) and prints the three observable results: the 32-bit word
 * written through the store pointer, the SR state after the call, and the
 * value returned by the function.  It contains NO copy of the function
 * logic — that lives solely in src/rx8_set_sr_param.c.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>

#include "rx8_samples.h"

/* Reconstructed function under test + SR-state accessors.  These prototypes
 * are kept here (not in rx8_samples.h) because the shared public header is
 * updated separately from the per-function verification harness. */
uint32_t rx8_set_sr_param(uint32_t *store, uint32_t new_sr);
uint32_t rx8_sr_read(void);
void     rx8_sr_write(uint32_t value);

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long cur, new_sr;

        if (sscanf(line, "set %lx %lx", &cur, &new_sr) != 2) {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }

        rx8_sr_write((uint32_t)cur);

        uint32_t store = 0xDEADBEEFu;   /* poison — must be overwritten */
        uint32_t ret = rx8_set_sr_param(&store, (uint32_t)new_sr);

        printf("%08lX %08lX %08lX\n",
               (unsigned long)store,
               (unsigned long)rx8_sr_read(),
               (unsigned long)ret);
    }
    return 0;
}
