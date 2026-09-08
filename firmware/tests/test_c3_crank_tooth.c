/*
 * test_c3_crank_tooth.c — C3 regression: the crank tooth counter saturates
 * at 0xFF (no wrap); the rotor A/B map derives a LOCAL count % 20 without
 * touching the global.
 *
 * Firmware sites: firmware/c/engine.c crank_tooth_count (decl :36, FULL_SYNC
 *   arms :163 `==0x1C || ==0x0A`), crank_timing_update (ISR entry, saturating
 *   increment), rotor_position_synchronization (local % 20 map, no global
 *   write-back).
 * IDA evidence: docs/notes/IDA_ANALYSIS.md:449-460 (session ae00d360) —
 *   tooth counter at 0xFFFF9FC2 "saturates at 0xFF" (no wrap); state-machine
 *   byte at 0xFFFF9F95 "max 0x24". A wrapping 0..19 counter can never reach
 *   the 0x1C (28) FULL_SYNC arm, so wrap-20 was dropped for saturation.
 *   TRIGGER_TOTAL_TEETH comment `3x6+1` = 19 != 20 is incoherent; the value
 *   20 is kept as the rotor-map modulus only.
 *
 * Host-self-contained model of ISR x 300 ticks: asserts 0..255 saturation,
 * both FULL_SYNC arms fire (tooth-10 and tooth-28), and the rotor map does
 * not mutate the global.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_c3_crank_tooth.c -o /tmp/fwtest/test_c3_crank_tooth
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

#define TRIGGER_TEETH_PER_ROTOR 6
#define TRIGGER_TOTAL_TEETH     20

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

static uint8_t count;

#ifdef TEST_BUGGY
/* Pre-fix ISR entry: 20-tooth wrap (kills the 0x1C arm). */
static void isr_tick_buggy(void)
{
    count++;
    if (count >= TRIGGER_TOTAL_TEETH) {
        count = 0;
    }
}
#else
/* Fixed ISR entry: saturate at 0xFF, no wrap. */
static void isr_tick_fixed(void)
{
    if (count < 0xFF) {
        count++;
    }
}
#endif

/* FULL_SYNC arm check copied from crank_position_state_machine (:163). */
#ifdef TEST_BUGGY
static int full_sync_arm(uint8_t c)
{
    return (c == 0x1C || c == 0x0A);
}
#endif

/* Rotor map copied from rotor_position_synchronization (local % 20). */
#ifdef TEST_BUGGY
static uint8_t map_global_write = 0;

/* Pre-fix rotor map: else-branch resets the GLOBAL counter. */
static void rotor_map_buggy(uint8_t c, uint8_t *rotor_id, uint8_t *rotor_pos)
{
    if (c < 10) {
        *rotor_id = 0;
        *rotor_pos = (uint8_t)(c % TRIGGER_TEETH_PER_ROTOR);
    } else if (c < 20) {
        *rotor_id = 1;
        *rotor_pos = (uint8_t)((c - 10) % TRIGGER_TEETH_PER_ROTOR);
    } else {
        count = 0; /* write side effect on the global */
        map_global_write = 1;
        *rotor_id = 0;
        *rotor_pos = 0;
    }
}
#else
static void rotor_map(uint8_t c, uint8_t *rotor_id, uint8_t *rotor_pos)
{
    uint8_t local = (uint8_t)(c % TRIGGER_TOTAL_TEETH);
    if (local < 10) {
        *rotor_id = 0;
        *rotor_pos = (uint8_t)(local % TRIGGER_TEETH_PER_ROTOR);
    } else {
        *rotor_id = 1;
        *rotor_pos = (uint8_t)((local - 10) % TRIGGER_TEETH_PER_ROTOR);
    }
}
#endif

int main(void)
{
#ifdef TEST_BUGGY
    /* ISR x 300 ticks with wrap-20: must NOT saturate (repro of the bug). */
    count = 0;
    int arm_0a = 0, arm_1c = 0;
    for (int tick = 1; tick <= 300; tick++) {
        isr_tick_buggy();
        if (full_sync_arm(count)) {
            if (count == 0x0A) {
                arm_0a = 1;
            }
            if (count == 0x1C) {
                arm_1c = 1;
            }
        }
    }
    CHECK(count == 0xFF, "tick 300 count=%u want saturate 255", count);
    CHECK(arm_0a, "tooth-10 arm never fired in 300 ticks");
    CHECK(arm_1c, "tooth-28 arm never fired in 300 ticks");
    {
        uint8_t rid, rpos;
        count = 28;
        map_global_write = 0;
        rotor_map_buggy(count, &rid, &rpos);
        CHECK(!map_global_write, "rotor map mutated the global counter");
        CHECK(count == 28, "global=%u want untouched 28", count);
        CHECK(rid == 0 && rpos == 2, "map(28)=A/%u want A/2", rpos);
    }
#else
    /* ISR x 300 ticks: 0..255 then saturation (no wrap). */
    count = 0;
    int arm_0a = 0, arm_1c = 0;
    int saw_wrap = 0;
    uint8_t prev = 0;
    for (int tick = 1; tick <= 300; tick++) {
        isr_tick_fixed();
        if (count < prev) {
            saw_wrap = 1;
        }
        prev = count;
        if (count == 0x0A) {
            arm_0a = 1;
        }
        if (count == 0x1C) {
            arm_1c = 1;
        }
        if (tick <= 255) {
            CHECK(count == (uint8_t)tick,
                  "tick %d count=%u want=%d", tick, count, tick);
        } else {
            CHECK(count == 0xFF,
                  "tick %d count=%u want saturated 255", tick, count);
        }
    }
    CHECK(!saw_wrap, "counter wrapped instead of saturating");
    CHECK(count == 0xFF, "final count=%u want 255", count);
    CHECK(arm_0a, "tooth-10 arm never fired in 300 ticks");
    CHECK(arm_1c, "tooth-28 arm never fired in 300 ticks");

    /* Rotor map is pure: global untouched, local % 20 decides A/B. */
    {
        uint8_t rid, rpos;
        count = 28;
        rotor_map(count, &rid, &rpos);
        CHECK(count == 28, "global=%u want untouched 28", count);
        CHECK(rid == 0 && rpos == 2, "map(28)=%u/%u want A/2", rid, rpos);

        count = 10;
        rotor_map(count, &rid, &rpos);
        CHECK(count == 10, "global=%u want untouched 10", count);
        CHECK(rid == 1 && rpos == 0, "map(10)=%u/%u want B/0", rid, rpos);

        count = 255;
        rotor_map(count, &rid, &rpos);
        CHECK(count == 255, "global=%u want untouched 255", count);
        CHECK(rid == 1, "map(255): local=%u rotor=%u want B",
              (uint8_t)(255 % 20), rid);
    }

    /* Repro confirmation: wrap-20 can never reach the 0x1C arm. */
    {
        uint8_t c = 0;
        int hit = 0;
        for (int i = 0; i < 300; i++) {
            c++;
            if (c >= TRIGGER_TOTAL_TEETH) {
                c = 0;
            }
            if (c == 0x1C) {
                hit = 1;
            }
        }
        CHECK(!hit, "repro: wrap-20 unexpectedly reached 0x1C");
    }
#endif

    if (failures == 0) {
        printf("PASS c3_crank_tooth\n");
    } else {
        printf("%d FAILURES c3_crank_tooth\n", failures);
    }
    return failures != 0;
}
