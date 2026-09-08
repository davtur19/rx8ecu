/*
 * test_m6_gap_sentinel.c — M6 regression: crank_sync_acquire must test the
 * stored gap domain (0/1), not the detector's internal 0xFF sentinel.
 *
 * Firmware sites: firmware/c/engine.c crank_gap_detect (:111-115 stores
 *   *gap_detect_r = 1 on gap, 0 on no-gap; 0xFF never reaches RAM) vs
 *   crank_sync_acquire (:389 non-running path, :406 running path testing
 *   `gap_r == 0xFF`). Consequence: *teeth_since=rotor_offset (:391) and the
 *   engine-running gap-toggle (:408-415) never executed.
 * Fix: test !=0 (gap) / ==0 (no gap) consistently.
 *
 * Host-self-contained model of detector store + both acquire paths.
 * Assertions: gap/no-gap vectors on teeth_since/gap_ctr transitions, and
 * the running-path toggle in both directions.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_m6_gap_sentinel.c -o /tmp/fwtest/test_m6_gap_sentinel
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

/* RAM mirrors */
static uint8_t gap_detect_r;
static uint8_t teeth_since;
static uint8_t gap_ctr;

/* Detector store model (engine.c:111-115): 1 on gap, 0 on no-gap. */
static void gap_store(int gap)
{
    gap_detect_r = gap ? 1 : 0;
}

/* Non-running acquire path (engine.c:378-398, ratio-above-limit taken). */
static void acquire_not_running(uint8_t rotor_offset)
{
    uint8_t gap_r = gap_detect_r;
#ifdef TEST_BUGGY
    if (gap_r == 0xFF) {
        teeth_since = rotor_offset;
    } else if (gap_r != 0) {
        gap_ctr = 1;
    } else {
        gap_ctr = 0;
    }
#else
    if (gap_r != 0) {
        teeth_since = rotor_offset;
    } else {
        gap_ctr = 0;
    }
#endif
}

/* Running-path gap toggle (engine.c:405-416). */
static void acquire_running_toggle(uint8_t rotor_offset)
{
    uint8_t gap_r = gap_detect_r;
#ifdef TEST_BUGGY
    if (gap_r == 0xFF) {
#else
    if (gap_r != 0) {
#endif
        if (rotor_offset == 0) {
            if (gap_ctr == 0) {
                gap_ctr = 1;
            } else {
                gap_ctr = 0;
            }
        }
    }
}

int main(void)
{
    /* Gap vector, not-running: teeth_since must take the rotor offset. */
    gap_store(1);
    teeth_since = 0xAA;
    gap_ctr = 0;
    acquire_not_running(6);
    CHECK(teeth_since == 6,
          "gap: teeth_since=%u want 6", teeth_since);

    /* Gap vector, rotor-A offset. */
    gap_store(1);
    teeth_since = 0xAA;
    gap_ctr = 0;
    acquire_not_running(0);
    CHECK(teeth_since == 0,
          "gap off=0: teeth_since=%u want 0", teeth_since);

    /* No-gap vector, not-running: gap_ctr must clear, teeth_since kept. */
    gap_store(0);
    teeth_since = 0xAA;
    gap_ctr = 1;
    acquire_not_running(6);
    CHECK(gap_ctr == 0, "no-gap: gap_ctr=%u want 0", gap_ctr);
    CHECK(teeth_since == 0xAA, "no-gap: teeth_since=%u want untouched 0xAA",
          teeth_since);

    /* Running toggle 0->1 on gap. */
    gap_store(1);
    gap_ctr = 0;
    acquire_running_toggle(0);
    CHECK(gap_ctr == 1, "running gap: gap_ctr=%u want 1", gap_ctr);

    /* Running toggle 1->0 on gap. */
    gap_store(1);
    gap_ctr = 1;
    acquire_running_toggle(0);
    CHECK(gap_ctr == 0, "running gap: gap_ctr=%u want 0", gap_ctr);

    /* Running, no gap: no toggle. */
    gap_store(0);
    gap_ctr = 0;
    acquire_running_toggle(0);
    CHECK(gap_ctr == 0, "running no-gap: gap_ctr=%u want 0", gap_ctr);

    if (failures == 0) {
        printf("PASS m6_gap_sentinel\n");
    } else {
        printf("%d FAILURES m6_gap_sentinel\n", failures);
    }
    return failures != 0;
}
