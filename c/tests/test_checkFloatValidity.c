/*
 * Host test for checkFloatValidity -- verifies the soft-float SQUARE ROOT
 * semantics of ROM entry 0x46CC (frexp@0x48C8 -> fixed-point sqrt@0x4740 ->
 * ldexp@0x481C), including the fault-code write for non-finite results.
 *
 * Build/run (helpers must be linked in -- they are separate lifts):
 *   cc -O2 c/checkFloatValidity.c c/bitfield_extract_merge.c c/div_4740.c \
 *          c/ldexp_481C.c c/tests/test_checkFloatValidity.c -o /tmp/t && /tmp/t
 *
 * The lift redirects its fault write (default 0xFFFF7304, real ECU MMIO) to a
 * local sink so the host build never touches hardware; the fault code is
 * asserted separately: 0x044C = result is +Inf, 0x044D = result is NaN.
 *
 * Reference oracle: c/tests/test_check_float_validity_0x46CC.py (bit-exact
 * vs the emulated ROM over 100k+ random float inputs per seed).  Expected
 * bit patterns below were confirmed against that oracle.
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

float checkFloatValidity(float value);
extern volatile uint32_t *checkFloatValidity_fault_addr;

/* Helper: create a float from its IEEE 754 bit pattern */
static float make_float(uint32_t bits) {
    float f;
    memcpy(&f, &bits, 4);
    return f;
}

static uint32_t float_bits(float f) {
    uint32_t b;
    memcpy(&b, &f, 4);
    return b;
}

int main(void)
{
    /*
     * {input bits, expected result bits, expected fault code}:
     *   fault 0x044C = +Inf result, 0x044D = NaN result, 0 = finite (no write).
     */
    struct { uint32_t in, out, fault; } tests[] = {
        { 0x00000000u, 0x00000000u, 0x0000u },   /* sqrt(0.0)  = 0.0          */
        { 0x80000000u, 0x80000000u, 0x0000u },   /* sqrt(-0.0) = -0.0         */
        { 0x3F800000u, 0x3F800000u, 0x0000u },   /* sqrt(1.0)  = 1.0          */
        { 0x40800000u, 0x40000000u, 0x0000u },   /* sqrt(4.0)  = 2.0          */
        { 0x41100000u, 0x40400000u, 0x0000u },   /* sqrt(9.0)  = 3.0          */
        { 0x3E800000u, 0x3F000000u, 0x0000u },   /* sqrt(0.25) = 0.5          */
        { 0x40000000u, 0x3FB504F3u, 0x0000u },   /* sqrt(2.0)  = 1.4142135    */
        { 0x00800000u, 0x20000000u, 0x0000u },   /* sqrt(min normal) = 2^-63  */
        { 0x007FFFFFu, 0x1FFFFFFEu, 0x0000u },   /* sqrt(max subnormal)       */
        { 0x7F7FFFFFu, 0x5F7FFFFFu, 0x0000u },   /* sqrt(max normal)          */
        { 0x7F800000u, 0x7F800000u, 0x044Cu },   /* sqrt(+inf) = +inf (0x44C) */
        { 0xFF800000u, 0x7F800001u, 0x044Du },   /* sqrt(-inf) = NaN  (0x44D) */
        { 0xBF800000u, 0x7F800001u, 0x044Du },   /* sqrt(-1.0) = NaN (0x44D)  */
        { 0x7FC00000u, 0x7F800001u, 0x044Du },   /* sqrt(NaN)   = NaN (0x44D) */
        { 0xFFC00000u, 0x7F800001u, 0x044Du },   /* sqrt(-NaN)  = NaN (0x44D) */
    };

    uint32_t sink = 0;
    checkFloatValidity_fault_addr = &sink;

    for (int i = 0; i < (int)(sizeof(tests) / sizeof(tests[0])); i++) {
        sink = 0;
        float r = checkFloatValidity(make_float(tests[i].in));
        uint32_t rb = float_bits(r);
        if (rb != tests[i].out || sink != tests[i].fault) {
            printf("FAIL[%d] in=0x%08X: got out=0x%08X fault=0x%X; "
                   "want out=0x%08X fault=0x%X\n",
                   i, tests[i].in, rb, sink, tests[i].out, tests[i].fault);
            return 1;
        }
    }

    printf("OK  checkFloatValidity: sqrt-chain matches oracle for %zu cases "
           "(result bits + fault code)\n",
           sizeof(tests) / sizeof(tests[0]));
    return 0;
}
