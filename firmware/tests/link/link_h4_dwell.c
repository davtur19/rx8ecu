/*
 * link_h4_dwell.c — Link pilot h4: compile-link-run against the REAL
 * outputPerRotorIgnitionDwell in firmware/c/engine.c (H4 float-clamp +
 * NaN-inhibit fix), not a model replica.
 *
 * Mechanism proof: links the real engine.c TU (with -DFW_HOST_TEST so the
 * host-only getDwellTimeUs_forHostTest accessor is compiled in), so a
 * firmware revert of the H4 fix (clamp-after-convert, or NaN folding into
 * DWELL_MIN_US) fails this binary at run time, a rotor-source regression
 * (rotor 0/1 reading 0xFFFFBC88 instead of 0xFFFFBC84) fails at run time,
 * and a signature change fails at compile time (extern decl via engine.h).
 *
 * Refactor-path coverage:
 *   - MMIO literals: engine.c:475/478 hard-code 0xFFFFBC84/0xFFFFBC88 as
 *     bare literals (NOT header macros), so the test pins the same
 *     addresses as local constants — a firmware move of the dwell source
 *     must also move this mapping or (a)/(b) fail loudly.
 *   - Float clamp path: raw/DWELL_BASE_DIVISOR, clamp to
 *     [DWELL_MIN_US, DWELL_MAX_US] BEFORE the u16 convert.
 *   - NaN inhibit: self-comparison (`divided != divided`) -> dwell 0.
 *   - Rotor routing: 0/1 -> lead word 0xFFFFBC84, 2/3 -> trail word
 *     0xFFFFBC88, >3 -> early return 0 (no MMIO read).
 *
 * Host execution boundary (same mechanism as link_m2_checksum):
 *   - Zero stubs: engine.c has no undefined externs (`nm -u engine.o`
 *     clean) — exactly like can.c (h1) and dtc.c (m2).
 *   - MMIO is real: the SH-2 0xFFFFBxxx page does not exist on the host
 *     (bare deref segfaults), so the test maps ONE 4 KiB page at 0xFFFFB000
 *     with mmap(MAP_FIXED) covering both dwell words (0xFFFFBC84/0xC88).
 *     The function only READS through the pointer; the test writes the
 *     float sources before each call. No constructor/ init-time MMIO runs
 *     at load (engine.c file-scope statics are plain zero-init).
 *   - Accessor: dwell_time_us is file-static with no production getter;
 *     -DFW_HOST_TEST exposes getDwellTimeUs_forHostTest (engine.c/.h),
 *     compiled out of every normal build.
 *
 * Proves:
 *   (a) rotor 0/1 read the lead word, rotor 2/3 the trail word
 *       (same input, different sources -> different dwell);
 *   (b) mid-range value: raw/DWELL_BASE_DIVISOR truncates to u16
 *       (2500000/1000 -> 2500);
 *   (c) low clamp: raw below DWELL_MIN_US*divisor -> DWELL_MIN_US
 *       (not a convert-first wrap);
 *   (d) high clamp: raw above DWELL_MAX_US*divisor -> DWELL_MAX_US;
 *   (e) NaN source -> dwell 0 (coil inhibit, H4 policy);
 *   (f) rotor_idx > 3 -> dwell 0 (invalid-index inhibit).
 *
 * Build (see firmware/tests/Makefile link-check):
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 -I../include -DFW_HOST_TEST \
 *       link/link_h4_dwell.c ../c/engine.c -o /tmp/fwtest/link_h4_dwell
 */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>

#include "engine.h"

#ifndef FW_HOST_TEST
#error "link_h4_dwell must build with -DFW_HOST_TEST (host-test accessor)"
#endif

/* Extern declaration comes from the real engine.h (linking the real
 * engine.c TU): a signature change in firmware breaks this build. Pin the
 * H4 contract values so a revert breaks the build, not just the run. */
_Static_assert(DWELL_MIN_US == 500, "DWELL_MIN_US revert");
_Static_assert(DWELL_MAX_US == 5000, "DWELL_MAX_US revert");
_Static_assert(DWELL_BASE_DIVISOR == 1000, "DWELL_BASE_DIVISOR revert");

/* The dwell-source literals live in the .c body (not header macros), so
 * pin the addresses the test maps — a firmware move of 0xFFFFBC84/88 must
 * also move this mapping or (a) fails loudly. Both words share the
 * 0xFFFFB000 4 KiB page (offsets 0xC84 / 0xC88). */
#define H4_PAGE_BASE  0xFFFFB000u
#define H4_PAGE_LEN   0x1000u
#define H4_DWELL_LEAD 0xFFFFBC84u  /* can_addr_copy_57 — rotors 0/1 */
#define H4_DWELL_TRAIL 0xFFFFBC88u /* can_addr_copy_58 — rotors 2/3 */

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

static volatile float *h4_f32(uint32_t addr)
{
    return (volatile float *)(uintptr_t)addr;
}

/* Expected result for a finite source: float divide, clamp, truncate —
 * the exact contract of the real function. Inputs below are chosen so the
 * division is exact in binary float (no rounding epsilon needed); the
 * compare is on the stored integer microseconds. */
static uint16_t h4_expect_u16(float raw)
{
    float d = raw / (float)DWELL_BASE_DIVISOR;
    if (d != d)
        return 0;
    if (d < (float)DWELL_MIN_US)
        d = (float)DWELL_MIN_US;
    else if (d > (float)DWELL_MAX_US)
        d = (float)DWELL_MAX_US;
    return (uint16_t)d;
}

static void h4_check_rotor(uint8_t rotor_idx, float raw, uint16_t want,
                           const char *what)
{
    uint16_t got;

    outputPerRotorIgnitionDwell(rotor_idx);
    got = getDwellTimeUs_forHostTest();
    CHECK(got == want, "%s: rotor %u got %u want %u (raw=%g)",
          what, (unsigned)rotor_idx, (unsigned)got, (unsigned)want,
          (double)raw);
    /* Sanity: want itself must be the contract value (guards against a
     * typo in the expectation table drifting with a broken helper). */
    CHECK(want == h4_expect_u16(raw) || raw != raw,
          "%s: expectation %u != contract %u",
          what, (unsigned)want, (unsigned)h4_expect_u16(raw));
}

/* (f) invalid-index inhibit, NON-VACUOUS form: prime dwell_time_us with a
 * known nonzero value (valid rotor 0, mid-range lead source 2500000 ->
 * 2500) and assert the prime itself BEFORE probing the invalid rotor.
 * Without the prime, the preceding NaN test leaves dwell_time_us == 0, so
 * a mutant that deletes the invalid-index zero-store (early return only)
 * would still read 0 and pass. With the prime, that mutant leaves 2500
 * and fails the == 0 assert. Requires the caller to have set the lead
 * dwell source to 2500000.0f beforehand. */
static void h4_check_invalid(uint8_t rotor_idx)
{
    outputPerRotorIgnitionDwell(0);
    CHECK(getDwellTimeUs_forHostTest() == 2500,
          "prime rotor 0 -> %u want 2500",
          (unsigned)getDwellTimeUs_forHostTest());
    outputPerRotorIgnitionDwell(rotor_idx);
    CHECK(getDwellTimeUs_forHostTest() == 0,
          "rotor %u -> %u want 0", (unsigned)rotor_idx,
          (unsigned)getDwellTimeUs_forHostTest());
}

int main(void)
{
    void *p = mmap((void *)(uintptr_t)H4_PAGE_BASE, H4_PAGE_LEN,
                   PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == (void *)-1) {
        printf("FAIL: mmap(0xFFFFB000) failed\n");
        return 1;
    }

    /* (a)+(b) rotor routing + mid-range divide: distinct sources so a
     * swapped lead/trail word cannot produce the same dwell by luck. */
    *h4_f32(H4_DWELL_LEAD)  = 2500000.0f; /* -> 2500 us */
    *h4_f32(H4_DWELL_TRAIL) = 1000000.0f; /* -> 1000 us */
    h4_check_rotor(0, 2500000.0f, 2500, "lead route");
    h4_check_rotor(1, 2500000.0f, 2500, "lead route");
    h4_check_rotor(2, 1000000.0f, 1000, "trail route");
    h4_check_rotor(3, 1000000.0f, 1000, "trail route");

    /* Cross-check: rotor 0 must track the LEAD word only. */
    *h4_f32(H4_DWELL_LEAD)  = 1500000.0f; /* -> 1500 */
    *h4_f32(H4_DWELL_TRAIL) = 3000000.0f; /* -> 3000 */
    h4_check_rotor(0, 1500000.0f, 1500, "lead tracks lead word");
    h4_check_rotor(2, 3000000.0f, 3000, "trail tracks trail word");

    /* (c) low clamp: 499.9 us -> DWELL_MIN_US (clamp-before-convert). */
    *h4_f32(H4_DWELL_LEAD) = 499900.0f;
    h4_check_rotor(0, 499900.0f, DWELL_MIN_US, "low clamp");
    *h4_f32(H4_DWELL_LEAD) = 0.0f;
    h4_check_rotor(0, 0.0f, DWELL_MIN_US, "zero source");

    /* (d) high clamp: 5000.1 us and a huge source -> DWELL_MAX_US
     * (convert-first would wrap/UB here on SH-2). */
    *h4_f32(H4_DWELL_LEAD) = 5000100.0f;
    h4_check_rotor(0, 5000100.0f, DWELL_MAX_US, "high clamp");
    *h4_f32(H4_DWELL_LEAD) = 100000000.0f;
    h4_check_rotor(0, 100000000.0f, DWELL_MAX_US, "huge clamp");

    /* (e) NaN source -> dwell 0 (H4 inhibit policy, not MIN).
     * Note: x86 (uint16_t)NaN -> 0, so the explicit `divided != divided`
     * branch is covered by the Makefile gate grep, not by this runtime. */
    *h4_f32(H4_DWELL_LEAD) = NAN;
    h4_check_rotor(0, NAN, 0, "NaN inhibit");

    /* (f) invalid rotor index -> dwell 0 (early return, no MMIO).
     * h4_check_invalid primes a nonzero dwell before each probe (F1). */
    *h4_f32(H4_DWELL_LEAD) = 2500000.0f;
    *h4_f32(H4_DWELL_TRAIL) = 2500000.0f;
    h4_check_invalid(4);
    h4_check_invalid(255);

    munmap(p, H4_PAGE_LEN);

    if (failures == 0) {
        printf("PASS link_h4_dwell (real engine.c TU)\n");
    } else {
        printf("%d FAILURES link_h4_dwell\n", failures);
    }
    return failures != 0;
}
