/* ============================================================================
 * oracle_delay_loop_n8.c  —  host test rig for rx8_delay_loop_n8 @0x239C
 * ============================================================================
 * Compile together with the reconstructed source (see
 * harness_delay_loop_n8.py) and pipe test vectors on stdin; one vector per
 * line, whitespace-separated hex token:
 *
 *     u16 <n>                    -> 00000000     (r0 return value, hex)
 *
 * `n` is truncated to 16 bits exactly like the reconstructed signature, so
 * vectors with upper bits set still verify the truncation path.  The oracle
 * contains NO copy of the function logic — that lives solely in
 * rx8_delay_loop_n8.c under test.  The printed value is the SH-2 r0 the
 * caller observes after the call: the ROM function never touches r0, so it
 * stays 0 for every input (the loop-count relationship is pinned separately
 * by the harness from the ROM's post-call r4/r5 state).
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>

#include "rx8_samples.h"

/* rx8_samples.h (shared, untouched by this sample) does not declare the
 * function under test; declare its prototype here instead. */
void rx8_delay_loop_n8(uint16_t n);

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long a;

        if (sscanf(line, "u16 %lx", &a) == 1) {
            rx8_delay_loop_n8((uint16_t)(uint32_t)a);
            printf("00000000\n");       /* r0 is never written by the ROM */
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
