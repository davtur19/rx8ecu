/*
 * test_h4_dwell_clamp.c — H4 regression: dwell must clamp the float BEFORE
 * converting to u16 (converting first is UB for out-of-range/negative inputs
 * and wraps mod 2^16 on SH-2 before the clamp can act).
 *
 * Firmware site: firmware/c/engine.c outputPerRotorIgnitionDwell (:461-471).
 * Policy (H4 decision): NaN -> 0 (coil inhibit — precedent in the same
 *   function: rotor_idx>3 -> dwell=0 inhibit; a weak MIN spark on a faulted
 *   input is worse than a clean inhibit). Finite values keep the MIN/MAX
 *   clamp; NaN is detected by self-comparison (`!(x >= MIN)` alone would
 *   fold NaN into MIN, the old verified-green behavior).
 *
 * Host note: float->u16 out-of-range is UB on the host too; the buggy model
 *   below exhibits the defect host-observably on huge positive inputs
 *   (saturates to MIN instead of MAX). The SH-2 wrap case (raw=-2e6 ->
 *   dwell=5000, want 500) is documented in comments.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_h4_dwell_clamp.c -o /tmp/fwtest/test_h4_dwell_clamp
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>
#include <math.h>

#define DWELL_MIN_US     500
#define DWELL_MAX_US     5000
#define DWELL_BASE_DIVISOR 1000

/* Pre-fix: convert first, clamp after (firmware/c/engine.c:463-471). */
uint16_t buggy_dwell(float raw)
{
    float divided = raw / (float)DWELL_BASE_DIVISOR;
    uint16_t dwell_time_us = (uint16_t)divided;
    if (dwell_time_us < DWELL_MIN_US) {
        dwell_time_us = DWELL_MIN_US;
    }
    if (dwell_time_us > DWELL_MAX_US) {
        dwell_time_us = DWELL_MAX_US;
    }
    return dwell_time_us;
}

/* Fixed: NaN inhibits (0); finite values clamp the float first. */
uint16_t fixed_dwell(float raw)
{
    float divided = raw / (float)DWELL_BASE_DIVISOR;
    if (divided != divided) {
        return 0;
    }
    if (divided < (float)DWELL_MIN_US) {
        divided = (float)DWELL_MIN_US;
    } else if (divided > (float)DWELL_MAX_US) {
        divided = (float)DWELL_MAX_US;
    }
    return (uint16_t)divided;
}

#ifdef TEST_BUGGY
#define DWELL buggy_dwell
#else
#define DWELL fixed_dwell
#endif

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

int main(void)
{
    struct {
        float in;
        uint16_t want;
    } vecs[] = {
        {-1000000.0f, 500},
        {-1.0f, 500},
        {0.0f, 500},
        {499900.0f, 500},    /* 499.9 us */
        {500000.0f, 500},
        {2500000.0f, 2500},
        {5000000.0f, 5000},
        {5000100.0f, 5000},  /* 5000.1 us */
        {100000000.0f, 5000},
        {NAN, 0},              /* policy: NaN -> inhibit (dwell 0) */
    };

    for (unsigned i = 0; i < 10; i++) {
        /* volatile: forces a runtime float->u16 conversion. A constant
         * input would let gcc fold the UB conversion at compile time
         * (different result than the runtime cvttss2si path). */
        volatile float vin = vecs[i].in;
        uint16_t got = DWELL(vin);
        CHECK(got == vecs[i].want, "in=%f got=%u want=%u",
              (double)vecs[i].in, got, vecs[i].want);
        if (vecs[i].in == vecs[i].in) { /* finite inputs stay in range */
            CHECK(got >= DWELL_MIN_US && got <= DWELL_MAX_US,
                  "in=%f out of range: %u", (double)vecs[i].in, got);
        }
    }

#ifndef TEST_BUGGY
    /* Repro: negative/huge sources must saturate, but convert-first wraps
     * (runtime cvttss2si -> int -> truncate mod 2^16, then the clamp sees a
     * huge u16 and pins MAX). On SH-2, raw=-2e6 -> quotient -2000us ->
     * wraps to 63536 -> 5000 (want 500). */
    {
        volatile float vneg = -1000000.0f;
        volatile float vn2 = -2000000.0f;
        CHECK(buggy_dwell(vneg) != fixed_dwell(vneg),
              "repro: buggy(-1e6)=%u fixed=%u must differ",
              buggy_dwell(vneg), fixed_dwell(vneg));
        CHECK(fixed_dwell(vn2) == 500, "fixed(-2e6) must be 500");
    }
#endif

    if (failures == 0) {
        printf("PASS h4_dwell_clamp\n");
    } else {
        printf("%d FAILURES h4_dwell_clamp\n", failures);
    }
    return failures != 0;
}
