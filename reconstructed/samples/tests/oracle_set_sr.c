/* ============================================================================
 * oracle_set_sr.c  —  host test rig for rx8_set_sr (samples/src/rx8_set_sr.c)
 * ============================================================================
 * Compile together with the reconstructed source and pipe test vectors on
 * stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     sr <init_sr> <sr_value> <sched>
 *                                       -> <result_sr>
 *
 *   <init_sr>   value the Status Register holds before the call
 *   <sr_value>  value handed to rx8_set_sr (the ROM's r4)
 *   <sched>     0/1  -> rx8_set_sr_scheduler_flag (0 = OS detour path)
 *
 * The oracle contains NO copy of the function logic — it only seeds the host
 * SR model, calls the reconstructed function under test, and prints the SR it
 * observes afterwards (mirroring the emulator, where cpu.sr is read after
 * cpu.call(0x3934, ...)).
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>

#include "rx8_samples.h"

/* Test hooks provided by rx8_set_sr.c (host model of the SH-2 SR). */
extern void     rx8_set_sr(uint32_t sr_value);
extern void     rx8_sr_write(uint32_t sr_value);
extern uint32_t rx8_sr_read(void);
extern void     rx8_set_sr_scheduler_flag(bool initialized);

int main(void)
{
    char line[128];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long init, val, sched;
        if (sscanf(line, "sr %lx %lx %lu", &init, &val, &sched) == 3) {
            rx8_set_sr_scheduler_flag(sched != 0);
            rx8_sr_write((uint32_t)init);
            rx8_set_sr((uint32_t)val);
            printf("%08lX\n", (unsigned long)rx8_sr_read());
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
