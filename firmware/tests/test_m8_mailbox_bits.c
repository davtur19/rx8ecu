/*
 * test_m8_mailbox_bits.c — M8 regression: can_enable_mailbox_int must set
 * one distinct enable bit per mailbox index 0-15 (16-bit mask).
 *
 * Firmware site: firmware/c/can.c can_enable_mailbox_int (:517 was
 *   `1U << (mailbox & 0x07)` into an 8-bit register — TX uses MB 0x08-0x0B,
 *   so enabling MB10/11 set MB2/MB3's bits). Inconsistent with
 *   can_get_mailbox_config (:215, 16-entry `& 0x0F` table 0x0001-0x8000)
 *   and can_init_mailbox_irq_mask (writes 16-bit 0xFF12 to the
 *   interrupt-enable register), proving the register is 16-bit.
 * Fix: `1U << (mailbox & 0x0F)` into a 16-bit RMW. No split per-bank
 * enables found in the notes — single 16-bit register per controller.
 *
 * Host-self-contained model of the enable RMW. Assertions: each index
 * 0-15 sets exactly its own bit; enabling all yields 0xFFFF.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_m8_mailbox_bits.c -o /tmp/fwtest/test_m8_mailbox_bits
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

static uint16_t enable_reg;

#ifdef TEST_BUGGY
static void enable_mb(uint8_t mailbox)
{
    uint8_t cur = (uint8_t)(enable_reg & 0xFF);
    cur |= (uint8_t)(1U << (mailbox & 0x07));
    enable_reg = (uint16_t)((enable_reg & 0xFF00) | cur);
}
#else
static void enable_mb(uint8_t mailbox)
{
    uint16_t cur = enable_reg;
    cur |= (uint16_t)(1U << (mailbox & 0x0F));
    enable_reg = cur;
}
#endif

int main(void)
{
    /* Each index sets exactly its own bit. */
    for (uint8_t mb = 0; mb < 16; mb++) {
        enable_reg = 0;
        enable_mb(mb);
        CHECK(enable_reg == (uint16_t)(1U << mb),
              "mb %u mask=0x%04X want 0x%04X", mb, enable_reg,
              (uint16_t)(1U << mb));
    }

    /* TX mailboxes 8-11 must not alias 0-3. */
    enable_reg = 0;
    enable_mb(10);
    CHECK(enable_reg == 0x0400,
          "mb10 mask=0x%04X want 0x0400 (aliased MB2?)", enable_reg);
    enable_reg = 0;
    enable_mb(11);
    CHECK(enable_reg == 0x0800,
          "mb11 mask=0x%04X want 0x0800 (aliased MB3?)", enable_reg);

    /* Enabling all 0-15 yields all 16 bits. */
    enable_reg = 0;
    for (uint8_t mb = 0; mb < 16; mb++) {
        enable_mb(mb);
    }
    CHECK(enable_reg == 0xFFFF,
          "all mask=0x%04X want 0xFFFF", enable_reg);

    if (failures == 0) {
        printf("PASS m8_mailbox_bits\n");
    } else {
        printf("%d FAILURES m8_mailbox_bits\n", failures);
    }
    return failures != 0;
}
