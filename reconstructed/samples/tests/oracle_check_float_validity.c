/* ============================================================================
 * oracle_check_float_validity.c — host test rig for rx8_check_float_validity
 *                                  @0x46CC
 * ============================================================================
 * Compile together with samples/src/rx8_check_float_validity.c and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     flt <bits>                -> <result bit pattern>
 *              (32-bit IEEE-754 single-precision bit pattern, value order)
 *
 * The function is a pure FPU register-level leaf w.r.t. its return value
 * (the hardware fault-status store at 0xFFFF7304 is compiled out on host,
 * see the #if 0 in the source), so no mmap()ed pages are needed — the oracle
 * only decodes the single float argument and prints the single-precision
 * result as an integer bit pattern.  It contains NO copy of the validity
 * logic; that lives solely in the reconstructed source under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>

/* Declared locally: rx8_samples.h cannot be extended (parallel agents), and
 * this test rig only needs this one function. */
float rx8_check_float_validity(float value);

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
        unsigned long a;
        if (sscanf(line, "flt %lx", &a) == 1) {
            float out = rx8_check_float_validity(b2f((uint32_t)a));
            printf("%08X\n", f2b(out));
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
