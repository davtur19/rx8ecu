/* ============================================================================
 * oracle_math_primitives_2490.c — host test rig for the 0x2490 / 0x2500 /
 * 0x2510 math-primitive leaves
 * ============================================================================
 * Compile together with samples/src/rx8_math_primitives_2490.c (see
 * harness_math_primitives_2490.py for the exact command) and pipe test
 * vectors on stdin; one vector per line, whitespace-separated hex tokens:
 *
 *     f16 <number> <scalar> <offset>      -> <result>   (0x2490 float->u16 fp)
 *               number/scalar/offset = 32-bit IEEE-754 single patterns
 *                                          (SH-2E fr4/fr5/fr6)
 *                                          result = %04X clamped u16 (r0)
 *
 *     f8f <mult> <off> <raw>              -> <result>   (0x2500 u8 fp -> float)
 *               mult/off  = 32-bit IEEE-754 single patterns (SH-2E fr4/fr5)
 *               raw       = 8-bit fixed-point value      (SH-2E r4,  extu.b)
 *                                          result = %08X raw float bits (fr0)
 *
 *     fps <a> <b> <frac>                  -> <result>   (0x2510 int blend)
 *               a/b = 32-bit signed values (SH-2E r4/r5), frac = 16-bit (r6)
 *                                          result = %08X (r0)
 *
 * All three are pure register-level FPU/int leaves (no RAM side-effects), so
 * no mmap()ed pages are needed — the oracle only decodes the arguments and
 * prints the results.  It contains NO copy of the function logic; that lives
 * solely in the reconstructed source under test.
 * ==========================================================================*/
#include <stdio.h>
#include <stdint.h>

/* Declared locally: rx8_samples.h cannot be extended (parallel agents), and
 * this test rig only needs these three functions. */
uint16_t rx8_float_to_fixed_16bit(float number, float scalar, float offset);
float    rx8_fixed_point_to_float_8bit(float mult, float off, uint8_t raw);
int32_t  rx8_fixed_point_scaling(int32_t a, int32_t b, uint16_t frac);

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
        char op[8];
        unsigned long a, b, c;
        if (sscanf(line, "%7s %lx %lx %lx", op, &a, &b, &c) == 4) {
            if (op[0] == 'f' && op[1] == '1' && op[2] == '6') {
                uint16_t r = rx8_float_to_fixed_16bit(b2f((uint32_t)a),
                                                       b2f((uint32_t)b),
                                                       b2f((uint32_t)c));
                printf("%04X\n", (unsigned)r);
            } else if (op[0] == 'f' && op[1] == '8' && op[2] == 'f') {
                float r = rx8_fixed_point_to_float_8bit(b2f((uint32_t)a),
                                                        b2f((uint32_t)b),
                                                        (uint8_t)c);
                printf("%08X\n", f2b(r));
            } else if (op[0] == 'f' && op[1] == 'p' && op[2] == 's') {
                int32_t r = rx8_fixed_point_scaling((int32_t)(uint32_t)a,
                                                    (int32_t)(uint32_t)b,
                                                    (uint16_t)c);
                printf("%08lX\n", (unsigned long)(uint32_t)r);
            } else {
                fprintf(stderr, "bad op: %s\n", op);
                return 2;
            }
        } else {
            fprintf(stderr, "bad vector: %s", line);
            return 2;
        }
    }
    return 0;
}
