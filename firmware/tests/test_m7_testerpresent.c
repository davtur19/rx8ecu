/*
 * test_m7_testerpresent.c — M7 regression: TesterPresent (SID 0x3E) accepts
 * only sub-function 0x00; anything else → NRC 0x12 subFunctionNotSupported.
 *
 * Firmware site: firmware/c/uds.c uds_handler TesterPresent arm.
 * Reference: docs/notes/KNOWLEDGE.md:30 (`3E 00` correct, `3E 80` → 0x12).
 * Pre-fix: echoed request[1] unvalidated (any sub-function → positive).
 *
 * Host-self-contained: TesterPresent arm model mirroring the firmware.
 *
 * Build:
 *   gcc -std=c11 -Wall -Wextra -Werror -O2 test_m7_testerpresent.c -o /tmp/fwtest/test_m7_testerpresent
 *   gcc ... -DTEST_BUGGY ... (must FAIL)
 */
#include <stdint.h>
#include <stdio.h>

/* Mirror of the uds_handler TesterPresent arm. */
static int model_tp(const uint8_t *req, uint8_t len, uint8_t *out)
{
#ifdef TEST_BUGGY
    out[0] = 0x7E;
    out[1] = (len > 1) ? req[1] : 0x00;
    return 2;
#else
    uint8_t sub = (len > 1) ? req[1] : 0x00;
    if (sub != 0x00) {
        out[0] = 0x7F;
        out[1] = 0x3E;
        out[2] = 0x12;
        return 3;
    }
    out[0] = 0x7E;
    out[1] = 0x00;
    return 2;
#endif
}

static int failures = 0;

#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); failures++; } \
} while (0)

int main(void)
{
    uint8_t out[8] = { 0 };
    int n;

    /* `3E 00` → positive [0x7E, 0x00]. */
    {
        uint8_t req[2] = { 0x3E, 0x00 };
        n = model_tp(req, 2, out);
        CHECK(n == 2 && out[0] == 0x7E && out[1] == 0x00,
              "3E 00 → len=%d %02X %02X, want 2/7E/00", n, out[0], out[1]);
    }

    /* `3E 80` → 7F 3E 12. */
    {
        uint8_t req[2] = { 0x3E, 0x80 };
        n = model_tp(req, 2, out);
        CHECK(n == 3 && out[0] == 0x7F && out[1] == 0x3E && out[2] == 0x12,
              "3E 80 → len=%d %02X %02X %02X, want 7F 3E 12",
              n, out[0], out[1], out[2]);
    }

    /* Any other non-zero sub-function → 0x12 as well. */
    {
        uint8_t req[2] = { 0x3E, 0x01 };
        n = model_tp(req, 2, out);
        CHECK(n == 3 && out[2] == 0x12, "3E 01 must be 7F 3E 12");
    }

    /* Bare `3E` (no sub-function byte) defaults to 0x00 → positive. */
    {
        uint8_t req[1] = { 0x3E };
        n = model_tp(req, 1, out);
        CHECK(n == 2 && out[0] == 0x7E && out[1] == 0x00,
              "bare 3E → len=%d %02X %02X, want 2/7E/00", n, out[0], out[1]);
    }

    if (failures == 0) {
        printf("PASS m7_testerpresent\n");
    } else {
        printf("%d FAILURES m7_testerpresent\n", failures);
    }
    return failures != 0;
}
