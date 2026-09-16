/*
 * link_h1_mbox.c — Link pilot h1: compile-link-run against the REAL
 * H1-fixed pure mailbox getters in firmware/c/can.c (getHCANRegAddr,
 * can_get_mailbox_offset_high, can_get_mailbox_config), not model replicas.
 *
 * Mechanism proof: links the real can.c TU, so a firmware revert of the H1
 * absolute-address fix (e.g. recomputing from HCAN_REG_MBOX_OFFSET or
 * dropping the +0x200 CAN1 bank) fails this binary at run time, and a
 * signature change fails at compile time (extern decls via can.h).
 *
 * Purity (verified by reading the can.c bodies, NOT assumed): none of the
 * three functions dereferences 0xFFFFxxxx — getHCANRegAddr is pure
 * arithmetic, can_get_mailbox_offset_high only casts the computed address
 * to a pointer (this test NEVER dereferences the returned pointers, it
 * integer-compares them), can_get_mailbox_config reads only its static
 * const ROM bitmask table. Zero stubs: can.c has no undefined externs
 * (nm -u clean), so no stub .c files are needed.
 *
 * Proves:
 *   (a) getHCANRegAddr: controller 0 returns the offset as-is
 *       (0xFFFFE406), controller 1 adds the 0x200 CAN1 bank;
 *   (b) can_get_mailbox_offset_high: idx 0/3 stay on the CAN0 bank for all
 *       four H1 registers (0xFFFFE406/0xFFFFE40A/0xFFFFE40E/0xFFFFE41A),
 *       idx 0x20 maps to the +0x200 bank;
 *   (c) can_get_mailbox_config: 1 << (idx & 0x0F), incl. wrap for 0x20.
 *
 * Build (see firmware/tests/Makefile link-check):
 *   gcc -std=c11 -Wall -Wextra -Werror -Wno-error=unused-function -O2 \
 *       -I../include link/link_h1_mbox.c ../c/can.c -o /tmp/fwtest/link_h1_mbox
 */
#include <stdint.h>
#include <stdio.h>

#include "can.h"

/* Extern declarations come from the real can.h (linking the real can.c TU):
 * a signature change in firmware breaks this build. */
_Static_assert(HCAN_MBOX_REG_ADDR == 0xFFFFE406, "HCAN_MBOX_REG_ADDR revert");
_Static_assert(HCAN_MBOX_READY_ADDR == 0xFFFFE40A, "HCAN_MBOX_READY_ADDR revert");
_Static_assert(HCAN_MBOX_STATUS_ADDR == 0xFFFFE40E, "HCAN_MBOX_STATUS_ADDR revert");
_Static_assert(HCAN_MBOX_DATA_RDY_ADDR == 0xFFFFE41A, "HCAN_MBOX_DATA_RDY_ADDR revert");

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

/* Integer-compare only: NEVER dereference the returned mailbox pointers
 * (they are absolute 0xFFFFxxxx MMIO addresses, invalid on the host). */
#define PTR_ADDR(p) ((uint32_t)(uintptr_t)(p))

int main(void)
{
    static const uint32_t regs[4] = {
        HCAN_MBOX_REG_ADDR,       /* 0xFFFFE406 */
        HCAN_MBOX_READY_ADDR,     /* 0xFFFFE40A */
        HCAN_MBOX_STATUS_ADDR,    /* 0xFFFFE40E */
        HCAN_MBOX_DATA_RDY_ADDR,  /* 0xFFFFE41A */
    };
    int i;

    /* (a) getHCANRegAddr: CAN0 as-is, CAN1 +0x200 bank. */
    CHECK(getHCANRegAddr(0, 0xFFFFE406u) == 0xFFFFE406u,
          "getHCANRegAddr(0, E406) -> 0x%08X want 0xFFFFE406",
          (unsigned)getHCANRegAddr(0, 0xFFFFE406u));
    CHECK(getHCANRegAddr(1, 0xFFFFE406u) == 0xFFFFE606u,
          "getHCANRegAddr(1, E406) -> 0x%08X want 0xFFFFE606",
          (unsigned)getHCANRegAddr(1, 0xFFFFE406u));
    CHECK(getHCANRegAddr(0, 0xFFFFE41Au) == 0xFFFFE41Au,
          "getHCANRegAddr(0, E41A) -> 0x%08X want 0xFFFFE41A",
          (unsigned)getHCANRegAddr(0, 0xFFFFE41Au));
    CHECK(getHCANRegAddr(1, 0xFFFFE41Au) == 0xFFFFE61Au,
          "getHCANRegAddr(1, E41A) -> 0x%08X want 0xFFFFE61A",
          (unsigned)getHCANRegAddr(1, 0xFFFFE41Au));

    /* (b) can_get_mailbox_offset_high: idx 0/3 primary bank for all four
     * H1 registers, idx 0x20 secondary (+0x200) bank. Boundary 0x1F/0x21. */
    for (i = 0; i < 4; i++) {
        CHECK(PTR_ADDR(can_get_mailbox_offset_high(0, regs[i])) == regs[i],
              "mbox idx0 reg[%d] -> 0x%08X want 0x%08X",
              i, (unsigned)PTR_ADDR(can_get_mailbox_offset_high(0, regs[i])),
              (unsigned)regs[i]);
        CHECK(PTR_ADDR(can_get_mailbox_offset_high(3, regs[i])) == regs[i],
              "mbox idx3 reg[%d] -> 0x%08X want 0x%08X",
              i, (unsigned)PTR_ADDR(can_get_mailbox_offset_high(3, regs[i])),
              (unsigned)regs[i]);
        CHECK(PTR_ADDR(can_get_mailbox_offset_high(0x1F, regs[i])) == regs[i],
              "mbox idx1F reg[%d] -> 0x%08X want 0x%08X",
              i, (unsigned)PTR_ADDR(can_get_mailbox_offset_high(0x1F, regs[i])),
              (unsigned)regs[i]);
        CHECK(PTR_ADDR(can_get_mailbox_offset_high(0x20, regs[i])) == regs[i] + 0x200u,
              "mbox idx20 reg[%d] -> 0x%08X want 0x%08X",
              i, (unsigned)PTR_ADDR(can_get_mailbox_offset_high(0x20, regs[i])),
              (unsigned)(regs[i] + 0x200u));
        CHECK(PTR_ADDR(can_get_mailbox_offset_high(0x21, regs[i])) == regs[i] + 0x200u,
              "mbox idx21 reg[%d] -> 0x%08X want 0x%08X",
              i, (unsigned)PTR_ADDR(can_get_mailbox_offset_high(0x21, regs[i])),
              (unsigned)(regs[i] + 0x200u));
    }

    /* (c) can_get_mailbox_config: full 16-entry bitmask + idx masking. */
    for (i = 0; i < 16; i++) {
        CHECK(can_get_mailbox_config((uint8_t)i) == (uint16_t)(1u << i),
              "mbox cfg %d -> 0x%04X want 0x%04X",
              i, (unsigned)can_get_mailbox_config((uint8_t)i),
              (unsigned)(1u << i));
    }
    CHECK(can_get_mailbox_config(3) == 0x0008u,
          "mbox cfg 3 -> 0x%04X want 0x0008",
          (unsigned)can_get_mailbox_config(3));
    CHECK(can_get_mailbox_config(0x20) == 0x0001u,
          "mbox cfg 0x20 -> 0x%04X want 0x0001 (idx & 0x0F)",
          (unsigned)can_get_mailbox_config(0x20));
    CHECK(can_get_mailbox_config(0x13) == 0x0008u,
          "mbox cfg 0x13 -> 0x%04X want 0x0008 (idx & 0x0F)",
          (unsigned)can_get_mailbox_config(0x13));

    if (failures == 0) {
        printf("PASS link_h1_mbox (real can.c TU)\n");
    } else {
        printf("%d FAILURES link_h1_mbox\n", failures);
    }
    return failures != 0;
}
