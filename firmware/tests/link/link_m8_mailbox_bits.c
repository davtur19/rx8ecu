/*
 * link_m8_mailbox_bits.c — Link pilot m8: compile-link-run against the REAL
 * can_enable_mailbox_int in firmware/c/can.c (M8 16-bit mailbox-int-enable
 * RMW fix), not a model replica.
 *
 * Mechanism proof: links the real can.c TU, so a firmware revert of the M8
 * fix (`1U << (mailbox & 0x0F)` 16-bit RMW — back to the 8-bit
 * `mailbox & 0x07` idiom, or a write-only store that drops the read) fails
 * this binary at run time, and a signature change fails at compile time
 * (extern decl via can.h).
 *
 * Refactor-path coverage (the whole point of m8 scoping):
 *   - 16-bit distinct bits: mailboxes 0-15 each set exactly their own bit
 *     in the interrupt-enable register (16 distinct nonzero expects);
 *   - TX-mailbox alias kill: MB10/MB11 (TX uses 0x08-0x0B) must land on
 *     bits 10/11, not bits 2/3 (the pre-fix `& 0x07` alias);
 *   - mask wrap: mailbox 0x12 -> bit 2, 0x10 -> bit 0, 0x1F -> bit 15
 *     (kills an unmasked `1U << mailbox` mutant);
 *   - RMW preservation: a primed nonzero high byte survives the enable
 *     (kills a write-only `*reg = bit` mutant);
 *   - controller bank isolation: controller 0 RMWs 0xFFFFE400, controller 1
 *     RMWs 0xFFFFE600, each leaving the other register's primed value
 *     untouched;
 *   - all-16 accumulation: enabling 0-15 yields 0xFFFF.
 *
 * Host execution boundary (same mechanism as link_h1_mbox — same TU):
 *   - Zero stubs: can.c has no undefined externs (`nm -u can.c` clean) —
 *     exactly like dtc.c (m2/h2) and engine.c (h4).
 *   - MMIO is real: the SH-2 0xFFFFExxx register page does not exist on the
 *     host (bare deref segfaults), so the test maps ONE 4 KiB page at
 *     0xFFFFE000 with mmap(MAP_FIXED), covering BOTH enable registers
 *     (0xFFFFE400 CAN0 and 0xFFFFE600 CAN1). The function's 16-bit
 *     read-modify-write then executes for real on mapped memory. The
 *     register literals live in the can.c body (controller ? 0xFFFFE601 :
 *     0xFFFFE401, minus 1) — pinned below as local constants, h4-style.
 *   - No constructor/init-time MMIO: can.c file-scope statics are plain
 *     zero-init / constant pointer initializers (verified: link_h1 runs
 *     can.c with no mapping at all).
 *   - Same unused-static relaxation as h1 (can_parse_mailbox_id/dir;
 *     firmware sources untouched).
 *
 * Proves (every assert killable; zero-expects are primed first):
 *   (a) mailboxes 0-15 on CAN0 each set exactly their own bit
 *       (16 nonzero expects, reg primed 0 before each);
 *   (b) MB10 -> 0x0400 and MB11 -> 0x0800 (no alias onto bits 2/3);
 *   (c) mask wrap: MB0x12 -> 0x0004, MB0x10 -> 0x0001, MB0x1F -> 0x8000;
 *   (d) RMW preserves a primed nonzero high byte: CAN0 0xAB00|MB0 ->
 *       0xAB01, CAN1 0x5A00|MB3 -> 0x5A08;
 *   (e) bank isolation: both regs primed 0x0F0F (nonzero) — enable(1,5)
 *       makes CAN1 0x0F2F and leaves CAN0 at the nonzero prime 0x0F0F,
 *       then enable(0,4) makes CAN0 0x0F1F and leaves CAN1 at 0x0F2F;
 *   (f) enabling all 16 mailboxes on CAN0 yields 0xFFFF (nonzero).
 *
 * Build (see firmware/tests/Makefile link-check):
 *   gcc -std=c11 -Wall -Wextra -Werror -Wno-error=unused-function -O2 \
 *       -I../include link/link_m8_mailbox_bits.c ../c/can.c \
 *       -o /tmp/fwtest/link_m8_mailbox_bits
 */
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>

#include "can.h"

/* Extern declaration comes from the real can.h (linking the real can.c
 * TU): a signature change in firmware breaks this build. Pin the bank
 * contract values so a revert breaks the build, not just the run — these
 * also anchor the 0xFFFFE4xx/0xFFFFE6xx family the enable registers sit
 * in (same pins as link_h1). */
_Static_assert(HCAN_MBOX_REG_ADDR == 0xFFFFE406, "HCAN_MBOX_REG_ADDR revert");
_Static_assert(HCAN_MBOX_READY_ADDR == 0xFFFFE40A, "HCAN_MBOX_READY_ADDR revert");
_Static_assert(HCAN_MBOX_STATUS_ADDR == 0xFFFFE40E, "HCAN_MBOX_STATUS_ADDR revert");
_Static_assert(HCAN_MBOX_DATA_RDY_ADDR == 0xFFFFE41A, "HCAN_MBOX_DATA_RDY_ADDR revert");

/* The enable-register literals live in the can.c body (reg_base-1 where
 * reg_base = controller ? 0xFFFFE601 : 0xFFFFE401), so pin the addresses
 * the test maps — a firmware move of the enable registers must also move
 * this mapping or (a)-(e) fail loudly. Both words fit ONE 4 KiB page. */
#define M8_PAGE_BASE       0xFFFFE000u
#define M8_PAGE_LEN        0x1000u
#define M8_CAN0_INT_ENABLE 0xFFFFE400u  /* controller 0, 16-bit RMW */
#define M8_CAN1_INT_ENABLE 0xFFFFE600u  /* controller 1, 16-bit RMW */

_Static_assert(M8_CAN0_INT_ENABLE >= M8_PAGE_BASE &&
               M8_CAN0_INT_ENABLE + 2u <= M8_PAGE_BASE + M8_PAGE_LEN,
               "CAN0 enable reg outside mapped page");
_Static_assert(M8_CAN1_INT_ENABLE >= M8_PAGE_BASE &&
               M8_CAN1_INT_ENABLE + 2u <= M8_PAGE_BASE + M8_PAGE_LEN,
               "CAN1 enable reg outside mapped page");

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

static volatile uint16_t *m8_reg(uint8_t controller)
{
    return (volatile uint16_t *)(uintptr_t)
        (controller ? M8_CAN1_INT_ENABLE : M8_CAN0_INT_ENABLE);
}

int main(void)
{
    void *p = mmap((void *)(uintptr_t)M8_PAGE_BASE, M8_PAGE_LEN,
                   PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (p == (void *)-1) {
        printf("FAIL: mmap(0xFFFFE000) failed\n");
        return 1;
    }

    /* (a) mailboxes 0-15: each sets exactly its own bit on CAN0. Register
     * primed 0 before every call, so each expect is a distinct nonzero
     * value — a zero-returning/stuck mutant is red on the first line. */
    for (uint8_t mb = 0; mb < 16; mb++) {
        *m8_reg(0) = 0u;
        can_enable_mailbox_int(0, mb);
        CHECK(*m8_reg(0) == (uint16_t)(1u << mb),
              "CAN0 mb %u -> 0x%04X want 0x%04X",
              mb, (unsigned)*m8_reg(0), (unsigned)(1u << mb));
    }

    /* (b) TX mailboxes 10/11 must not alias onto bits 2/3 (pre-fix
     * `& 0x07` gives 0x0004/0x0008 — both nonzero, both red here). */
    *m8_reg(0) = 0u;
    can_enable_mailbox_int(0, 10);
    CHECK(*m8_reg(0) == 0x0400u,
          "CAN0 mb10 -> 0x%04X want 0x0400 (aliased MB2?)",
          (unsigned)*m8_reg(0));
    *m8_reg(0) = 0u;
    can_enable_mailbox_int(0, 11);
    CHECK(*m8_reg(0) == 0x0800u,
          "CAN0 mb11 -> 0x%04X want 0x0800 (aliased MB3?)",
          (unsigned)*m8_reg(0));

    /* (c) mask wrap: high mailbox numbers wrap with & 0x0F (an unmasked
     * `1U << mailbox` gives 0x4000/0x0001-wrong/0x8000-when-truncated —
     * every expect is a distinct nonzero value). */
    *m8_reg(0) = 0u;
    can_enable_mailbox_int(0, 0x12);
    CHECK(*m8_reg(0) == 0x0004u,
          "CAN0 mb0x12 -> 0x%04X want 0x0004 (unmasked 1<<0x12?)",
          (unsigned)*m8_reg(0));
    *m8_reg(0) = 0u;
    can_enable_mailbox_int(0, 0x10);
    CHECK(*m8_reg(0) == 0x0001u,
          "CAN0 mb0x10 -> 0x%04X want 0x0001",
          (unsigned)*m8_reg(0));
    *m8_reg(0) = 0u;
    can_enable_mailbox_int(0, 0x1F);
    CHECK(*m8_reg(0) == 0x8000u,
          "CAN0 mb0x1F -> 0x%04X want 0x8000",
          (unsigned)*m8_reg(0));

    /* (d) RMW preserves primed nonzero high bytes: a write-only store
     * (`*reg = bit`) drops the 0xAB/0x5A prime → red. */
    *m8_reg(0) = 0xAB00u;
    can_enable_mailbox_int(0, 0);
    CHECK(*m8_reg(0) == 0xAB01u,
          "CAN0 prime AB00|MB0 -> 0x%04X want 0xAB01",
          (unsigned)*m8_reg(0));
    *m8_reg(1) = 0x5A00u;
    can_enable_mailbox_int(1, 3);
    CHECK(*m8_reg(1) == 0x5A08u,
          "CAN1 prime 5A00|MB3 -> 0x%04X want 0x5A08",
          (unsigned)*m8_reg(1));

    /* (e) bank isolation: both registers primed to the SAME nonzero value
     * 0x0F0F (bit 5 and bit 4 clear, so a wrong-bank RMW changes them).
     * enable(1,5) must bump CAN1 to 0x0F2F and leave CAN0 at its nonzero
     * prime; then the symmetric check for enable(0,4). Every expect here
     * is nonzero, so each is killable (h4 F1 lesson: no bare zero-expects
     * without a primed nonzero first). */
    *m8_reg(0) = 0x0F0Fu;
    *m8_reg(1) = 0x0F0Fu;
    can_enable_mailbox_int(1, 5);
    CHECK(*m8_reg(1) == 0x0F2Fu,
          "CAN1 prime 0F0F|MB5 -> 0x%04X want 0x0F2F",
          (unsigned)*m8_reg(1));
    CHECK(*m8_reg(0) == 0x0F0Fu,
          "CAN0 changed by controller-1 call -> 0x%04X want prime 0x0F0F",
          (unsigned)*m8_reg(0));
    can_enable_mailbox_int(0, 4);
    CHECK(*m8_reg(0) == 0x0F1Fu,
          "CAN0 prime 0F0F|MB4 -> 0x%04X want 0x0F1F",
          (unsigned)*m8_reg(0));
    CHECK(*m8_reg(1) == 0x0F2Fu,
          "CAN1 changed by controller-0 call -> 0x%04X want 0x0F2F",
          (unsigned)*m8_reg(1));

    /* (f) enabling all 16 mailboxes accumulates to all-ones (nonzero). */
    *m8_reg(0) = 0u;
    for (uint8_t mb = 0; mb < 16; mb++) {
        can_enable_mailbox_int(0, mb);
    }
    CHECK(*m8_reg(0) == 0xFFFFu,
          "CAN0 all 16 -> 0x%04X want 0xFFFF", (unsigned)*m8_reg(0));

    munmap((void *)(uintptr_t)M8_PAGE_BASE, M8_PAGE_LEN);

    if (failures == 0) {
        printf("PASS link_m8_mailbox_bits (real can.c TU)\n");
    } else {
        printf("%d FAILURES link_m8_mailbox_bits\n", failures);
    }
    return failures != 0;
}
