/*
 * test_h2_dtc_status.c — H2 regression: DTC status readers must observe the
 * bytes the state machine writes (SEVERITY 0x07 / FLAGS3 0x09), not the
 * never-written TYPE byte (0x06).
 *
 * Firmware sites: firmware/include/dtc.h dtc_read_status (:419-425),
 *   writers firmware/c/dtc.c:464-465,475,484,225,
 *   readers :661-665 (worst_priority), :809-813 (sid18), :884-885 (sid12).
 * ROM reference: IDA_ANALYSIS.md DTC layout — +0x06 status byte
 *   (bit7=confirmed, bit6=failed), +0x07 severity (0x80=confirmed); the C
 *   state machine persists status in SEVERITY/FLAGS3, so dtc_read_status
 *   returns the SEVERITY|FLAGS3 composite.
 *
 * Host-self-contained: RAM-backed record model + mini sid18/sid12/
 * worst_priority loops mirroring the firmware readers.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_h2_dtc_status.c -o /tmp/fwtest/test_h2_dtc_status
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

#define SLOTS 21
#define REC_SIZE 0x34

#define TYPE_OFF 0x06
#define SEV_OFF  0x07
#define FLAGS3_OFF 0x09

#define ST_CONFIRMED   0x80u
#define ST_TEST_FAILED 0x10u
#define ST_PENDING     0x20u

static uint8_t table[SLOTS][REC_SIZE];
static uint16_t codes[SLOTS];

/* SET path copied from dtc_state_machine mode 1 (dtc.c:463-466). */
void model_set(uint8_t slot)
{
    table[slot][SEV_OFF] = ST_CONFIRMED;
    table[slot][FLAGS3_OFF] |= ST_TEST_FAILED;
}

uint8_t buggy_read_status(uint8_t slot)
{
    return table[slot][TYPE_OFF];
}

uint8_t fixed_read_status(uint8_t slot)
{
    return (uint8_t)(table[slot][SEV_OFF] | table[slot][FLAGS3_OFF]);
}

#ifdef TEST_BUGGY
#define READ_STATUS buggy_read_status
#else
#define READ_STATUS fixed_read_status
#endif

/* Mini readers mirroring obd_sid18_readDTCInfo / obd_sid12_readDTCByStatus /
 * dtc_find_worst_priority filtering. */
int mini_sid18_count(uint8_t mask)
{
    int n = 0;
    for (uint8_t i = 0; i < SLOTS; i++) {
        if (codes[i] == 0xFFFFu || codes[i] == 0u) {
            continue;
        }
        /* sid18 counts by status mask over every occupied slot. */
        if ((READ_STATUS(i) & mask) != 0) {
            n++;
        }
    }
    return n;
}

int mini_sid12(uint8_t mask, uint8_t *out)
{
    uint8_t idx = 2;
    out[0] = 0x52;
    out[1] = 0x02;
    for (uint8_t i = 0; i < SLOTS; i++) {
        uint8_t st = READ_STATUS(i);
        if ((st & mask) != 0) {
            if (codes[i] != 0xFFFFu && codes[i] != 0u) {
                out[idx] = (uint8_t)(codes[i] >> 8);
                out[idx + 1] = (uint8_t)(codes[i]);
                out[idx + 2] = st;
                idx += 3;
            }
        }
    }
    return idx;
}

int mini_worst(uint8_t mask, uint16_t *code)
{
    int n = 0;
    uint16_t worst = 0xFFFFu;
    for (uint8_t i = 0; i < SLOTS; i++) {
        if (codes[i] == 0xFFFFu || codes[i] == 0u) {
            continue;
        }
        if ((READ_STATUS(i) & mask) != 0) {
            n++;
            worst = codes[i];
        }
    }
    *code = worst;
    return n;
}

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

int main(void)
{
    for (int i = 0; i < SLOTS; i++) {
        codes[i] = 0xFFFFu;
        for (int j = 0; j < REC_SIZE; j++) {
            table[i][j] = 0;
        }
    }

    /* SET one DTC in slot 3. */
    codes[3] = 0x0202u;
    model_set(3);

    /* Pending-clear path (dtc.c:225) must also be observable. */
    table[3][FLAGS3_OFF] |= ST_PENDING;

    CHECK(mini_sid18_count(ST_CONFIRMED) == 1,
          "sid18 count mask 0x80 = %d, want 1", mini_sid18_count(ST_CONFIRMED));

    uint8_t out[64];
    int len = mini_sid12(ST_CONFIRMED, out);
    CHECK(len == 5, "sid12 len=%d want 5", len);
    CHECK(out[2] == 0x02 && out[3] == 0x02,
          "sid12 record bytes %02X %02X want 02 02", out[2], out[3]);
    CHECK((out[4] & ST_CONFIRMED) != 0, "sid12 status 0x%02X lacks 0x80", out[4]);

    uint16_t wcode = 0;
    int n = mini_worst(ST_CONFIRMED, &wcode);
    CHECK(n == 1 && wcode == 0x0202u, "worst n=%d code=0x%04X", n, wcode);

    /* Pending mask must match while pending is set ... */
    CHECK(mini_sid18_count(ST_PENDING) == 1, "pending mask must match");
    /* ... and stop matching after the aging/clear path clears it. */
    table[3][FLAGS3_OFF] &= (uint8_t)~ST_PENDING;
    CHECK(mini_sid18_count(ST_PENDING) == 0, "pending mask must clear");
    CHECK(mini_sid18_count(ST_CONFIRMED) == 1, "confirmed must survive");

    if (failures == 0) {
        printf("PASS h2_dtc_status\n");
    } else {
        printf("%d FAILURES h2_dtc_status\n", failures);
    }
    return failures != 0;
}
