/*
 * Host test for checkFloatValidity -- verifies IEEE 754 NaN/Inf detection.
 *
 * Build/run:
 *   cc -O2 c/checkFloatValidity.c c/tests/test_checkFloatValidity.c -o /tmp/t && /tmp/t
 *
 * WARNING: The C lift omits the write to hardware register 0xFFFF7304
 * (would segfault on host).  The write is validated in emulator tests.
 * This test only verifies the pass-through (returns same float value).
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

float checkFloatValidity(float value);

/* Helper: create a float from its IEEE 754 bit pattern */
static float make_float(uint32_t bits) {
    float f;
    memcpy(&f, &bits, 4);
    return f;
}

/* Compare floats by their bit pattern (handles NaN != NaN correctly) */
static int same_bits(float a, float b) {
    uint32_t ab, bb;
    memcpy(&ab, &a, 4);
    memcpy(&bb, &b, 4);
    return ab == bb;
}

int main(void)
{
    struct { uint32_t bits; const char *desc; } tests[] = {
        { 0x00000000u, "zero" },
        { 0x80000000u, "neg zero" },
        { 0x3F800000u, "1.0" },
        { 0x3F000000u, "0.5" },
        { 0xBF800000u, "-1.0" },
        { 0x7F800000u, "+inf" },
        { 0xFF800000u, "-inf" },
        { 0x7F800001u, "NaN (payload 1)" },
        { 0x7FC00000u, "NaN (quiet)" },
        { 0xFFC00000u, "NaN (quiet, neg)" },
        { 0x7F812345u, "NaN (payload 0x12345)" },
        { 0x00800000u, "min normal" },
        { 0x007FFFFFu, "max subnormal" },
        { 0x00000001u, "min subnormal" },
        { 0x7F7FFFFFu, "max normal" },
        { 0x4B000000u, "large normal (8388608.0)" },
    };

    for (int i = 0; i < sizeof(tests)/sizeof(tests[0]); i++) {
        float f = make_float(tests[i].bits);
        float r = checkFloatValidity(f);
        /* Must pass through same value (compare bits to handle NaN) */
        if (!same_bits(r, f)) {
            printf("FAIL: 0x%08X (%s): changed to 0x%08X\n",
                   tests[i].bits, tests[i].desc, *(uint32_t*)&r);
            return 1;
        }
    }

    printf("OK  checkFloatValidity: pass-through correct for %zu cases\n",
           sizeof(tests)/sizeof(tests[0]));
    return 0;
}
