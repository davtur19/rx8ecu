/* ============================================================================
 * oracle_fpu_nop_stub.c  —  host test rig for rx8_fpu_nop_stub @0x2064
 * ============================================================================
 * Compile together with src/rx8_fpu_nop_stub.c and pipe test vectors on
 * stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     sr <value>       -> <resulting SR, %08X>
 *
 * <value> is the 32-bit word the ROM function loads into the Status Register
 * via its delay-slot `ldc r4,sr`.  The oracle prints the SR value the write
 * produces — the emulator's `ldc Rn,SR` is a raw full-width store, so the
 * oracle output must equal the input.  It contains NO copy of the function
 * logic; that lives solely in src/rx8_fpu_nop_stub.c.
 * ==========================================================================*/
#include <stdint.h>
#include <stdio.h>

#include "rx8_samples.h"

/* rx8_samples.h (shared, untouched by this sample) does not declare the
 * function under test; declare its prototype here instead. */
uint32_t rx8_fpu_nop_stub(uint32_t sr);

int main(void)
{
    char line[256];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long sr;

        if (sscanf(line, "sr %lx", &sr) == 1) {
            printf("%08lX\n",
                   (unsigned long)rx8_fpu_nop_stub((uint32_t)sr));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
