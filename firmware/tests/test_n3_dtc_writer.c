/*
 * test_n3_dtc_writer.c — N3 regression: the dtc_state_machine SET path must
 * persist the ROM +0x06 status byte (bit 7=confirmed, bit 6=failed) in
 * addition to the SEVERITY/FLAGS3 bytes the composite reader observes.
 *
 * Firmware sites: firmware/c/dtc.c dtc_state_machine mode 1 (writer),
 *   firmware/include/dtc.h dtc_read_status (composite reader, unchanged).
 * ROM reference: docs/notes/IDA_ANALYSIS.md:707 ("+0x06: status byte
 *   (bit 7=confirmed, bit 6=failed)"). +0x09 FLAGS3 stays firmware-local
 *   (no ROM provenance — IDA layout jumps +0x07→+0x0A).
 *
 * Host-self-contained: RAM-backed 52-byte record + SET-path and reader
 * models mirroring the firmware.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_n3_dtc_writer.c -o /tmp/fwtest/test_n3_dtc_writer
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

#define REC_SIZE 0x34
#define OFF_06   0x06
#define OFF_07   0x07
#define OFF_09   0x09

#define ST_CONFIRMED   0x80u
#define ST_FAILED      0x40u
#define ST_TEST_FAILED 0x10u
#define ST_PENDING     0x20u

static uint8_t rec[REC_SIZE];

/* SET path model. Fixed (dtc.c mode 1 after N3): writes +0x06 confirmed/
 * failed bits plus SEVERITY/FLAGS3. Buggy: SEVERITY/FLAGS3 only. */
static void model_set(void)
{
#ifndef TEST_BUGGY
    rec[OFF_06] |= (uint8_t)(ST_CONFIRMED | ST_FAILED);
#endif
    rec[OFF_07] = ST_CONFIRMED;
    rec[OFF_09] |= ST_TEST_FAILED;
}

/* Composite reader model (dtc_read_status — unchanged by N3). */
static uint8_t model_read_status(void)
{
    return (uint8_t)(rec[OFF_07] | rec[OFF_09]);
}

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

int main(void)
{
    for (int i = 0; i < REC_SIZE; i++) {
        rec[i] = 0;
    }
    /* A plausible pre-existing OBD class nibble in +0x06 must survive SET
     * (writer uses |=, not =). */
    rec[OFF_06] = 0x03;

    model_set();

    /* N3: raw +0x06 shows confirmed + failed bits. */
    CHECK((rec[OFF_06] & (ST_CONFIRMED | ST_FAILED)) ==
          (ST_CONFIRMED | ST_FAILED),
          "+0x06 raw=0x%02X, want confirmed|failed bits", rec[OFF_06]);
    /* Pre-existing low bits preserved by the |= write. */
    CHECK((rec[OFF_06] & 0x03u) == 0x03u,
          "+0x06 low bits clobbered: 0x%02X", rec[OFF_06]);

    /* Composite reader still matches (h2 harness behavior preserved). */
    CHECK((model_read_status() & ST_CONFIRMED) != 0,
          "composite 0x%02X lacks confirmed", model_read_status());
    CHECK((model_read_status() & ST_TEST_FAILED) != 0,
          "composite 0x%02X lacks test-failed", model_read_status());

    /* Pending lifecycle on the firmware-local +0x09 still observable. */
    rec[OFF_09] |= ST_PENDING;
    CHECK((model_read_status() & ST_PENDING) != 0, "pending must show");
    rec[OFF_09] &= (uint8_t)~ST_PENDING;
    CHECK((model_read_status() & ST_PENDING) == 0, "pending must clear");
    CHECK((model_read_status() & ST_CONFIRMED) != 0,
          "confirmed must survive pending clear");

    if (failures == 0) {
        printf("PASS n3_dtc_writer\n");
    } else {
        printf("%d FAILURES n3_dtc_writer\n", failures);
    }
    return failures != 0;
}
