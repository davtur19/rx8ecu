/* ============================================================================
 * oracle_saturate.c — host test rig for rx8_saturate @0x2404
 * ============================================================================
 * Compile together with samples/src/rx8_saturate.c and pipe test vectors on
 * stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     sat <sig> <lower> <upper>
 *              (32-bit IEEE-754 bit patterns, big-endian value order)
 *                                       -> <result bit pattern>
 *
 * The function is a pure register-level FPU leaf (no RAM side-effects), so no
 * mmap()ed pages are needed — the oracle only decodes the three float
 * arguments and prints the single-precision result as an integer bit pattern.
 * It contains NO copy of the clamp logic; that lives solely in the
 * reconstructed source under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>

/* Declared locally: rx8_samples.h cannot be extended (parallel agents), and
 * this test rig only needs this one function. */
float rx8_saturate(float sig, float lower, float upper);

static uint32_t f2b(float f)
{
    union { float f; uint32_t u; } x;
    x.f = f;
    return x.u;
}

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
        if (sscanf(line, "sat %lx %lx %lx", &a, &b, &c) == 3) {
            float out = rx8_saturate(b2f((uint32_t)a),
                                     b2f((uint32_t)b),
                                     b2f((uint32_t)c));
            printf("%08X\n", f2b(out));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
