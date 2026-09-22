/*
 * link_c1_addr_width.c — Link co-pilot c1: constant-expression assertions
 * over the REAL TASK_QUEUE_BASE-family / RTOS_QUEUE_BASE /
 * DTC_PRIMARY_TABLE_BASE macros (platform.h + rtos.h + dtc.h), not model
 * replicas.
 *
 * Mechanism proof: includes the real firmware headers via -I$(FW_INC).
 * A firmware revert of any base/stride macro fails this binary at
 * compile time (the value pins at the _Static_assert block below) or at
 * run time (the runtime value CHECKs). This harness compiles NO firmware
 * bodies, so a uint16_t narrowing of an address local inside main.c /
 * dtc.c is NOT visible here — that narrowing is caught by the Makefile
 * gate grep (`uint32_t addr = ...` present, `uint16_t addr = ...`
 * absent), not by this binary. Asserts constants/addresses only — NEVER
 * calls the dereferencing inlines (rtos_queue_get_*, dtc_read_status-
 * family deref 0xFFFFxxxx and would fault on the host). Zero stubs, no
 * MMIO derefs.
 *
 * Proves:
 *   (a) TASK_QUEUE_BASE-family + RTOS_QUEUE_BASE values agree
 *       (0xFFFFD4E0, stride 8, 100 slots);
 *   (b) DTC primary slot arithmetic for slots 0/20/7 stays 32-bit
 *       (uint32_t round-trip: addr == BASE + slot*stride + off, high
 *       page 0xFFFF preserved);
 *   (c) the harness's own address macros are >= 4 bytes wide — a
 *       self-pin of the local macro shape only (the casts are written
 *       in this file); firmware-body narrowing stays with the gate
 *       grep, mirroring the model harness test_c1_addr_width.c contract.
 *
 * Build (see firmware/tests/Makefile link-check):
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 -I../include \
 *       link/link_c1_addr_width.c -o /tmp/fwtest/link_c1_addr_width
 */
#include <stdint.h>
#include <stdio.h>

#include "platform.h"
#include "rtos.h"
#include "dtc.h"

/* Address expressions exactly as the firmware computes them, in uint32_t. */
#define LINK_C1_TASK_ADDR(slot, off) \
    ((uint32_t)((uint32_t)(TASK_QUEUE_BASE) + ((uint32_t)(slot) * (uint32_t)(TASK_QUEUE_ENTRY_SIZE)) + (uint32_t)(off)))
#define LINK_C1_RTOS_ADDR(slot, off) \
    ((uint32_t)((uint32_t)(RTOS_QUEUE_BASE) + ((uint32_t)(slot) * (uint32_t)(RTOS_QUEUE_ENTRY_SIZE)) + (uint32_t)(off)))
#define LINK_C1_DTC_ADDR(slot, off) \
    ((uint32_t)((uint32_t)(DTC_PRIMARY_TABLE_BASE) + ((uint32_t)(slot) * (uint32_t)(DTC_PRIMARY_ENTRY_SIZE)) + (uint32_t)(off)))

/* Compile-time contract: real macro values (fail closed on revert). */
_Static_assert(TASK_QUEUE_BASE == 0xFFFFD4E0, "TASK_QUEUE_BASE revert");
_Static_assert(RTOS_QUEUE_BASE == 0xFFFFD4E0, "RTOS_QUEUE_BASE revert");
_Static_assert(TASK_QUEUE_BASE == RTOS_QUEUE_BASE, "queue base alias split");
_Static_assert(TASK_QUEUE_ENTRY_SIZE == 8, "TASK_QUEUE_ENTRY_SIZE revert");
_Static_assert(RTOS_QUEUE_ENTRY_SIZE == 8, "RTOS_QUEUE_ENTRY_SIZE revert");
_Static_assert(DTC_PRIMARY_TABLE_BASE == 0xFFFF8928, "DTC_PRIMARY_TABLE_BASE revert");
_Static_assert(DTC_PRIMARY_ENTRY_SIZE == 0x34, "DTC_PRIMARY_ENTRY_SIZE revert");
_Static_assert(DTC_PRIMARY_MAX_SLOTS == 21, "DTC_PRIMARY_MAX_SLOTS revert");

/* Width asserts below are self-referential: LINK_C1_*_ADDR cast to
 * uint32_t in THIS file, so sizeof >= 4 is always true — they pin the
 * harness macro shape only and cannot see a firmware-body narrowing
 * (this TU compiles no firmware sources). The Makefile gate grep on
 * `uint32_t addr = ...` / `uint16_t addr = ...` carries that load;
 * keep these as local shape pins, not firmware contracts. */
_Static_assert(sizeof(LINK_C1_TASK_ADDR(0, 0)) >= 4, "task queue addr expr truncated");
_Static_assert(sizeof(LINK_C1_RTOS_ADDR(0, 0)) >= 4, "rtos queue addr expr truncated");
_Static_assert(sizeof(LINK_C1_DTC_ADDR(0, 0)) >= 4, "dtc primary addr expr truncated");
_Static_assert(sizeof(uint32_t) >= 4, "RAM address locals need 32 bits");

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

int main(void)
{
    /* (a) Queue-base family values from the real headers. */
    CHECK((uint32_t)TASK_QUEUE_BASE == 0xFFFFD4E0u,
          "TASK_QUEUE_BASE 0x%08X want 0xFFFFD4E0",
          (unsigned)TASK_QUEUE_BASE);
    CHECK((uint32_t)RTOS_QUEUE_BASE == 0xFFFFD4E0u,
          "RTOS_QUEUE_BASE 0x%08X want 0xFFFFD4E0",
          (unsigned)RTOS_QUEUE_BASE);
    CHECK(LINK_C1_TASK_ADDR(0, 0) == LINK_C1_RTOS_ADDR(0, 0),
          "task vs rtos base alias: 0x%08X vs 0x%08X",
          (unsigned)LINK_C1_TASK_ADDR(0, 0),
          (unsigned)LINK_C1_RTOS_ADDR(0, 0));

    /* Queue slot arithmetic stays on the 0xFFFF page (slots 0/7/99). */
    CHECK(LINK_C1_RTOS_ADDR(0, 0) == 0xFFFFD4E0u,
          "rtos slot0 -> 0x%08X want 0xFFFFD4E0",
          (unsigned)LINK_C1_RTOS_ADDR(0, 0));
    CHECK(LINK_C1_RTOS_ADDR(7, 0) == 0xFFFFD518u,
          "rtos slot7 -> 0x%08X want 0xFFFFD518",
          (unsigned)LINK_C1_RTOS_ADDR(7, 0));
    CHECK(LINK_C1_RTOS_ADDR(99, 7) == 0xFFFFD7FFu,
          "rtos slot99+7 -> 0x%08X want 0xFFFFD7FF",
          (unsigned)LINK_C1_RTOS_ADDR(99, 7));

    /* (b) DTC primary stride arithmetic, slots 0/20/7, computed in
     * uint32_t; round-trip: addr == BASE + slot*stride + off. */
    CHECK(LINK_C1_DTC_ADDR(0, 0) == 0xFFFF8928u,
          "dtc slot0 -> 0x%08X want 0xFFFF8928",
          (unsigned)LINK_C1_DTC_ADDR(0, 0));
    CHECK(LINK_C1_DTC_ADDR(20, 0) == 0xFFFF8D38u,
          "dtc slot20 -> 0x%08X want 0xFFFF8D38",
          (unsigned)LINK_C1_DTC_ADDR(20, 0));
    CHECK(LINK_C1_DTC_ADDR(7, 0) == 0xFFFF8A94u,
          "dtc slot7 -> 0x%08X want 0xFFFF8A94",
          (unsigned)LINK_C1_DTC_ADDR(7, 0));
    CHECK(LINK_C1_DTC_ADDR(7, DTC_REC_SEVERITY_OFFSET) ==
          (uint32_t)(0xFFFF8928u + 7u * 0x34u + 0x07u),
          "dtc slot7+sev -> 0x%08X",
          (unsigned)LINK_C1_DTC_ADDR(7, DTC_REC_SEVERITY_OFFSET));
    CHECK(LINK_C1_DTC_ADDR(20, DTC_REC_FREEZE_OFFSET) ==
          (uint32_t)(0xFFFF8928u + 20u * 0x34u + 0x0Au),
          "dtc slot20+freeze -> 0x%08X",
          (unsigned)LINK_C1_DTC_ADDR(20, DTC_REC_FREEZE_OFFSET));
    CHECK((LINK_C1_DTC_ADDR(20, 0) & 0xFFFF0000u) == 0xFFFF0000u,
          "dtc slot20 lost high page: 0x%08X",
          (unsigned)LINK_C1_DTC_ADDR(20, 0));

    if (failures == 0) {
        printf("PASS link_c1_addr_width (real platform.h/rtos.h/dtc.h)\n");
    } else {
        printf("%d FAILURES link_c1_addr_width\n", failures);
    }
    return failures != 0;
}
