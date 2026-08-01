/* ============================================================================
 * oracle_float_to_fp_16bit.c — host test rig for 0x24C0 (fixed-point -> float)
 * ============================================================================
 * Compile together with samples/src/rx8_float_to_fp_16bit.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     fpf <raw> <mult> <off>
 *              raw  = 16-bit fixed-point value        (SH-2E r4,  extu.w)
 *              mult = 32-bit IEEE-754 single pattern  (SH-2E fr4)
 *              off  = 32-bit IEEE-754 single pattern  (SH-2E fr5)
 *                                       -> <result bit pattern> (fr0)
 *
 * The function is a pure register-level FPU leaf (no RAM side-effects), so no
 * mmap()ed pages are needed — the oracle only decodes the two float arguments
 * and prints the single-precision result as an integer bit pattern.  It
 * contains NO copy of the function logic; that lives solely in the
 * reconstructed source under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>

/* Declared locally: rx8_samples.h cannot be extended (parallel agents), and
 * this test rig only needs this one function. */
float rx8_fixed_point_to_float_16bit(float mult, float off, uint16_t raw);

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
        unsigned long raw, a, b;
        if (sscanf(line, "fpf %lx %lx %lx", &raw, &a, &b) == 3) {
            float out = rx8_fixed_point_to_float_16bit(
                b2f((uint32_t)a), b2f((uint32_t)b), (uint16_t)raw);
            printf("%08X\n", f2b(out));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
