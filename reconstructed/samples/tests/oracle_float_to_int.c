/* ============================================================================
 * oracle_float_to_int.c — host test rig for rx8_float_to_int @0x24D0
 * ============================================================================
 * Compile together with samples/src/rx8_float_to_int.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     f2i <signal> <mult> <offset>
 *              (32-bit IEEE-754 bit patterns, big-endian value order)
 *                                       -> <result>  (32-bit hex)
 *
 * The function is a pure register-level FPU leaf (no RAM side-effects), so no
 * mmap()ed pages are needed — the oracle only decodes the three float arguments
 * and prints the result.  It contains NO copy of the conversion logic; that
 * lives solely in the reconstructed source under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>

/* Declared locally: rx8_samples.h cannot be extended (parallel agents), and
 * this test rig only needs this one function. */
uint8_t rx8_float_to_int(float signal, float mult, float offset);

static float b2f(uint32_t u)
{
    union { float f; uint32_t u; } x;
    x.u = u;
    return x.f;
}

int main(void)
{
    char line[128];

    while (fgets(line, sizeof line, stdin)) {
        unsigned long a, b, c;
        if (sscanf(line, "f2i %lx %lx %lx", &a, &b, &c) == 3) {
            uint8_t out = rx8_float_to_int(b2f((uint32_t)a),
                                           b2f((uint32_t)b),
                                           b2f((uint32_t)c));
            printf("%08X\n", (unsigned)out);
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
