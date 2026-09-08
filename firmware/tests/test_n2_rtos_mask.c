/*
 * test_n2_rtos_mask.c — N2 regression: RTOS_DISP_HANDLER_MASK must be
 * 0x00FFFFFF so type bits 24-26 (and any priority residue) never pollute
 * the handler address.
 *
 * Firmware site: firmware/include/rtos.h:98-102 (was 0x0FFFFFFF: keeps
 *   bits 24-27, so the first typed enqueue calls a type-polluted address).
 * Verified: only mask users are rtos_dispatch_get_handler /
 *   rtos_build_dispatch (consumed by rtos_dispatch + rtos_scheduler in
 *   firmware/c/rtos.c); the RTOS queue has no external producers today
 *   (only the scheduler's own lower-priority re-enqueue) — nothing depends
 *   on bits 24-28 surviving in the handler. SH handler addresses fit in 24
 *   bits (512 KB flash @ 0x000000).
 *
 * Assertions: build/extract round-trip is identity for every type/prio
 * combo; a polluted dispatch word extracts to the clean low 24 bits.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_n2_rtos_mask.c -o /tmp/fwtest/test_n2_rtos_mask
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

#ifdef TEST_BUGGY
#define HANDLER_MASK 0x0FFFFFFFu
#else
#define HANDLER_MASK 0x00FFFFFFu
#endif
#define TYPE_SHIFT 24
#define TYPE_MASK 0x07u
#define PRIO_SHIFT 28
#define PRIO_MASK 0x03u

static uint32_t build_dispatch(uint32_t handler, uint8_t type, uint8_t prio)
{
    return (handler & HANDLER_MASK)
           | ((uint32_t)(type & TYPE_MASK) << TYPE_SHIFT)
           | ((uint32_t)(prio & PRIO_MASK) << PRIO_SHIFT);
}

static uint32_t get_handler(uint32_t dispatch)
{
    return dispatch & HANDLER_MASK;
}

int main(void)
{
    /* Round-trip: every type/prio combo must preserve the handler. */
    for (uint8_t t = 0; t < 8; t++) {
        for (uint8_t p = 0; p < 4; p++) {
            uint32_t d = build_dispatch(0x00081234u, t, p);
            CHECK(get_handler(d) == 0x00081234u,
                  "handler=0x%08X type=%u prio=%u -> 0x%08X",
                  0x00081234u, t, p, get_handler(d));
        }
    }

    /* Polluted word (type=2, prio=3 overlaid): clean low 24 bits out. */
    CHECK(get_handler(0x32FF1234u) == 0x00FF1234u,
          "polluted 0x32FF1234 -> 0x%08X want 0x00FF1234",
          get_handler(0x32FF1234u));

    /* Type-7 word: no type residue in the handler. */
    CHECK(get_handler(build_dispatch(0x00081234u, 7, 0)) == 0x00081234u,
          "type7 -> 0x%08X want 0x00081234",
          get_handler(build_dispatch(0x00081234u, 7, 0)));

    if (failures == 0) {
        printf("PASS n2_rtos_mask\n");
    } else {
        printf("%d FAILURES n2_rtos_mask\n", failures);
    }
    return failures != 0;
}
