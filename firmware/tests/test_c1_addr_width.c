/*
 * test_c1_addr_width.c — C1 regression: 32-bit RAM addresses must not be
 * truncated into uint16_t locals (task queue + DTC table layer).
 *
 * Firmware sites: firmware/c/main.c (task_read8/16, task_write16,
 *   task_queue_init), firmware/include/dtc.h (dtc_read_code/severity/
 *   status, dtc_write_code), firmware/c/dtc.c (backup/primary/freezestore/
 *   sync address locals). Correct idiom: firmware/include/rtos.h
 *   (uint32_t addr = RTOS_QUEUE_BASE + ...).
 *
 * This harness is host-self-contained (target MMIO cannot be dereferenced
 * on the host): it replicates the exact address expressions from the
 * firmware, byte-for-byte in constant terms, and checks round-trip.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_c1_addr_width.c -o /tmp/fwtest/test_c1_addr_width
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 -DTEST_BUGGY test_c1_addr_width.c -o /tmp/buggy (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

/* Extracted address macros (values identical to platform.h / dtc.h). */
#define TASK_QUEUE_BASE        0xFFFFD4E0u
#define TASK_QUEUE_ENTRY_SIZE  8u
#define DTC_PRIMARY_TABLE_BASE 0xFFFF8928u
#define DTC_PRIMARY_ENTRY_SIZE 0x34u
#define DTC_BACKUP_TABLE_BASE  0xFFFF8EA0u
#define DTC_BACKUP_ENTRY_SIZE  0x28u

/* Fixed idiom (what the firmware must use): full 32-bit address. */
#define TASK_Q_ADDR(idx, off) \
    ((uint32_t)(TASK_QUEUE_BASE + ((idx) * TASK_QUEUE_ENTRY_SIZE) + (off)))
#define DTC_P_ADDR(slot, off) \
    ((uint32_t)(DTC_PRIMARY_TABLE_BASE + ((slot) * DTC_PRIMARY_ENTRY_SIZE) + (off)))
#define DTC_B_ADDR(slot, off) \
    ((uint32_t)(DTC_BACKUP_TABLE_BASE + ((slot) * DTC_BACKUP_ENTRY_SIZE) + (off)))

/* Compile-time contract: address expressions must be >= 32 bits wide. */
typedef uint32_t fw_ram_addr_t;
_Static_assert(sizeof(fw_ram_addr_t) >= 4, "RAM addresses need 32 bits");
_Static_assert(sizeof(TASK_Q_ADDR(0, 0)) >= 4, "task queue addr expr truncated");
_Static_assert(sizeof(DTC_P_ADDR(0, 0)) >= 4, "dtc primary addr expr truncated");
_Static_assert(sizeof(DTC_B_ADDR(0, 0)) >= 4, "dtc backup addr expr truncated");

/* Buggy idiom (pre-fix firmware): truncated into uint16_t. */
uint32_t buggy_task_addr(uint16_t idx, uint8_t off)
{
    uint16_t addr = TASK_QUEUE_BASE + (idx * TASK_QUEUE_ENTRY_SIZE) + off;
    return (uint32_t)(uintptr_t)addr;
}

uint32_t buggy_dtc_addr(uint8_t slot, uint8_t off)
{
    uint16_t addr = DTC_PRIMARY_TABLE_BASE + (slot * DTC_PRIMARY_ENTRY_SIZE) + off;
    return (uint32_t)(uintptr_t)addr;
}

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

int main(void)
{
    const uint16_t task_slots[] = {0, 7, 20, 99};
    const uint8_t dtc_slots[] = {0, 7, 20};
    int i;

    /* 1. Fixed idiom round-trips for task slots 0/7/20/99, all offsets. */
    for (i = 0; i < 4; i++) {
        for (uint32_t off = 0; off < TASK_QUEUE_ENTRY_SIZE; off++) {
            uint32_t expect = 0xFFFFD4E0u + (uint32_t)task_slots[i] * 8u + off;
            uint32_t got = TASK_Q_ADDR(task_slots[i], off);
            CHECK(got == expect, "task fixed slot=%u off=%u got=0x%08lX want=0x%08lX",
                  task_slots[i], (unsigned)off,
                  (unsigned long)got, (unsigned long)expect);
            CHECK((got & 0xFFFF0000u) == 0xFFFF0000u,
                  "task fixed slot=%u lost high page: 0x%08lX",
                  task_slots[i], (unsigned long)got);
        }
    }

    /* 2. Fixed idiom round-trips for DTC primary slots 0/7/20. */
    for (i = 0; i < 3; i++) {
        uint32_t expect = 0xFFFF8928u + (uint32_t)dtc_slots[i] * 0x34u;
        uint32_t got = DTC_P_ADDR(dtc_slots[i], 0);
        CHECK(got == expect, "dtc fixed slot=%u got=0x%08lX want=0x%08lX",
              dtc_slots[i], (unsigned long)got, (unsigned long)expect);
        CHECK((got & 0xFFFF0000u) == 0xFFFF0000u,
              "dtc fixed slot=%u lost high page: 0x%08lX",
              dtc_slots[i], (unsigned long)got);
    }

    /* 3. Fixed idiom round-trips for backup slots 0/7. */
    for (i = 0; i < 2; i++) {
        uint8_t s = (i == 0) ? 0 : 7;
        uint32_t expect = 0xFFFF8EA0u + (uint32_t)s * 0x28u;
        CHECK(DTC_B_ADDR(s, 0) == expect, "dtc backup fixed slot=%u", s);
    }

#ifdef TEST_BUGGY
    /* Pre-fix emulation: the buggy idiom is used as the address. Every
     * access must land on the right page — it does not. */
    for (i = 0; i < 4; i++) {
        uint32_t want = TASK_Q_ADDR(task_slots[i], 0);
        uint32_t got = buggy_task_addr(task_slots[i], 0);
        CHECK(got == want, "BUGGY task slot=%u -> 0x%08lX (want 0x%08lX)",
              task_slots[i], (unsigned long)got, (unsigned long)want);
    }
    for (i = 0; i < 3; i++) {
        uint32_t want = DTC_P_ADDR(dtc_slots[i], 0);
        uint32_t got = buggy_dtc_addr(dtc_slots[i], 0);
        CHECK(got == want, "BUGGY dtc slot=%u -> 0x%08lX (want 0x%08lX)",
              dtc_slots[i], (unsigned long)got, (unsigned long)want);
    }
#else
    /* 4. Repro confirmation: the old uint16_t idiom provably truncates
     * (lands on page 0x0000xxxx instead of 0xFFFFxxxx). */
    for (i = 0; i < 4; i++) {
        uint32_t bad = buggy_task_addr(task_slots[i], 0);
        uint32_t good = TASK_Q_ADDR(task_slots[i], 0);
        CHECK(bad != good, "repro: task slot=%u not truncated?", task_slots[i]);
        CHECK((bad & 0xFFFF0000u) == 0x00000000u,
              "repro: task slot=%u bad addr not on low page: 0x%08lX",
              task_slots[i], (unsigned long)bad);
    }
    for (i = 0; i < 3; i++) {
        uint32_t bad = buggy_dtc_addr(dtc_slots[i], 0);
        uint32_t good = DTC_P_ADDR(dtc_slots[i], 0);
        CHECK(bad != good, "repro: dtc slot=%u not truncated?", dtc_slots[i]);
    }
#endif

    if (failures == 0) {
        printf("PASS c1_addr_width\n");
    } else {
        printf("%d FAILURES c1_addr_width\n", failures);
    }
    return failures != 0;
}
