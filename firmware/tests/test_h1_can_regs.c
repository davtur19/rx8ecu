/*
 * test_h1_can_regs.c — H1 regression: CAN register addressing.
 *
 * Pre-fix TX passed HCAN_MBOX_OFFSET (a 16-bit register *content*) as the
 * reg_addr argument; pre-fix RX passed PFC *offsets* (0x000C/0x0018), so the
 * helper dereferenced 0x000C/0x0018 (SH7055 vector area). Fixed call sites
 * pass the absolute addresses (can.h: HCAN_MBOX_REG_ADDR etc.).
 *
 * Firmware sites: firmware/c/can.c:715,734,753 (TX), :1514,1529,1542 (RX).
 *
 * Host-self-contained: exact copy of can_get_mailbox_offset_high plus the
 * call-site argument constants; asserts effective addresses for idx 0/3/0x20.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_h1_can_regs.c -o /tmp/fwtest/test_h1_can_regs
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

/* Correct absolute constants (firmware/include/can.h). */
#define HCAN_MBOX_REG_ADDR      0xFFFFE406u
#define HCAN_MBOX_READY_ADDR    0xFFFFE40Au
#define HCAN_MBOX_STATUS_ADDR   0xFFFFE40Eu
#define HCAN_MBOX_DATA_RDY_ADDR 0xFFFFE41Au

/* Pre-fix arguments: register contents / PFC offsets. */
#define WRONG_TX_CONTENT        0x803Eu  /* typical HCAN_MBOX_OFFSET content */
#define WRONG_RX_OFFSET_STATUS  0x000Cu  /* HCAN_REG_MBOX_STATUS (PFC offset) */
#define WRONG_RX_OFFSET_DATA    0x0018u  /* HCAN_REG_MBOX_DATA_READY (offset) */

/* Exact copy of can_get_mailbox_offset_high (firmware/c/can.c). */
uint32_t mbox_effective(uint8_t mailbox_idx, uint32_t reg_addr)
{
    uint32_t addr = reg_addr;
    if (mailbox_idx >= 0x20) {
        addr += 0x200u;
    }
    return addr;
}

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

int main(void)
{
    const uint8_t idxs[] = {0, 3, 0x20};
    /* (fixed reg passed at each call site, expected CAN0 effective) */
    struct {
        const char *site;
        uint32_t fixed_reg;
        uint32_t expect_c0;
    } sites[] = {
        {"TX status :715", HCAN_MBOX_REG_ADDR, 0xFFFFE406u},
        {"TX ready  :734", HCAN_MBOX_READY_ADDR, 0xFFFFE40Au},
        {"TX trig   :753", HCAN_MBOX_REG_ADDR, 0xFFFFE406u},
        {"RX status :1514", HCAN_MBOX_STATUS_ADDR, 0xFFFFE40Eu},
        {"RX data   :1529", HCAN_MBOX_DATA_RDY_ADDR, 0xFFFFE41Au},
        {"RX retry  :1542", HCAN_MBOX_DATA_RDY_ADDR, 0xFFFFE41Au},
    };
    /* Buggy argument used at each site pre-fix. */
#ifdef TEST_BUGGY
    const uint32_t buggy_reg[] = {
        WRONG_TX_CONTENT, WRONG_TX_CONTENT, WRONG_TX_CONTENT,
        WRONG_RX_OFFSET_STATUS, WRONG_RX_OFFSET_DATA, WRONG_RX_OFFSET_DATA,
    };
#endif

    for (unsigned s = 0; s < 6; s++) {
        for (unsigned k = 0; k < 3; k++) {
            uint8_t idx = idxs[k];
            uint32_t bank = (idx >= 0x20) ? 0x200u : 0u;
            uint32_t want = sites[s].expect_c0 + bank;
#ifdef TEST_BUGGY
            uint32_t got = mbox_effective(idx, buggy_reg[s]);
            CHECK(got == want, "BUGGY %s idx=0x%02X eff=0x%08lX want=0x%08lX",
                  sites[s].site, idx, (unsigned long)got, (unsigned long)want);
#else
            uint32_t got = mbox_effective(idx, sites[s].fixed_reg);
            CHECK(got == want, "%s idx=0x%02X eff=0x%08lX want=0x%08lX",
                  sites[s].site, idx, (unsigned long)got, (unsigned long)want);
#endif
        }
    }

#ifndef TEST_BUGGY
    /* Repro: the old arguments provably dereference the wrong page. */
    CHECK(mbox_effective(0, WRONG_TX_CONTENT) != 0xFFFFE406u,
          "repro: TX content arg must not yield 0xFFFFE406");
    CHECK(mbox_effective(0, WRONG_RX_OFFSET_STATUS) == 0x000Cu,
          "repro: RX status offset arg lands on 0x000C (vector area)");
    CHECK(mbox_effective(0, WRONG_RX_OFFSET_DATA) == 0x0018u,
          "repro: RX data offset arg lands on 0x0018 (vector area)");
#endif

    if (failures == 0) {
        printf("PASS h1_can_regs\n");
    } else {
        printf("%d FAILURES h1_can_regs\n", failures);
    }
    return failures != 0;
}
