/*
 * test_m2_checksum.c — M2 regression: dtc_region_checksum_validate_8928 must
 * implement the documented check (guard words at 0xFFFF8920/0xFFFF8924 plus
 * per-entry 15-byte additive sum == 0xA5 mod 256), not the old tautology
 * that always returned 1.
 *
 * Firmware site: firmware/c/dtc.c dtc_region_checksum_validate_8928.
 * ROM reference: docs/notes/IDA_ANALYSIS.md:715 ("guards 0xFFFF8920/8924,
 *   15-byte sum per entry = 0xA5"). dtc_init already recovers on 0
 *   (reinitializes slots) — no init change needed.
 *
 * Host-self-contained: guard pair + 21×52-byte table model with the exact
 * fixed expressions (blank-guard reject, empty-slot skip, 15-byte sum vs
 * 0xA5). Buggy model: unconditional 1.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_m2_checksum.c -o /tmp/fwtest/test_m2_checksum
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

#define SLOTS 21
#define REC_SIZE 0x34

static uint16_t guard0, guard1;
static uint8_t table[SLOTS][REC_SIZE];

#ifdef TEST_BUGGY
static int model_validate(void)
{
    return 1; /* old tautology: inner `sum==0` check unreachable */
}
#else
/* Exact mirror of the fixed dtc_region_checksum_validate_8928. */
static int model_validate(void)
{
    if (guard0 == 0xFFFF || guard0 == 0x0000 ||
        guard1 == 0xFFFF || guard1 == 0x0000) {
        return 0;
    }
    for (uint8_t i = 0; i < SLOTS; i++) {
        uint16_t code = (uint16_t)(((uint16_t)table[i][0] << 8) |
                                   table[i][1]);
        if (code == 0xFFFF || code == 0x0000) {
            continue;
        }
        uint16_t sum = 0;
        for (uint8_t j = 0; j < 15; j++) {
            sum += table[i][j];
        }
        if ((sum & 0xFFu) != 0xA5u) {
            return 0;
        }
    }
    return 1;
}
#endif

/* Fill one slot so its first-15-byte sum ≡ 0xA5 (mod 256): fixed code bytes
 * plus a computed adjust byte at index 14. */
static void make_valid_slot(uint8_t s, uint8_t c0, uint8_t c1)
{
    for (int j = 0; j < REC_SIZE; j++) {
        table[s][j] = 0;
    }
    table[s][0] = c0;
    table[s][1] = c1;
    table[s][6] = 0xC0; /* status bits, arbitrary payload */
    table[s][7] = 0x80;
    uint16_t sum = 0;
    for (int j = 0; j < 14; j++) {
        sum += table[s][j];
    }
    table[s][14] = (uint8_t)((0xA5u - (sum & 0xFFu)) & 0xFFu);
}

static void fill(uint8_t v)
{
    for (int i = 0; i < SLOTS; i++) {
        for (int j = 0; j < REC_SIZE; j++) {
            table[i][j] = v;
        }
    }
}

/* Empty-canonical slot: code 0xFFFF, rest 0xFF (dtc_init recovery image). */
static void make_empty_slots(void)
{
    fill(0xFF);
}

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

int main(void)
{
    /* All-zero image → 0 (blank guards). */
    guard0 = 0x0000;
    guard1 = 0x0000;
    fill(0x00);
    CHECK(model_validate() == 0, "all-zero image must return 0");

    /* All-0xFF image → 0 (erased guards). */
    guard0 = 0xFFFF;
    guard1 = 0xFFFF;
    fill(0xFF);
    CHECK(model_validate() == 0, "all-0xFF image must return 0");

    /* Valid table → 1 (guards live, one checksummed slot, rest empty). */
    guard0 = 0xA5A5;
    guard1 = 0x5AA5;
    make_empty_slots();
    make_valid_slot(3, 0x02, 0x02);
    CHECK(model_validate() == 1, "valid table must return 1");

    /* Corrupt slot (one payload byte flipped → sum != 0xA5) → 0. */
    table[3][7] ^= 0x01;
    CHECK(model_validate() == 0, "corrupt slot must return 0");
    table[3][7] ^= 0x01;
    CHECK(model_validate() == 1, "un-corrupted table must return 1 again");

    /* Live slots but blanked guards → 0 (guard half of the check). */
    guard0 = 0xFFFF;
    guard1 = 0x5AA5;
    CHECK(model_validate() == 0, "blank guard0 must return 0");
    guard0 = 0xA5A5;
    guard1 = 0x0000;
    CHECK(model_validate() == 0, "blank guard1 must return 0");

    if (failures == 0) {
        printf("PASS m2_checksum\n");
    } else {
        printf("%d FAILURES m2_checksum\n", failures);
    }
    return failures != 0;
}
