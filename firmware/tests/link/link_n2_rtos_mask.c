/*
 * link_n2_rtos_mask.c — Link pilot n2: compile-link-run against the REAL
 * firmware/include/rtos.h inline accessors (rtos_build_dispatch /
 * rtos_dispatch_get_handler|get_type|get_priority), not a model replica.
 *
 * Mechanism proof: includes "rtos.h" from FW_INC (-I$(FW_INC)), so a
 * firmware revert of RTOS_DISP_HANDLER_MASK (0x00FFFFFF -> 0x0FFFFFFF) or a
 * signature change fails this binary at compile or run time. Reuses the
 * same vectors as the model harness test_n2_rtos_mask.c (full type×prio
 * round-trip + polluted-word extraction + type-7 word).
 *
 * Build (see firmware/tests/Makefile link-check):
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 -I../include \
 *       link/link_n2_rtos_mask.c -o /tmp/fwtest/link_n2_rtos_mask
 */
#include <stdint.h>
#include <stdio.h>

#include "rtos.h"

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

int main(void)
{
    /* Round-trip: every type/prio combo must preserve the handler. */
    for (uint8_t t = 0; t < 8; t++) {
        for (uint8_t p = 0; p < 4; p++) {
            uint32_t d = rtos_build_dispatch(0x00081234u, t, p);
            CHECK(rtos_dispatch_get_handler(d) == 0x00081234u,
                  "handler=0x%08X type=%u prio=%u -> 0x%08X",
                  0x00081234u, t, p, rtos_dispatch_get_handler(d));
            CHECK(rtos_dispatch_get_type(d) == t,
                  "type: handler=0x%08X type=%u prio=%u -> %u",
                  0x00081234u, t, p, rtos_dispatch_get_type(d));
            CHECK(rtos_dispatch_get_priority(d) == p,
                  "prio: handler=0x%08X type=%u prio=%u -> %u",
                  0x00081234u, t, p, rtos_dispatch_get_priority(d));
        }
    }

    /* Polluted word (type=2, prio=3 overlaid): clean low 24 bits out. */
    CHECK(rtos_dispatch_get_handler(0x32FF1234u) == 0x00FF1234u,
          "polluted 0x32FF1234 -> 0x%08X want 0x00FF1234",
          rtos_dispatch_get_handler(0x32FF1234u));

    /* Type-7 word: no type residue in the handler. */
    CHECK(rtos_dispatch_get_handler(rtos_build_dispatch(0x00081234u, 7, 0))
          == 0x00081234u,
          "type7 -> 0x%08X want 0x00081234",
          rtos_dispatch_get_handler(rtos_build_dispatch(0x00081234u, 7, 0)));

    if (failures == 0) {
        printf("PASS link_n2_rtos_mask (real rtos.h)\n");
    } else {
        printf("%d FAILURES link_n2_rtos_mask\n", failures);
    }
    return failures != 0;
}
