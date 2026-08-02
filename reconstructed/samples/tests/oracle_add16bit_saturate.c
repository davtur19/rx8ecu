/* ============================================================================
 * oracle_add16bit_saturate.c — host test rig for rx8_add16bit_saturate @0x2460
 * ============================================================================
 * Compile together with samples/src/rx8_add16bit_saturate.c (see
 * harness_add16bit_saturate.py for the exact command) and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     add <add1> <add2>                 -> <result>   (0x2460 saturating u16 add)
 *               add1/add2 = raw 32-bit SH-2 r4/r5 values (the ROM `extu.w`s
 *                           them to 16 bits, so high bits are dropped here too
 *                           by the uint16_t parameters)
 *                                          result = %04X (r0, clamped u16)
 *
 * This is a pure register-level integer leaf (no RAM side-effects), so no
 * mmap()ed pages are needed — the oracle only decodes the arguments and
 * prints the result.  It contains NO copy of the function logic; that lives
 * solely in the reconstructed source under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>

/* Declared locally: rx8_samples.h cannot be extended (parallel agents), and
 * this test rig only needs this one function. */
uint16_t rx8_add16bit_saturate(uint16_t add1, uint16_t add2);

int main(void)
{
    char line[64];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long a, b;
        if (sscanf(line, "add %lx %lx", &a, &b) == 2) {
            uint16_t r = rx8_add16bit_saturate((uint16_t)a, (uint16_t)b);
            printf("%04X\n", (unsigned)r);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
