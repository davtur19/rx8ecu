/* ============================================================================
 * oracle_add_saturate_8bit.c — host test rig for rx8_add_saturate_8bit @0x2478
 * ============================================================================
 * Compile together with samples/src/rx8_add_saturate_8bit.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     add8 <add1> <add2>
 *              (both 8-bit values; SH-2E r4/r5, extu.b-masked)
 *                                       -> <result u8 as %02X>   (r0)
 *
 * The function is a pure register-level leaf (no RAM side-effects, no stack
 * frame), so no mmap()ed pages are needed — the oracle only decodes the two
 * byte arguments and prints the u8 result.  It contains NO copy of the
 * saturating-add logic; that lives solely in the reconstructed source under
 * test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>

/* Declared locally: rx8_samples.h cannot be extended (parallel agents), and
 * this test rig only needs this one function. */
uint8_t rx8_add_saturate_8bit(uint8_t add1, uint8_t add2);

int main(void)
{
    char line[128];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long a, b;
        if (sscanf(line, "add8 %lx %lx", &a, &b) == 2) {
            uint8_t out = rx8_add_saturate_8bit((uint8_t)a, (uint8_t)b);
            printf("%02X\n", (unsigned)out);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
